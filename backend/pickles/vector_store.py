"""
PicklesGPT Vector Store Interface

ChromaDB wrapper for semantic search across trading books.
"""

import logging
from typing import List, Dict, Optional
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False

logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB vector store for trading book RAG.
    """
    
    def __init__(
        self,
        db_path: str = "/data/chroma",
        collection_name: str = "trading_books",
        embedding_model: str = "all-MiniLM-L6-v2"
    ):
        if not HAS_CHROMA:
            raise ImportError("chromadb required: pip install chromadb")
        if not HAS_EMBEDDINGS:
            raise ImportError("sentence-transformers required")
        
        self.db_path = db_path
        self.collection_name = collection_name
        
        # Initialize embedding model
        logger.info(f"Loading embedding model: {embedding_model}")
        self.embedder = SentenceTransformer(embedding_model)
        
        # Initialize ChromaDB
        logger.info(f"Connecting to ChromaDB at: {db_path}")
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Get collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        logger.info(f"Collection '{collection_name}' has {self.collection.count()} chunks")
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        category_filter: Optional[str] = None,
        author_filter: Optional[str] = None,
        min_relevance: float = 0.3
    ) -> List[Dict]:
        """
        Search for relevant chunks.
        
        Args:
            query: Natural language search query
            n_results: Max results to return
            category_filter: Filter by category (e.g., "Options")
            author_filter: Filter by author
            min_relevance: Minimum similarity score (0-1)
        
        Returns:
            List of dicts with text, metadata, and score
        """
        # Build where filter
        where = {}
        if category_filter:
            where["category"] = category_filter
        if author_filter:
            where["author"] = author_filter
        
        # Generate query embedding
        query_embedding = self.embedder.encode(query).tolist()
        
        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where if where else None,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        formatted = []
        for i in range(len(results['documents'][0])):
            # Convert distance to similarity (cosine)
            distance = results['distances'][0][i]
            similarity = 1 - distance  # Cosine distance to similarity
            
            if similarity >= min_relevance:
                formatted.append({
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'score': round(similarity, 4)
                })
        
        return formatted
    
    def search_by_book(
        self,
        book_title: str,
        query: str,
        n_results: int = 5
    ) -> List[Dict]:
        """
        Search within a specific book.
        """
        query_embedding = self.embedder.encode(query).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where={"book_title": {"$contains": book_title}},
            include=["documents", "metadatas", "distances"]
        )
        
        formatted = []
        for i in range(len(results['documents'][0])):
            distance = results['distances'][0][i]
            similarity = 1 - distance
            formatted.append({
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'score': round(similarity, 4)
            })
        
        return formatted
    
    def get_categories(self) -> List[str]:
        """Get all unique categories."""
        # This is a workaround since ChromaDB doesn't have distinct()
        # In practice, we'd cache this
        categories = set()
        results = self.collection.get(
            limit=10000,
            include=["metadatas"]
        )
        for meta in results['metadatas']:
            categories.add(meta.get('category', 'Unknown'))
        return sorted(list(categories))
    
    def get_books(self, category: Optional[str] = None) -> List[Dict]:
        """Get list of books, optionally filtered by category."""
        where = {"category": category} if category else None
        
        results = self.collection.get(
            limit=10000,
            where=where,
            include=["metadatas"]
        )
        
        # Deduplicate by book title
        books = {}
        for meta in results['metadatas']:
            title = meta.get('book_title', 'Unknown')
            if title not in books:
                books[title] = {
                    'title': title,
                    'author': meta.get('author', 'Unknown'),
                    'category': meta.get('category', 'Unknown')
                }
        
        return sorted(list(books.values()), key=lambda x: x['title'])
    
    def get_stats(self) -> Dict:
        """Get collection statistics."""
        return {
            'total_chunks': self.collection.count(),
            'categories': self.get_categories(),
            'book_count': len(self.get_books()),
            'db_path': self.db_path
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_store_instance = None

def get_store(
    db_path: str = "/data/chroma",
    collection_name: str = "trading_books"
) -> VectorStore:
    """
    Get singleton instance of vector store.
    """
    global _store_instance
    if _store_instance is None:
        _store_instance = VectorStore(db_path, collection_name)
    return _store_instance


def search_books(
    query: str,
    n_results: int = 5,
    category: Optional[str] = None
) -> List[Dict]:
    """
    Quick search function.
    """
    store = get_store()
    return store.search(query, n_results, category_filter=category)
