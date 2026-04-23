"""
Module 3: Embedder + Vector Store (FINAL STABLE VERSION)
TF-IDF embeddings — fast, deterministic, no threading issues.
No Streamlit caching → avoids deadlocks.
"""

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import hashlib
import warnings
import numpy as np
import chromadb
import streamlit as st
from typing import List, Dict, Optional
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=RuntimeWarning)

load_dotenv()

CHROMA_DIR = None
COLLECTION_NAME = "contract_chunks_semantic"


# ── SEMANTIC EMBEDDINGS (STREAMLIT CACHED) ────────────────────────────────────
@st.cache_resource
def get_embedding_model():
    from sentence_transformers import SentenceTransformer
    # Using a fast, local semantic embedding model.
    # Cached globally by Streamlit to prevent PyTorch thread deadlocks on Mac.
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model

def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Semantic dense embedding using local huggingface model.
    """
    if not texts:
        return []

    model = get_embedding_model()
    # Setting convert_to_tensor=False outputs numpy arrays safely
    embeddings = model.encode(texts, convert_to_tensor=False)
    
    # SentenceTransformer already normalizes somewhat, but just to be safe
    # we normalize for Cosine Similarity space in ChromaDB
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    return embeddings.tolist()


# ── ChromaDB helpers (NO CACHE) ───────────────────────────────────────────────
@st.cache_resource
def _get_chroma_client():
    if CHROMA_DIR:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        return chromadb.PersistentClient(path=CHROMA_DIR)
    else:
        return chromadb.Client()


def get_collection() -> chromadb.Collection:
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _make_id(chunk_id: str) -> str:
    return hashlib.md5(chunk_id.encode()).hexdigest()


# ── Index ─────────────────────────────────────────────────────────────────────
def clear_collection():
    """Wipes the entire vector store collection to prevent data bleed between contracts."""
    client = _get_chroma_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

def index_chunks(chunks, topic_labels: Optional[List[Dict]] = None, clear_first: bool = True) -> int:
    """Embed and store contract chunks."""
    
    if clear_first:
        clear_collection()

    texts = [c.text for c in chunks]
    print(f"📦 Embedding {len(texts)} chunks...")

    embeddings = embed_texts(texts)

    collection = get_collection()

    ids, metadatas, documents = [], [], []

    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        meta = {
            "source_file": chunk.source_file,
            "page_num": chunk.page_num,
            "chunk_id_original": chunk.chunk_id,
        }

        if topic_labels and i < len(topic_labels):
            label = topic_labels[i]
            meta.update({
                "clause_type": label.get("clause_type", "other"),
                "risk_level": label.get("risk_level", "low"),
                "confidence": str(label.get("confidence", 0.0)),
                "summary": label.get("summary", ""),
            })

        ids.append(_make_id(chunk.chunk_id))
        metadatas.append(meta)
        documents.append(chunk.text)

    # batch insert
    for i in range(0, len(ids), 100):
        collection.upsert(
            ids=ids[i:i+100],
            embeddings=embeddings[i:i+100],
            metadatas=metadatas[i:i+100],
            documents=documents[i:i+100],
        )

    print(f"✅ Indexed {len(ids)} chunks into ChromaDB")
    return len(ids)


# ── Search ────────────────────────────────────────────────────────────────────
def semantic_search(
    query: str,
    top_k: int = 5,
    filter_clause_type: Optional[str] = None,
    filter_risk_level: Optional[str] = None,
    filter_source_file: Optional[str] = None,
) -> List[Dict]:

    if not query.strip():
        return []

    query_embedding = embed_texts([query])[0]
    collection = get_collection()

    where = {}
    if filter_clause_type:
        where["clause_type"] = filter_clause_type
    if filter_risk_level:
        where["risk_level"] = filter_risk_level
    if filter_source_file:
        where["source_file"] = filter_source_file

    kwargs = dict(
        query_embeddings=[query_embedding],
        n_results=min(top_k, max(collection.count(), 1)),
        include=["documents", "metadatas", "distances"],
    )

    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    return [
        {
            "text": doc,
            "metadata": meta,
            "similarity": round(1 - dist, 4),
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


# ── Stats ─────────────────────────────────────────────────────────────────────
def get_collection_stats() -> Dict:
    return {
        "total_chunks": get_collection().count(),
        "collection_name": COLLECTION_NAME,
        "persist_dir": CHROMA_DIR,
    }