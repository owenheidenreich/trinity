#!/usr/bin/env python3
"""
Test the book ingestion pipeline on a single PDF.

Usage:
    python test_ingestion.py /path/to/book.pdf
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pickles.ingest_books import (
    process_pdf,
    is_front_matter,
    find_content_start,
    clean_text,
    chunk_text,
    HAS_FITZ
)


def test_single_pdf(pdf_path: str):
    """Test ingestion on a single PDF."""
    
    if not HAS_FITZ:
        print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF")
        return
    
    import fitz
    
    print(f"\n{'='*60}")
    print(f"Testing: {Path(pdf_path).name}")
    print(f"{'='*60}\n")
    
    # Open PDF
    doc = fitz.open(pdf_path)
    print(f"Total pages: {len(doc)}")
    
    # Find content start
    content_start = find_content_start(doc)
    print(f"Content starts at page: {content_start + 1}")
    
    # Show what we're skipping
    print(f"\n--- Front Matter (pages 1-{content_start}) ---")
    for i in range(min(content_start, 5)):  # Show first 5 skipped pages
        page = doc[i]
        text = page.get_text()[:200].replace('\n', ' ')
        is_fm, reason = is_front_matter(page.get_text())
        print(f"  Page {i+1}: {reason} | {text}...")
    
    # Show first content page
    if content_start < len(doc):
        print(f"\n--- First Content Page (page {content_start + 1}) ---")
        text = doc[content_start].get_text()[:500]
        print(text)
    
    # Process and show chunks
    print(f"\n--- Processing Full Book ---")
    category = Path(pdf_path).parent.name
    book_meta, chunks = process_pdf(pdf_path, category)
    
    print(f"\nBook Metadata:")
    print(f"  Title: {book_meta.title}")
    print(f"  Author: {book_meta.author}")
    print(f"  Category: {book_meta.category}")
    print(f"  Total Pages: {book_meta.total_pages}")
    print(f"  Content Start: Page {book_meta.content_start_page}")
    
    print(f"\nChunking Results:")
    print(f"  Total Chunks: {len(chunks)}")
    if chunks:
        avg_words = sum(c.word_count for c in chunks) / len(chunks)
        print(f"  Avg Words/Chunk: {avg_words:.1f}")
        
        print(f"\n--- Sample Chunks ---")
        for i, chunk in enumerate(chunks[:3]):  # Show first 3 chunks
            print(f"\nChunk {i+1} (page {chunk.page_number}, {chunk.word_count} words):")
            print(f"  Chapter: {chunk.chapter or 'N/A'}")
            print(f"  Text: {chunk.text[:200]}...")
    
    doc.close()
    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_ingestion.py /path/to/book.pdf")
        print("\nExample:")
        print('  python test_ingestion.py "/Users/.../The Library/Options/Get Rich With Options.pdf"')
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)
    
    test_single_pdf(pdf_path)
