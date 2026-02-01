"""
Trinity Backend - Embeddings Service
FastEmbed-based text embeddings for RAG and semantic memory
"""

import logging
from typing import List, Optional
import numpy as np

from config import EMBEDDING_MODEL, EMBEDDING_DIM

logger = logging.getLogger(__name__)

# Lazy-load FastEmbed to avoid slow startup
_embedding_model = None


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


def embed_text(text: str) -> Optional[np.ndarray]:
    """
    Generate embedding for a single text.
    
    Args:
        text: Text to embed
        
    Returns:
        numpy array of shape (384,) or None on failure
    """
    model = get_embedding_model()
    if model is None:
        return None
    
    try:
        # FastEmbed returns a generator, convert to list
        embeddings = list(model.embed([text]))
        if embeddings:
            return np.array(embeddings[0], dtype=np.float32)
        return None
    except Exception as e:
        logger.error(f'❌ Embedding error: {e}')
        return None


def embed_batch(texts: List[str]) -> List[np.ndarray]:
    """
    Generate embeddings for multiple texts efficiently.
    
    Args:
        texts: List of texts to embed
        
    Returns:
        List of numpy arrays, each of shape (384,)
    """
    if not texts:
        return []
    
    model = get_embedding_model()
    if model is None:
        return []
    
    try:
        embeddings = list(model.embed(texts))
        return [np.array(e, dtype=np.float32) for e in embeddings]
    except Exception as e:
        logger.error(f'❌ Batch embedding error: {e}')
        return []


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
