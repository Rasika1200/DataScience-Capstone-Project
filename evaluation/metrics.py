"""
Evaluation Module
Computes all metrics your professor will ask about:
  1. Clause extraction F1 (precision/recall against CUAD ground truth)
  2. Summarization quality (ROUGE-L, BERTScore)
  3. Hallucination rate (LLM self-check)
  4. Human agreement rate (from HITL SQLite log)

Run: python evaluation/run_eval.py
"""

import os
import json
import sqlite3
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv

load_dotenv()


# ── 1. Clause extraction F1 ─────────────────────────────────────────────────
def compute_extraction_f1(
    predicted_clauses: List[str],
    ground_truth_clauses: List[str],
) -> Dict:
    """
    Compute precision, recall, and F1 for clause type prediction.
    predicted_clauses: list of predicted clause type strings
    ground_truth_clauses: list of true clause type strings (from CUAD labels)
    """
    pred_set = set(c.lower() for c in predicted_clauses)
    true_set = set(c.lower() for c in ground_truth_clauses)

    if not pred_set and not true_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    tp = len(pred_set & true_set)
    fp = len(pred_set - true_set)
    fn = len(true_set - pred_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
    }


def evaluate_on_cuad(cuad_sample_path: str, predictions: List[Dict]) -> Dict:
    """
    Evaluate clause extraction against a CUAD dataset sample.
    cuad_sample_path: path to a JSON file with [{contract_id, clause_types: [...]}]
    predictions: [{contract_id, predicted_clause_types: [...]}]
    """
    with open(cuad_sample_path) as f:
        ground_truths = {item["contract_id"]: item["clause_types"] for item in json.load(f)}

    all_metrics = []
    for pred in predictions:
        cid = pred["contract_id"]
        if cid not in ground_truths:
            continue
        metrics = compute_extraction_f1(
            pred["predicted_clause_types"],
            ground_truths[cid],
        )
        metrics["contract_id"] = cid
        all_metrics.append(metrics)

    if not all_metrics:
        return {"error": "No matching contract IDs found"}

    df = pd.DataFrame(all_metrics)
    return {
        "mean_precision": round(df["precision"].mean(), 4),
        "mean_recall": round(df["recall"].mean(), 4),
        "mean_f1": round(df["f1"].mean(), 4),
        "n_contracts": len(all_metrics),
        "per_contract": all_metrics,
    }


# ── 2. Summarization quality (ROUGE-L, BERTScore) ───────────────────────────
def compute_rouge_l(predictions: List[str], references: List[str]) -> Dict:
    """
    Compute ROUGE-L between predicted summaries and reference summaries.
    Requires: pip install rouge-score
    """
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
        scores = [scorer.score(ref, pred)["rougeL"].fmeasure
                  for pred, ref in zip(predictions, references)]
        return {
            "rouge_l_mean": round(np.mean(scores), 4),
            "rouge_l_std": round(np.std(scores), 4),
            "rouge_l_min": round(np.min(scores), 4),
            "rouge_l_max": round(np.max(scores), 4),
        }
    except ImportError:
        return {"error": "Install rouge-score: pip install rouge-score"}


def compute_bertscore(predictions: List[str], references: List[str]) -> Dict:
    """
    Compute BERTScore F1 between predictions and references.
    Requires: pip install bert-score
    """
    try:
        from bert_score import score as bert_score
        P, R, F1 = bert_score(predictions, references, lang="en", rescale_with_baseline=True)
        return {
            "bertscore_f1_mean": round(F1.mean().item(), 4),
            "bertscore_precision_mean": round(P.mean().item(), 4),
            "bertscore_recall_mean": round(R.mean().item(), 4),
        }
    except ImportError:
        return {"error": "Install bert-score: pip install bert-score"}


# ── 3. Hallucination rate ────────────────────────────────────────────────────
def check_hallucination_rate(
    qa_pairs: List[Dict],
    contract_contexts: List[str],
) -> Dict:
    """
    Use GPT to verify if each answer is grounded in the provided context.
    qa_pairs: [{"question": "...", "answer": "..."}]
    contract_contexts: list of context strings used to generate each answer

    Returns hallucination rate (fraction of answers NOT grounded in context).
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    hallucinated = 0
    results = []

    for qa, context in zip(qa_pairs, contract_contexts):
        prompt = f"""Given this contract context:
---
{context[:2000]}
---

Is the following answer FULLY supported by the context above?
Question: {qa['question']}
Answer: {qa['answer']}

Reply with ONLY: {{"grounded": true}} or {{"grounded": false, "reason": "brief explanation"}}"""

        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        results.append({
            "question": qa["question"],
            "answer": qa["answer"],
            "grounded": result.get("grounded", False),
            "reason": result.get("reason", ""),
        })
        if not result.get("grounded", True):
            hallucinated += 1

    return {
        "total_qa_pairs": len(qa_pairs),
        "hallucinated": hallucinated,
        "hallucination_rate": round(hallucinated / max(len(qa_pairs), 1), 4),
        "grounded_rate": round(1 - hallucinated / max(len(qa_pairs), 1), 4),
        "details": results,
    }


# ── 4. Human agreement rate (from SQLite) ───────────────────────────────────
def compute_human_agreement_rate(db_path: Optional[str] = None) -> Dict:
    """
    Compute the rate at which human reviewers accepted clauses without edits.
    Reads from the HITL SQLite feedback database.
    """
    if db_path is None:
        db_path = os.getenv("SQLITE_DB_PATH", "./data/feedback.db")

    if not os.path.exists(db_path):
        return {"error": f"No feedback database found at {db_path}"}

    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM hitl_feedback", conn)
    conn.close()

    if df.empty:
        return {"error": "No HITL feedback recorded yet"}

    total = len(df)
    accepted = len(df[df["decision"] == "accepted"])
    edited = len(df[df["decision"] == "edited"])
    rejected = len(df[df["decision"] == "rejected"])
    pending = len(df[df["decision"] == "pending"])

    # Agreement = accepted without any edit
    agreement_rate = accepted / (total - pending) if (total - pending) > 0 else 0.0

    per_clause = df.groupby("clause_type")["decision"].value_counts().unstack(fill_value=0)

    return {
        "total_reviewed": total - pending,
        "accepted": accepted,
        "edited": edited,
        "rejected": rejected,
        "human_agreement_rate": round(agreement_rate, 4),
        "per_clause_breakdown": per_clause.to_dict(),
    }


# ── 5. Full evaluation report ────────────────────────────────────────────────
def generate_eval_report(output_path: str = "./evaluation/eval_report.json") -> Dict:
    """
    Combine all metrics into a single evaluation report.
    Used for the capstone write-up and demo.
    """
    report = {
        "human_agreement": compute_human_agreement_rate(),
    }
    print(json.dumps(report, indent=2))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to {output_path}")
    return report


if __name__ == "__main__":
    generate_eval_report()
