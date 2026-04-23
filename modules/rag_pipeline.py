"""
Module 5: RAG Pipeline (FREE — local embeddings + Groq)
Retrieves relevant chunks and assembles context for the LLM.
"""

import os
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()


def retrieve(query: str, top_k: int = 6, filter_clause_type: Optional[str] = None, filter_source_file: Optional[str] = None) -> List[Dict]:
    """Retrieve top_k semantically similar chunks using local embeddings."""
    from modules.embedder import semantic_search
    return semantic_search(query=query, top_k=top_k, filter_clause_type=filter_clause_type, filter_source_file=filter_source_file)


import streamlit as st

@st.cache_resource
def get_reranker():
    # Disabled: PyTorch CrossEncoder causes fatal macOS thread mutex deadlocks
    # in Streamlit execution loops. Falling back to robust TF-IDF similarity.
    return None

def rerank(query: str, candidates: List[Dict]) -> List[Dict]:
    """
    Rerank candidates. Uses local cross-encoder if available,
    otherwise falls back to similarity score ordering.
    """
    model = get_reranker()
    if model is not None:
        pairs = [(query, c["text"]) for c in candidates]
        try:
            scores = model.predict(pairs)
            for c, score in zip(candidates, scores):
                c["rerank_score"] = float(score)
            return sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        except Exception:
            pass

    # Fallback to similarity
    return sorted(candidates, key=lambda x: x.get("similarity", 0), reverse=True)


def assemble_context(chunks: List[Dict], max_tokens: int = 6000) -> str:
    """Assemble retrieved chunks into a context string with metadata headers."""
    char_budget = max_tokens * 4
    parts = []
    used = 0

    for i, chunk in enumerate(chunks):
        meta = chunk.get("metadata", {})
        header = (f"[Chunk {i+1} | File: {meta.get('source_file','?')} | "
                  f"Page: {meta.get('page_num','?')} | "
                  f"Clause: {meta.get('clause_type','?')} | "
                  f"Risk: {meta.get('risk_level','?')}]")
        block = f"{header}\n{chunk['text']}\n"
        if used + len(block) > char_budget:
            break
        parts.append(block)
        used += len(block)

    return "\n---\n".join(parts)


def rag_retrieve_and_assemble(
    query: str,
    top_k: int = 8,
    rerank_results: bool = True,
    filter_clause_type: Optional[str] = None,
    filter_source_file: Optional[str] = None,
) -> Tuple[str, List[Dict]]:
    """Full RAG pipeline: retrieve → rerank → assemble context."""
    candidates = retrieve(query, top_k=top_k, filter_clause_type=filter_clause_type, filter_source_file=filter_source_file)
    if rerank_results and len(candidates) > 1:
        candidates = rerank(query, candidates)
    context = assemble_context(candidates)
    return context, candidates


if __name__ == "__main__":
    query = "What is the liability cap?"
    context, chunks = rag_retrieve_and_assemble(query, top_k=4)
    print(f"Retrieved {len(chunks)} chunks")
    print(context[:400])
