"""
PicklesGPT Chat Handler

Main chat endpoint for Pickles persona with:
- RAG search against trading book library
- Market data integration (when available)
- Enhanced prompt building
"""

import logging
import requests
from typing import Dict, List, Optional
from flask import Blueprint, request, jsonify

from .persona import (
    build_pickles_prompt,
    should_search_books,
    extract_search_query,
    extract_symbols,
    PICKLES_IDENTITY
)

logger = logging.getLogger(__name__)

# Create Blueprint for Pickles routes
pickles_bp = Blueprint('pickles', __name__, url_prefix='/pickles')

# ChromaDB store (initialized on first use)
_vector_store = None

def get_vector_store():
    """Lazy-load the vector store."""
    global _vector_store
    if _vector_store is None:
        try:
            from .vector_store import VectorStore
            import os
            db_path = os.environ.get('CHROMA_PERSIST_DIR', '/data/chroma')
            _vector_store = VectorStore(db_path=db_path)
            logger.info(f"📚 Vector store initialized: {_vector_store.collection.count()} chunks")
        except Exception as e:
            logger.warning(f"⚠️ Vector store not available: {e}")
            _vector_store = None
    return _vector_store


def search_books(query: str, n_results: int = 3) -> List[Dict]:
    """
    Search the book library for relevant passages.
    
    Returns list of dicts with 'text', 'metadata', 'score'.
    """
    store = get_vector_store()
    if store is None:
        logger.warning("📚 Vector store not available - RAG disabled")
        return []
    
    try:
        results = store.search(query, n_results=n_results)
        logger.info(f"📚 RAG search: '{query[:50]}...' → {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"📚 RAG search failed: {e}")
        return []


def get_market_data(symbols: Dict[str, List[str]]) -> Optional[Dict]:
    """
    Fetch real-time market data for mentioned symbols.
    
    Uses yfinance for stocks/indices, CoinGecko for crypto.
    Returns None if no data needed or fetch fails.
    """
    # Check if any symbols mentioned
    all_symbols = []
    for category in symbols.values():
        all_symbols.extend(category)
    
    if not all_symbols:
        return None
    
    try:
        import yfinance as yf
        
        data = {}
        
        # Fetch stock/ETF/index data
        stock_symbols = symbols.get('stocks', []) + symbols.get('indices', [])
        if stock_symbols:
            data['stocks'] = {}
            for sym in stock_symbols[:5]:  # Limit to 5
                try:
                    ticker = yf.Ticker(sym)
                    info = ticker.fast_info
                    data['stocks'][sym] = {
                        'price': round(info.last_price, 2),
                        'change_percent': round(info.regular_market_change_percent, 2) if hasattr(info, 'regular_market_change_percent') else 0
                    }
                except Exception as e:
                    logger.warning(f"Could not fetch {sym}: {e}")
        
        # Fetch crypto data (simplified)
        crypto_symbols = symbols.get('crypto', [])
        if crypto_symbols:
            data['crypto'] = {}
            # Map to CoinGecko IDs
            crypto_map = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana'}
            for sym in crypto_symbols[:3]:
                if sym in crypto_map:
                    try:
                        ticker = yf.Ticker(f"{sym}-USD")
                        info = ticker.fast_info
                        data['crypto'][sym] = {
                            'price': info.last_price,
                            'change_24h': 0  # Would need additional API call
                        }
                    except:
                        pass
        
        return data if data else None
        
    except ImportError:
        logger.warning("yfinance not installed - market data disabled")
        return None
    except Exception as e:
        logger.error(f"Market data fetch failed: {e}")
        return None


@pickles_bp.route('/chat', methods=['POST'])
def pickles_chat():
    """
    Main Pickles chat endpoint with RAG and market data.
    
    Request:
        - prompt: User message
        - contextMemory: Previous messages
        - principal: User ID (optional)
    
    Response:
        - generated_text: Pickles' response
        - rag_used: Whether book RAG was used
        - books_cited: List of books referenced
        - market_data: Real-time data included
    """
    try:
        data = request.get_json()
        user_prompt = data.get('prompt', '')
        context_messages = data.get('contextMemory', [])
        principal = data.get('principal')
        
        if not user_prompt:
            return jsonify({'error': 'Prompt required'}), 400
        
        # 1. Check if we should search books
        book_excerpts = []
        if should_search_books(user_prompt):
            search_query = extract_search_query(user_prompt)
            book_excerpts = search_books(search_query)
        
        # 2. Check for market symbols and fetch data
        symbols = extract_symbols(user_prompt)
        market_data = get_market_data(symbols)
        
        # 3. Load user memory if available
        user_memory = None
        if principal:
            try:
                from inference_server import load_user_memory
                user_memory = load_user_memory(principal)
            except:
                pass
        
        # 4. Build full prompt
        full_prompt = build_pickles_prompt(
            user_message=user_prompt,
            context_messages=context_messages,
            book_excerpts=book_excerpts,
            market_data=market_data,
            user_memory=user_memory
        )
        
        # 5. Generate with Ollama
        import os
        ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        model_name = os.environ.get('MODEL_NAME', 'llama3.1:8b')
        
        response = requests.post(
            f"{ollama_host}/api/generate",
            json={
                "model": model_name,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": -1
                }
            },
            timeout=120
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama returned {response.status_code}")
        
        result = response.json()
        generated_text = result.get('response', '')
        
        # 6. Build response
        books_cited = [
            ex['metadata'].get('book_title', 'Unknown')
            for ex in book_excerpts
        ] if book_excerpts else []
        
        return jsonify({
            'generated_text': generated_text,
            'model': model_name,
            'rag_used': len(book_excerpts) > 0,
            'books_cited': books_cited,
            'market_data_included': market_data is not None,
            'persona': 'pickles'
        })
        
    except Exception as e:
        logger.error(f"Pickles chat error: {e}")
        return jsonify({'error': str(e)}), 500


@pickles_bp.route('/search', methods=['POST'])
def search_library():
    """
    Direct search endpoint for the book library.
    
    Request:
        - query: Search query
        - n_results: Max results (default 5)
        - category: Optional category filter
    
    Response:
        - results: Array of {text, metadata, score}
    """
    try:
        data = request.get_json()
        query = data.get('query', '')
        n_results = data.get('n_results', 5)
        category = data.get('category')
        
        if not query:
            return jsonify({'error': 'Query required'}), 400
        
        store = get_vector_store()
        if store is None:
            return jsonify({'error': 'Vector store not initialized'}), 503
        
        results = store.search(query, n_results=n_results, category_filter=category)
        
        return jsonify({
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500


@pickles_bp.route('/status', methods=['GET'])
def pickles_status():
    """
    Get Pickles system status.
    
    Returns:
        - vector_store: Whether book library is loaded
        - book_count: Number of books indexed
        - chunk_count: Total chunks in database
        - categories: Available book categories
    """
    try:
        store = get_vector_store()
        
        if store is None:
            return jsonify({
                'status': 'limited',
                'vector_store': False,
                'message': 'Book library not loaded - RAG disabled'
            })
        
        stats = store.get_stats()
        
        return jsonify({
            'status': 'ready',
            'vector_store': True,
            'chunk_count': stats.get('total_chunks', 0),
            'book_count': stats.get('book_count', 0),
            'categories': stats.get('categories', [])
        })
        
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500
