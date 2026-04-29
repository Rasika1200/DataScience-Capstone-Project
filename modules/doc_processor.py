"""
Module 1: Document Processor
Extracts text from PDF/DOCX contracts, cleans it, and chunks it into
overlapping segments suitable for embedding and topic modelling.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
from docx import Document


@dataclass
class Chunk:
    text: str
    chunk_id: str
    source_file: str
    page_num: int
    char_start: int
    char_end: int
    metadata: dict = field(default_factory=dict)


def extract_text_from_pdf(file_path: str) -> List[dict]:
    """Extract text page-by-page from a PDF using PyMuPDF."""
    pages = []
    doc = fitz.open(file_path)
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        text = _clean_text(text)
        if text.strip():
            pages.append({"page_num": page_num + 1, "text": text})
    doc.close()
    return pages


def extract_text_from_docx(file_path: str) -> List[dict]:
    """Extract text paragraph-by-paragraph from a DOCX file."""
    doc = Document(file_path)
    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    full_text = _clean_text(full_text)
    # Treat entire doc as page 1 for simplicity
    return [{"page_num": 1, "text": full_text}]


def extract_text(file_path: str) -> List[dict]:
    """Auto-detect file type and extract text."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(file_path)
    elif path.suffix.lower() in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")


def _clean_text(text: str) -> str:
    """Remove excessive whitespace and fix common PDF extraction artifacts."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" \n", "\n", text)
    return text.strip()


def chunk_pages(
    pages: List[dict],
    source_file: str,
    chunk_size: int = 500,
    overlap: int = 80,
) -> List[Chunk]:
    """
    Sliding-window chunking over extracted pages.
    Uses word-level splitting so chunks never cut mid-word.
    chunk_size and overlap are in words (not tokens) for simplicity.
    """
    chunks = []
    chunk_idx = 0

    for page in pages:
        words = page["text"].split()
        page_num = page["page_num"]
        start = 0

        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)

            chunk = Chunk(
                text=chunk_text,
                chunk_id=f"{Path(source_file).stem}_p{page_num}_c{chunk_idx}",
                source_file=source_file,
                page_num=page_num,
                char_start=start,
                char_end=end,
            )
            chunks.append(chunk)
            chunk_idx += 1

            if end == len(words):
                break
            start += chunk_size - overlap  # sliding window with overlap

    return chunks


def process_raw_text(text: str, source_file: str = "Webpage_Text", chunk_size: int = 500, overlap: int = 80) -> List[Chunk]:
    """
    Process raw text strings directly, bypassing PDF/DOCX extraction.
    Used for extracting text from the Chrome Extension DOM.
    """
    cleaned_text = _clean_text(text)
    pages = [{"page_num": 1, "text": cleaned_text}]
    return chunk_pages(pages, source_file=source_file, chunk_size=chunk_size, overlap=overlap)


def process_contract(file_path: str, chunk_size: int = 500, overlap: int = 80) -> List[Chunk]:
    """
    End-to-end: extract text from file and return overlapping chunks.
    This is the main entry point used by other modules.
    """
    pages = extract_text(file_path)
    chunks = chunk_pages(pages, source_file=file_path, chunk_size=chunk_size, overlap=overlap)
    return chunks


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python doc_processor.py <path_to_contract.pdf>")
        sys.exit(1)

    path = sys.argv[1]
    result = process_contract(path)
    print(f"Extracted {len(result)} chunks from {path}")
    print("\nFirst chunk preview:")
    print(result[0].text[:300])
