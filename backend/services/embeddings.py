"""
Trinity Backend - Embeddings Service
FastEmbed-based text embeddings for RAG and semantic memory

Phase 5: Integrated with EmbeddingCache for cost optimization.
"""

import logging
from typing import List, Optional
import numpy as np

from config import EMBEDDING_MODEL, EMBEDDING_DIM

logger = logging.getLogger(__name__)

# Lazy-load FastEmbed to avoid slow startup
_embedding_model = None

# Lazy-load cache to avoid circular imports
_cache = None


def _get_cache():
    """Lazy-load the embedding cache."""
    global _cache
    if _cache is None:
        try:
            from services.caching import get_embedding_cache
            _cache = get_embedding_cache()
        except ImportError:
            logger.warning("Caching module not available - embeddings will not be cached")
    return _cache


def get_embedding_model():
    """Get or initialize the FastEmbed model (lazy loading)."""
    global _embedding_model
    
    if _embedding_model is None:
        try:
            from fastembed import TextEmbedding
            logger.info(f'🧠 Loading embedding model: {EMBEDDING_MODEL}')
            _embedding_model = TextEmbedding(model_name=EMBEDDING_MODEL)
            logger.info(f'✅ Embedding model loaded ({EMBEDDING_DIM} dimensions)')
        except ImportError:
            logger.error('❌ FastEmbed not installed. Run: pip install fastembed')
            return None
        except Exception as e:
            logger.error(f'❌ Failed to load embedding model: {e}')
            return None
    
    return _embedding_model


def embed_text(text: str, use_cache: bool = True) -> Optional[np.ndarray]:
    """
    Generate embedding for a single text.
    
    Args:
        text: Text to embed
        use_cache: Whether to use embedding cache (default True)
        
    Returns:
        numpy array of shape (384,) or None on failure
    """
    # Try cache first
    if use_cache:
        cache = _get_cache()
        if cache:
            cached = cache.get(text)
            if cached is not None:
                return cached
    
    model = get_embedding_model()
    if model is None:
        return None
    
    try:
        # FastEmbed returns a generator, convert to list
        embeddings = list(model.embed([text]))
        if embeddings:
            embedding = np.array(embeddings[0], dtype=np.float32)
            
            # Cache the result
            if use_cache:
                cache = _get_cache()
                if cache:
                    cache.put(text, embedding)
            
            return embedding
        return None
    except Exception as e:
        logger.error(f'❌ Embedding error: {e}')
        return None


def embed_batch(texts: List[str], use_cache: bool = True) -> List[np.ndarray]:
    """
    Generate embeddings for multiple texts efficiently.
    
    Uses cache for texts that have been seen before.
    
    Args:
        texts: List of texts to embed
        use_cache: Whether to use embedding cache (default True)
        
    Returns:
        List of numpy arrays, each of shape (384,)
    """
    if not texts:
        return []
    
    cache = _get_cache() if use_cache else None
    results: List[Optional[np.ndarray]] = [None] * len(texts)
    texts_to_embed: List[tuple[int, str]] = []  # (index, text)
    
    # Check cache first
    if cache:
        for i, text in enumerate(texts):
            cached = cache.get(text)
            if cached is not None:
                results[i] = cached
            else:
                texts_to_embed.append((i, text))
    else:
        texts_to_embed = list(enumerate(texts))
    
    # Embed uncached texts
    if texts_to_embed:
        model = get_embedding_model()
        if model is None:
            return []
        
        try:
            uncached_texts = [t for _, t in texts_to_embed]
            embeddings = list(model.embed(uncached_texts))
            
            for (orig_idx, text), emb in zip(texts_to_embed, embeddings):
                embedding = np.array(emb, dtype=np.float32)
                results[orig_idx] = embedding
                
                # Cache the new embedding
                if cache:
                    cache.put(text, embedding)
                    
        except Exception as e:
            logger.error(f'❌ Batch embedding error: {e}')
            return []
    
    # Filter out any None values (shouldn't happen normally)
    return [r for r in results if r is not None]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Similarity score between -1 and 1
    """
    if a is None or b is None:
        return 0.0
    
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return float(np.dot(a, b) / (norm_a * norm_b))


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Split text into overlapping chunks for embedding.
    
    Uses simple word-based chunking. For production, consider
    sentence-aware splitting.
    
    Args:
        text: Text to chunk
        chunk_size: Target words per chunk
        overlap: Words to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if not text:
        return []
    
    words = text.split()
    chunks = []
    
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = ' '.join(words[start:end])
        chunks.append(chunk)
        
        if end >= len(words):
            break
        
        start = end - overlap
    
    return chunks


def compute_text_hash(text: str) -> str:
    """
    Compute a hash of text for deduplication.
    
    Args:
        text: Text to hash
        
    Returns:
        Hex string hash
    """
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


# Module availability flag for graceful degradation
V4_EMBEDDINGS_AVAILABLE = True
