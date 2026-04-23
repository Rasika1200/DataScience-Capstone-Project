"""
Module 4: Clause Matcher (OPTIMIZED — fast vectorized similarity)
"""

import numpy as np
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# -----------------------
# CLAUSE DEFINITIONS
# -----------------------

CANONICAL_CLAUSE_DESCRIPTIONS = {
    "liability": "The party is responsible for damages, losses, or harm caused to the other party.",
    "indemnification": "One party agrees to compensate and defend the other party against claims and losses.",
    "limitation of liability": "The maximum financial exposure is capped. No liability for indirect damages.",
    "termination": "The agreement may be ended under specified conditions.",
    "payment terms": "Invoices must be paid within a specified number of days.",
    "confidentiality / NDA": "Confidential information must not be disclosed to third parties.",
    "intellectual property": "Ownership of inventions, patents, copyrights, and trade secrets.",
    "governing law": "The agreement is governed by a specific jurisdiction.",
    "dispute resolution": "Disputes resolved via arbitration, mediation, or litigation.",
    "force majeure": "No liability for failure due to uncontrollable events.",
    "warranty": "Guarantees about quality and performance.",
    "non-compete / non-solicitation": "Restriction on competition or hiring.",
    "assignment": "Rights cannot be transferred without consent.",
    "other": "General clause.",
}

CLAUSE_RISK_WEIGHTS = {
    "liability": 0.9, "indemnification": 0.85, "limitation of liability": 0.8,
    "termination": 0.7, "payment terms": 0.5, "confidentiality / NDA": 0.65,
    "intellectual property": 0.75, "governing law": 0.4, "dispute resolution": 0.6,
    "force majeure": 0.5, "warranty": 0.55, "non-compete / non-solicitation": 0.7,
    "assignment": 0.45, "other": 0.2,
}

_cached_canonical_embeddings: Optional[Dict[str, List[float]]] = None


# -----------------------
# EMBEDDINGS (CACHED)
# -----------------------

def get_canonical_embeddings():
    global _cached_canonical_embeddings
    if _cached_canonical_embeddings is not None:
        return _cached_canonical_embeddings

    from modules.embedder import embed_texts

    clause_names = list(CANONICAL_CLAUSE_DESCRIPTIONS.keys())
    descriptions = list(CANONICAL_CLAUSE_DESCRIPTIONS.values())

    print("Embedding canonical clauses (one-time)...")
    embeddings = embed_texts(descriptions)

    _cached_canonical_embeddings = {
        "names": clause_names,
        "matrix": np.array(embeddings)
    }

    return _cached_canonical_embeddings


# -----------------------
# MAIN MATCHING FUNCTION (FAST)
# -----------------------

def match_chunks(chunk_texts: List[str], threshold: float = 0.25) -> List[Dict]:
    from modules.embedder import embed_texts

    print(f"Matching {len(chunk_texts)} chunks (FAST vectorized)...")

    # Step 1: embeddings
    chunk_embeddings = embed_texts(chunk_texts)
    canonical = get_canonical_embeddings()

    clause_names = canonical["names"]
    clause_matrix = canonical["matrix"]

    # Step 2: cosine similarity (vectorized)
    dot_product = np.dot(chunk_embeddings, clause_matrix.T)

    chunk_norms = np.linalg.norm(chunk_embeddings, axis=1, keepdims=True)
    clause_norms = np.linalg.norm(clause_matrix, axis=1)

    similarity_matrix = dot_product / (chunk_norms * clause_norms)

    # Step 3: build results
    results = []

    for i, text in enumerate(chunk_texts):
        scores = similarity_matrix[i]

        # top 3 matches
        top_indices = np.argsort(scores)[::-1][:3]
        top_matches = [(clause_names[j], float(scores[j])) for j in top_indices]

        best_clause, best_score = top_matches[0]

        if best_score < threshold:
            best_clause, best_score = "other", 0.0

        base_risk = CLAUSE_RISK_WEIGHTS.get(best_clause, 0.2)
        risk_score = round(base_risk * best_score, 3)

        risk_level = (
            "high" if risk_score >= 0.6
            else "medium" if risk_score >= 0.35
            else "low"
        )

        results.append({
            "text": text,
            "matched_clause": best_clause,
            "match_score": round(best_score, 4),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "top_3_matches": [
                {"clause": c, "score": round(s, 4)} for c, s in top_matches
            ],
            "chunk_embedding": chunk_embeddings[i],
        })

    return results


# -----------------------
# UTIL FUNCTIONS
# -----------------------

def get_high_risk_clauses(match_results: List[Dict]) -> List[Dict]:
    return sorted(
        [r for r in match_results if r["risk_level"] == "high"],
        key=lambda x: x["risk_score"], reverse=True
    )


def summarize_risk_profile(match_results: List[Dict]) -> Dict:
    from collections import Counter

    clause_counts = Counter(r["matched_clause"] for r in match_results)
    risk_counts = Counter(r["risk_level"] for r in match_results)

    avg_risk = np.mean([r["risk_score"] for r in match_results]) if match_results else 0.0

    return {
        "total_clauses": len(match_results),
        "clause_type_distribution": dict(clause_counts),
        "risk_distribution": dict(risk_counts),
        "average_risk_score": round(float(avg_risk), 3),
        "high_risk_count": risk_counts.get("high", 0),
    }


# -----------------------
# TEST
# -----------------------

if __name__ == "__main__":
    samples = [
        "In no event shall either party be liable for indirect damages.",
        "Either party may terminate with notice.",
        "Confidential information must not be disclosed.",
        "Payment is due within 30 days.",
    ]

    results = match_chunks(samples)

    for r in results:
        print(f"\n{r['text']}")
        print(f"-> {r['matched_clause']} | score={r['match_score']} | risk={r['risk_level']}")