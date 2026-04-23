"""
Module 2: Topic Modeller (FREE stack)
- BERTopic: local, uses sentence-transformers (no API)
- LLM labelling: Groq free API (Llama 3.1)
- Zero-shot classification: Groq free API
"""

import os
import json
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

CLAUSE_TAXONOMY = [
    "liability",
    "indemnification",
    "limitation of liability",
    "termination",
    "payment terms",
    "confidentiality / NDA",
    "intellectual property",
    "governing law",
    "dispute resolution",
    "force majeure",
    "warranty",
    "non-compete / non-solicitation",
    "assignment",
    "other",
]


def get_groq_client():
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Get free key at https://console.groq.com")
    return Groq(api_key=api_key)


# ── BERTopic (fully local, no API) ───────────────────────────────────────────
def run_bertopic(texts: List[str], n_topics: int = 10) -> Dict:
    """Run BERTopic locally using sentence-transformers. Completely free."""
    try:
        from bertopic import BERTopic
        from sentence_transformers import SentenceTransformer
        from umap import UMAP
        from hdbscan import HDBSCAN

        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0,
                          metric="cosine", random_state=42)
        hdbscan_model = HDBSCAN(min_cluster_size=5, metric="euclidean",
                                cluster_selection_method="eom", prediction_data=True)

        topic_model = BERTopic(
            embedding_model=embedding_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            nr_topics=n_topics,
            verbose=False,
        )

        topics, probs = topic_model.fit_transform(texts)
        return {
            "topics_per_chunk": topics,
            "topic_info": topic_model.get_topic_info().to_dict(orient="records"),
            "model": topic_model,
        }
    except ImportError as e:
        raise ImportError(f"Run: pip install bertopic umap-learn hdbscan\n{e}")


# ── LLM zero-shot classification via Groq ────────────────────────────────────
def classify_chunk_llm(chunk_text: str, client=None) -> Dict:
    """Classify a single chunk using Groq Llama. Free API."""
    if client is None:
        client = get_groq_client()

    taxonomy_str = "\n".join(f"- {c}" for c in CLAUSE_TAXONOMY)
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    prompt = f"""You are a contract analysis expert. Classify this contract excerpt.

Clause taxonomy:
{taxonomy_str}

Contract excerpt:
\"\"\"{chunk_text[:800]}\"\"\"

Respond ONLY with valid JSON (no backticks, no extra text):
{{"clause_type": "<one from taxonomy>", "confidence": 0.0, "risk_level": "<low|medium|high>", "summary": "<one sentence>", "key_phrases": ["phrase1", "phrase2"]}}"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=200,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[start:end])


def classify_chunks_llm(chunks_texts: List[str]) -> List[Dict]:
    """Classify all chunks. Batches with progress output."""
    client = get_groq_client()
    results = []

    for i, text in enumerate(chunks_texts):
        try:
            result = classify_chunk_llm(text, client=client)
        except Exception as e:
            result = {
                "clause_type": "other",
                "confidence": 0.0,
                "risk_level": "low",
                "summary": f"Classification failed: {e}",
                "key_phrases": [],
            }
        results.append(result)
        if (i + 1) % 10 == 0:
            print(f"  Classified {i+1}/{len(chunks_texts)} chunks...")

    return results


# ── Label BERTopic topics with Groq ─────────────────────────────────────────
def label_topics_with_llm(topic_model, client=None) -> Dict[int, str]:
    """Assign clause taxonomy labels to BERTopic clusters using Groq."""
    if client is None:
        client = get_groq_client()

    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    taxonomy_str = ", ".join(CLAUSE_TAXONOMY)
    topic_labels = {}

    for topic_id in topic_model.get_topics():
        if topic_id == -1:
            topic_labels[-1] = "noise / unclassified"
            continue

        top_words = [w for w, _ in topic_model.get_topic(topic_id)[:10]]

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content":
                f"Keywords from a contract clause cluster: {', '.join(top_words)}\n"
                f"Pick the SINGLE best matching clause type from: {taxonomy_str}\n"
                f"Reply with just the clause type name, nothing else."}],
            temperature=0.0,
            max_tokens=20,
        )
        label = response.choices[0].message.content.strip().lower()
        topic_labels[topic_id] = label if label in CLAUSE_TAXONOMY else "other"

    return topic_labels


if __name__ == "__main__":
    samples = [
        "The Company shall not be liable for any indirect or consequential damages.",
        "Either party may terminate with 30 days written notice.",
        "All payments are due within 45 days of invoice receipt.",
        "The receiving party shall keep all information strictly confidential.",
    ]
    print("Testing LLM classification with Groq...")
    results = classify_chunks_llm(samples)
    for text, r in zip(samples, results):
        print(f"\n{text[:60]}...")
        print(f"  -> {r['clause_type']} | risk={r['risk_level']} | conf={r['confidence']:.2f}")
