"""
PicklesGPT Book Ingestion Pipeline

Smart PDF processing with:
- Front matter detection (skip copyright, TOC, intros)
- Semantic chunking (by paragraphs/sections)
- Rich metadata extraction (title, author, chapter, page)
- Batch embedding with sentence-transformers

Usage:
    python -m pickles.ingest_books --library /path/to/books --db /path/to/chroma
"""

import os
import re
import json
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

# These will be imported when running on server with dependencies
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    print("Warning: PyMuPDF not installed. Run: pip install PyMuPDF")

try:
    from sentence_transformers import SentenceTransformer
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False
    print("Warning: sentence-transformers not installed")

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    print("Warning: chromadb not installed")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# FRONT MATTER DETECTION PATTERNS
# =============================================================================

# Pages to always skip (by content patterns)
SKIP_PATTERNS = [
    # Copyright & Legal
    r'(?i)all rights reserved',
    r'(?i)copyright\s*©?\s*\d{4}',
    r'(?i)isbn[\s:-]*[\d-]+',
    r'(?i)library of congress',
    r'(?i)printed in (the )?united states',
    r'(?i)no part of this (book|publication)',
    r'(?i)permission (in writing|to reproduce)',
    r'(?i)trademark(s)? (of|are)',
    
    # Publisher Info
    r'(?i)published by\s+\w+',
    r'(?i)first (edition|printing)',
    r'(?i)cover design',
    r'(?i)typeset in',
    r'(?i)editorial\s+\w+',
    
    # Table of Contents
    r'(?i)^table of contents$',
    r'(?i)^contents$',
    r'(?i)chapter\s+\d+\s*\.{3,}\s*\d+',  # Chapter 1 ..... 15
    r'(?i)^\s*\d+\s*$',  # Just page numbers
    
    # Front/Back Matter
    r'(?i)^dedication$',
    r'(?i)^acknowledgment',
    r'(?i)^about the author',
    r'(?i)^foreword$',
    r'(?i)^preface$',
    r'(?i)^index$',
    r'(?i)^bibliography$',
    r'(?i)^glossary$',
    r'(?i)^appendix\s*[a-z]?$',
]

# Minimum content to consider a page valid
MIN_PAGE_CHARS = 200
MIN_PAGE_WORDS = 50

# Chapter detection patterns
CHAPTER_PATTERNS = [
    r'(?i)^chapter\s+(\d+|[ivxlc]+)',
    r'(?i)^part\s+(\d+|[ivxlc]+)',
    r'(?i)^section\s+(\d+)',
    r'(?i)^\d+\.\s+[A-Z]',  # 1. Introduction
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BookMetadata:
    """Metadata extracted from PDF"""
    title: str
    author: str
    category: str  # Folder name (Options, Day Trading, etc.)
    file_path: str
    total_pages: int
    content_start_page: int  # First page of actual content
    extraction_date: str


@dataclass
class TextChunk:
    """A chunk of text with metadata"""
    text: str
    book_title: str
    author: str
    category: str
    chapter: Optional[str]
    page_number: int
    chunk_index: int
    source_file: str
    char_count: int
    word_count: int


# =============================================================================
# FRONT MATTER DETECTION
# =============================================================================

def is_front_matter(text: str) -> Tuple[bool, str]:
    """
    Detect if a page is front matter that should be skipped.
    
    Returns:
        (should_skip, reason)
    """
    text_lower = text.lower().strip()
    
    # Too short to be real content
    if len(text) < MIN_PAGE_CHARS:
        return True, "too_short"
    
    word_count = len(text.split())
    if word_count < MIN_PAGE_WORDS:
        return True, "too_few_words"
    
    # Check against skip patterns
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, text):
            return True, f"pattern:{pattern[:30]}"
    
    # High ratio of numbers to text (likely TOC or index)
    numbers = len(re.findall(r'\d+', text))
    words = len(text.split())
    if words > 0 and numbers / words > 0.3:
        return True, "high_number_ratio"
    
    # Too many dots (TOC pattern: Chapter 1 ........ 15)
    dots = text.count('.')
    if dots > 20 and dots / len(text) > 0.05:
        return True, "toc_dots"
    
    # Detect TOC pages by multiple chapter references
    # A real chapter page has ONE "Chapter X" at the top, not many
    chapter_mentions = len(re.findall(r'(?i)chapter\s+\d+', text))
    if chapter_mentions >= 3:
        return True, "toc_multiple_chapters"
    
    # Detect pages with lots of page number references (TOC indicator)
    # Pattern: word followed by number at end of line
    page_refs = len(re.findall(r'\w+\s+\d+\s*$', text, re.MULTILINE))
    if page_refs >= 5:
        return True, "toc_page_references"
    
    return False, "content"


def is_chapter_page(text: str) -> bool:
    """
    Detect if a page is a real chapter start (not TOC).
    
    Real chapter pages have:
    - ONE chapter heading
    - Followed by substantial body text
    - NOT a list of other chapters
    """
    # Check for chapter heading
    chapter_match = re.search(r'(?i)^chapter\s+(\d+|[ivxlc]+)', text, re.MULTILINE)
    if not chapter_match:
        return False
    
    # If there are multiple chapter references, it's probably TOC
    chapter_count = len(re.findall(r'(?i)chapter\s+\d+', text))
    if chapter_count >= 3:
        return False
    
    # Check for substantial text after the chapter heading
    # Real chapters have paragraphs, not just titles
    lines = text.split('\n')
    long_lines = [l for l in lines if len(l) > 60]  # Prose has long lines
    
    return len(long_lines) >= 3


def find_content_start(doc) -> int:
    """
    Find the first page of actual book content.
    
    Scans from the beginning looking for:
    - First REAL chapter heading (not TOC)
    - End of front matter patterns
    
    Returns the page index (0-based) where content starts.
    """
    for page_num in range(min(50, len(doc))):  # Check first 50 pages max
        page = doc[page_num]
        text = page.get_text()
        
        # Check if this is a real chapter page (not TOC)
        if is_chapter_page(text):
            logger.info(f"  Found chapter start at page {page_num + 1}")
            return page_num
        
        # Skip if it's front matter
        is_fm, reason = is_front_matter(text)
        if is_fm:
            continue
        
        # Found substantial non-front-matter content
        # Only consider it content if we're past typical front matter section
        if page_num > 8:  # Most front matter is < 8 pages
            logger.info(f"  Content detected at page {page_num + 1}")
            return page_num
    
    # Default: start at page 15 if nothing else found
    # (conservative - better to skip some content than include junk)
    return min(15, len(doc) - 1)


# =============================================================================
# TEXT EXTRACTION
# =============================================================================

def extract_title_author(doc, file_path: str) -> Tuple[str, str]:
    """
    Extract title and author from PDF metadata or filename.
    """
    # Try PDF metadata first
    metadata = doc.metadata
    title = metadata.get('title', '').strip()
    author = metadata.get('author', '').strip()
    
    # Fallback to filename parsing
    if not title or title.lower() in ['untitled', 'unknown']:
        filename = Path(file_path).stem
        # Clean up filename: "Trading_Options_For_Dummies_(2008)" -> "Trading Options For Dummies"
        title = re.sub(r'\s*\(\d{4}\)\s*', '', filename)  # Remove years
        title = re.sub(r'[_-]', ' ', title)  # Replace underscores/hyphens
        title = title.strip()
    
    if not author:
        # Try to extract author from filename patterns like "Author - Title.pdf"
        if ' - ' in Path(file_path).stem:
            parts = Path(file_path).stem.split(' - ')
            if len(parts) == 2:
                author = parts[0].strip()
    
    return title or "Unknown Title", author or "Unknown Author"


def extract_chapter(text: str) -> Optional[str]:
    """
    Extract chapter title from page text if present.
    """
    for pattern in CHAPTER_PATTERNS:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            # Get the full line containing the chapter heading
            lines = text.split('\n')
            for line in lines:
                if re.search(pattern, line):
                    return line.strip()[:100]  # Limit length
    return None


def clean_text(text: str) -> str:
    """
    Clean extracted text:
    - Remove excessive whitespace
    - Remove page numbers
    - Fix common OCR issues
    """
    # Remove standalone page numbers
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
    
    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove excessive spaces
    text = re.sub(r' {3,}', ' ', text)
    
    # Fix common OCR issues
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)  # camelCase splits
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)  # hyphenation at line breaks
    
    return text.strip()


# =============================================================================
# SEMANTIC CHUNKING
# =============================================================================

def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    min_chunk_size: int = 100
) -> List[str]:
    """
    Split text into semantic chunks.
    
    Strategy:
    1. Split by paragraphs first (\n\n)
    2. If paragraph too long, split by sentences
    3. If sentence too long, split by words
    4. Maintain overlap between chunks for context
    """
    chunks = []
    
    # Split into paragraphs
    paragraphs = text.split('\n\n')
    
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # If adding this paragraph exceeds chunk size
        if len(current_chunk) + len(para) > chunk_size:
            # Save current chunk if it's substantial
            if len(current_chunk) >= min_chunk_size:
                chunks.append(current_chunk.strip())
            
            # Handle paragraph that's too long by itself
            if len(para) > chunk_size:
                # Split by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) > chunk_size:
                        if len(current_chunk) >= min_chunk_size:
                            chunks.append(current_chunk.strip())
                        current_chunk = sent
                    else:
                        current_chunk += " " + sent if current_chunk else sent
            else:
                # Start new chunk with overlap from previous
                if chunks:
                    # Get last ~50 chars from previous chunk
                    overlap = chunks[-1][-chunk_overlap:] if len(chunks[-1]) > chunk_overlap else ""
                    current_chunk = overlap + " " + para
                else:
                    current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para
    
    # Don't forget the last chunk
    if len(current_chunk) >= min_chunk_size:
        chunks.append(current_chunk.strip())
    
    return chunks


# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_pdf(
    file_path: str,
    category: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50
) -> Tuple[BookMetadata, List[TextChunk]]:
    """
    Process a single PDF file into metadata and chunks.
    """
    if not HAS_FITZ:
        raise ImportError("PyMuPDF required: pip install PyMuPDF")
    
    logger.info(f"Processing: {Path(file_path).name}")
    
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.error(f"  Failed to open PDF: {e}")
        raise
    
    # Extract metadata
    title, author = extract_title_author(doc, file_path)
    logger.info(f"  Title: {title}")
    logger.info(f"  Author: {author}")
    
    # Find where content starts (skip front matter)
    content_start = find_content_start(doc)
    logger.info(f"  Skipping {content_start} pages of front matter")
    
    # Create book metadata
    book_meta = BookMetadata(
        title=title,
        author=author,
        category=category,
        file_path=file_path,
        total_pages=len(doc),
        content_start_page=content_start + 1,  # 1-indexed for humans
        extraction_date=datetime.now().isoformat()
    )
    
    # Extract and process pages
    all_chunks = []
    current_chapter = None
    chunk_index = 0
    
    for page_num in range(content_start, len(doc)):
        page = doc[page_num]
        text = page.get_text()
        
        # Skip empty or front matter pages
        is_fm, reason = is_front_matter(text)
        if is_fm:
            logger.debug(f"  Skipping page {page_num + 1}: {reason}")
            continue
        
        # Check for chapter heading
        chapter = extract_chapter(text)
        if chapter:
            current_chapter = chapter
        
        # Clean and chunk the text
        cleaned = clean_text(text)
        page_chunks = chunk_text(cleaned, chunk_size, chunk_overlap)
        
        for chunk_content in page_chunks:
            chunk = TextChunk(
                text=chunk_content,
                book_title=title,
                author=author,
                category=category,
                chapter=current_chapter,
                page_number=page_num + 1,  # 1-indexed
                chunk_index=chunk_index,
                source_file=Path(file_path).name,
                char_count=len(chunk_content),
                word_count=len(chunk_content.split())
            )
            all_chunks.append(chunk)
            chunk_index += 1
    
    # Calculate pages before closing
    total_pages = len(doc)
    content_pages = total_pages - content_start
    doc.close()
    
    logger.info(f"  Extracted {len(all_chunks)} chunks from {content_pages} content pages")
    
    return book_meta, all_chunks


def process_library(
    library_path: str,
    db_path: str,
    collection_name: str = "trading_books",
    batch_size: int = 100
) -> Dict:
    """
    Process all PDFs in the library and store in ChromaDB.
    """
    if not HAS_CHROMA:
        raise ImportError("chromadb required: pip install chromadb")
    if not HAS_EMBEDDINGS:
        raise ImportError("sentence-transformers required")
    
    library = Path(library_path)
    
    # Initialize embedding model
    logger.info("Loading embedding model: all-MiniLM-L6-v2")
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    # Initialize ChromaDB
    logger.info(f"Initializing ChromaDB at: {db_path}")
    client = chromadb.PersistentClient(path=db_path)
    
    # Create or get collection
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )
    
    # Track stats
    stats = {
        'total_books': 0,
        'total_chunks': 0,
        'total_pages': 0,
        'skipped_pages': 0,
        'failed_books': [],
        'by_category': {}
    }
    
    # Find all PDFs organized by category
    for category_dir in library.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith('.'):
            continue
        
        category = category_dir.name
        logger.info(f"\n{'='*60}")
        logger.info(f"Category: {category}")
        logger.info(f"{'='*60}")
        
        stats['by_category'][category] = {'books': 0, 'chunks': 0}
        
        pdf_files = list(category_dir.glob("*.pdf"))
        logger.info(f"Found {len(pdf_files)} PDFs")
        
        for pdf_path in pdf_files:
            try:
                book_meta, chunks = process_pdf(
                    str(pdf_path),
                    category
                )
                
                if not chunks:
                    logger.warning(f"  No chunks extracted, skipping")
                    continue
                
                # Prepare for ChromaDB
                texts = [c.text for c in chunks]
                ids = [f"{Path(pdf_path).stem}_{i}" for i in range(len(chunks))]
                metadatas = [
                    {
                        'book_title': c.book_title,
                        'author': c.author,
                        'category': c.category,
                        'chapter': c.chapter or '',
                        'page_number': c.page_number,
                        'source_file': c.source_file,
                        'word_count': c.word_count
                    }
                    for c in chunks
                ]
                
                # Generate embeddings in batches
                logger.info(f"  Generating embeddings for {len(texts)} chunks...")
                embeddings = embedder.encode(texts, show_progress_bar=False).tolist()
                
                # Add to ChromaDB in batches
                for i in range(0, len(texts), batch_size):
                    batch_end = min(i + batch_size, len(texts))
                    collection.add(
                        documents=texts[i:batch_end],
                        embeddings=embeddings[i:batch_end],
                        metadatas=metadatas[i:batch_end],
                        ids=ids[i:batch_end]
                    )
                
                # Update stats
                stats['total_books'] += 1
                stats['total_chunks'] += len(chunks)
                stats['total_pages'] += book_meta.total_pages
                stats['by_category'][category]['books'] += 1
                stats['by_category'][category]['chunks'] += len(chunks)
                
            except Exception as e:
                logger.error(f"  Failed to process {pdf_path.name}: {e}")
                stats['failed_books'].append({
                    'file': str(pdf_path),
                    'error': str(e)
                })
    
    # Save stats
    stats_file = Path(db_path) / "ingestion_stats.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)
    
    logger.info(f"\n{'='*60}")
    logger.info("INGESTION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Books processed: {stats['total_books']}")
    logger.info(f"Total chunks: {stats['total_chunks']}")
    logger.info(f"Failed: {len(stats['failed_books'])}")
    
    return stats


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest trading books into ChromaDB")
    parser.add_argument("--library", required=True, help="Path to book library")
    parser.add_argument("--db", required=True, help="Path for ChromaDB storage")
    parser.add_argument("--collection", default="trading_books", help="Collection name")
    parser.add_argument("--test", action="store_true", help="Process only first 5 books")
    
    args = parser.parse_args()
    
    # Verify paths
    if not Path(args.library).exists():
        print(f"Error: Library not found at {args.library}")
        exit(1)
    
    # Create DB directory
    Path(args.db).mkdir(parents=True, exist_ok=True)
    
    # Run ingestion
    stats = process_library(
        args.library,
        args.db,
        args.collection
    )
    
    print(f"\nStats saved to: {args.db}/ingestion_stats.json")
