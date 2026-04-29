"""
Module 6: LLM Engine (Groq — FINAL STABLE VERSION)
"""

import os
import json
import time
import re
from typing import List, Optional, Dict
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

import requests
from types import SimpleNamespace

def call_llm(prompt, json_mode=False):
    from groq import Groq
    import requests
    
    # 1. Try Groq (Cloud API) - Blazing fast, uses 0% of your RAM
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        try:
            client = Groq(api_key=api_key)
            model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
                
            response = client.chat.completions.create(**kwargs)
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e).lower()
            if "request limit" in err or "429" in err or "rate limit" in err or "tokens" in err:
                print("⚡️ Groq rate limit reached! Falling back to offline local Olama AI...")
            else:
                print(f"⚠️ Groq error ({e}). Falling back to local offline Ollama...")

    # 2. Local Fallback (Ollama) - Lightweight model to prevent freezing
    # We use llama3.2 (3B model) or llama3.2:1b (1B model) instead of 8B!
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "llama3.2", 
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 8192}
        }
        if json_mode:
            payload["format"] = "json"

        response = requests.post(url, json=payload, timeout=60)
        
        # If the model isn't downloaded, Ollama will return a 404
        if response.status_code == 404 or "model 'llama3.2' not found" in response.text:
            return "⚠️ Groq is rate-limited, and you don't have the lightweight Llama 3.2 model. Run this in your terminal: `ollama pull llama3.2`"
            
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return "⚠️ Groq is rate-limited, and Ollama is not running. Open Ollama app to run offline."
    except Exception as e:
        print("Ollama fallback error:", e)
        return f"⚠️ Model error: {e}"


# ── Safe JSON parsing ─────────────────────────────────────────────────────────
def _parse_json(raw: str) -> dict:
    """Robustly parse JSON from LLM output, handling markdown blocks."""
    text = raw.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```"):
        # Match ```json ... ``` or just ``` ... ```
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
    
    # Find the first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except Exception as e:
            print(f"JSON partial parse error: {e}")
            pass

    # Final fallback attempt
    try:
        return json.loads(text)
    except Exception:
        raise ValueError(f"Could not parse JSON from: {raw[:100]}...")


# ── Schemas ───────────────────────────────────────────────────────────────────
class ExtractedClause(BaseModel):
    clause_type: str
    extracted_text: str
    summary: str
    risk_level: str
    risk_explanation: str
    page_reference: Optional[str] = None
    confidence: float


class ContractAnalysis(BaseModel):
    contract_name: str
    overall_risk_level: str
    executive_summary: str
    completeness_assessment: Optional[str] = None
    risk_assessment: Optional[str] = None
    risk_sources: List[str] = []
    readability_assessment: Optional[str] = None
    fairness_summary: Optional[str] = None
    fairness_details: Optional[str] = None
    fairness_sources: List[str] = []
    clauses: List[ExtractedClause]
    red_flags: List[str]
    missing_clauses: List[str]


class ChatAnswer(BaseModel):
    answer: str
    sources: List[str]
    confidence: float
    caveat: Optional[str] = None


# ── Document Verification ───────────────────────────────────────────────────────
def verify_document_type(text: str):
    prompt = f"""
    You are an AI document classifier. Analyze the text of the document provided below.
    Determine if this text represents a legal contract, agreement, terms of service, NDA, legal covenant, or formal exhibit.
    If it is just a software manual, an installation guide, a menu, a resume, a novel, or a random unstructured document, mark it as false.
    
    Document text:
    {text[:4000]}
    
    Return strictly valid JSON in this exact structure:
    {{"is_contract": true or false, "reason": "A 1-sentence explanation of what the document actually appears to be."}}
    """
    try:
        result = call_llm(prompt, json_mode=True)
        data = _parse_json(result)
        return {
            "is_contract": data.get("is_contract", True),
            "reason": data.get("reason", "Analysis passed.")
        }
    except Exception as e:
        print("Verification failed, assuming it is a contract:", e)
        return {"is_contract": True, "reason": "Verification bypassed due to error."}

# ── Clause extraction (SAFE) ───────────────────────────────────────────────────
def extract_clauses(text, contract_name="Contract"):
    prompt = f"""
    Act as an expert AI Contract Reviewer. Extract the 3 to 5 most critical clauses from this document text.
    Disclaimer: You are a technical analysis tool, not a lawyer. You do not provide legal advice.
    For each clause, provide:
    - clause_type (e.g. Liability, Termination, Payment, Confidentiality, IP)
    - summary (a concise 1-sentence summary of the clause's effect)
    - risk_level (low, medium, or high)
    - extracted_text (the actual verbatim phrase or sentence from the text)
    - risk_explanation (1 brief sentence explaining why it is this risk level)
    - confidence_score (a float from 0.0 to 1.0 indicating your certainty in this extraction)

    Also, provide 5 short assessments of the entire document:
    - completeness_assessment: Is the document missing standard protections?
    - risk_assessment: What is the biggest overall risk? (1 concise sentence, under 15 words)
    - risk_sources: A list of 1-3 section names or clause titles that are the source of this risk (e.g. ["Section 2", "Confidentiality"]).
    - readability_assessment: Is the language clear or complex?
    - fairness_summary: A short, 3-to-6 word label stating who the document favors (e.g. 'Favors Twitter\\'s board and management', 'Document appears board-favorable', or 'Balanced').
    - fairness_details: A 1-2 sentence explanation of why it favors them, written in clear, neutral, and cautious terms. Do not make strong legal conclusions.
    - fairness_sources: A list of 1-3 section names or clause titles that are the source of this fairness assessment.

    Document Text:
    {text}

    Return strictly valid JSON in this exact structure:
    {{"executive_summary": "...", "completeness_assessment": "...", "risk_assessment": "...", "risk_sources": ["..."], "readability_assessment": "...", "fairness_summary": "...", "fairness_details": "...", "fairness_sources": ["..."], "red_flags": ["Optional array of critical legal issues"], "clauses": [{{"clause_type": "...", "summary": "...", "risk_level": "low/medium/high", "extracted_text": "...", "risk_explanation": "...", "confidence_score": 0.9}}]}}
    """

    try:
        result = call_llm(prompt, json_mode=True)
        data = _parse_json(result)
        
        parsed_clauses = []
        for c in data.get("clauses", []):
            conf = c.get("confidence_score", 0.85)
            if not isinstance(conf, (int, float)):
                conf = 0.85
            parsed_clauses.append(ExtractedClause(
                clause_type=c.get("clause_type", "General").lower(),
                confidence=float(conf),
                summary=c.get("summary", "No summary provided"),
                risk_level=c.get("risk_level", "medium").lower(),
                risk_explanation=c.get("risk_explanation", ""),
                extracted_text=c.get("extracted_text", "")
            ))
            
        # Safely filter out LLM hallucinated empty flags like "None"
        raw_flags = data.get("red_flags", [])
        actual_red_flags = [
            f for f in raw_flags 
            if f.strip().lower() not in ["none", "none.", "n/a", "no", "no red flags", "none identified", "null", "no red flags identified.", "nothing", "nothing flagged"]
        ]

        high_count = sum(1 for c in parsed_clauses if c.risk_level == "high")
        med_count = sum(1 for c in parsed_clauses if c.risk_level == "medium")
            
        # Determine overall system risk dynamically (Calibrated threshold)
        overall_risk_level = "low"
        
        # Check if any red flags are critically severe based on business logic
        has_critical_flags = any(
            any(w in f.lower() for w in ["missing", "failure", "breach", "liability", "indemnif", "cap", "critical"])
            for f in actual_red_flags
        )
        
        # High Risk: Critical flags present or multiple high-risk clauses
        if has_critical_flags or high_count >= 2:
            overall_risk_level = "high"
        # Medium Risk: Any minor red flags, 1 high-risk clause, or multiple medium-risk clauses
        elif actual_red_flags or high_count >= 1 or med_count >= 2:
            overall_risk_level = "medium"

        return ContractAnalysis(
            contract_name=contract_name,
            overall_risk_level=overall_risk_level,
            executive_summary=data.get("executive_summary", "Contract analysis complete."),
            completeness_assessment=data.get("completeness_assessment", "Standard protections included."),
            risk_assessment=data.get("risk_assessment", "Standard obligations."),
            risk_sources=data.get("risk_sources", []),
            readability_assessment=data.get("readability_assessment", "Standard legal language."),
            fairness_summary=data.get("fairness_summary", "Balanced"),
            fairness_details=data.get("fairness_details", "Balanced obligations."),
            fairness_sources=data.get("fairness_sources", []),
            red_flags=actual_red_flags,
            missing_clauses=[],
            clauses=parsed_clauses
        )
    except Exception as e:
        print("Intelligent extraction failed, using fallback:", e)
        # Fallback if the AI fails
        clauses = [
            ExtractedClause(
                clause_type="general clause",
                confidence=0.8,
                summary="Fallback extraction.",
                risk_level="medium",
                risk_explanation="Generated using intelligent model extraction.",
                extracted_text="Extraction failed structure parsing."
            )
        ]
        return ContractAnalysis(
            contract_name=contract_name,
            overall_risk_level="medium",
            executive_summary="Fallback summary.",
            completeness_assessment="Extraction failed; cannot determine completeness.",
            risk_assessment="Extraction failed; fallback risk is medium.",
            readability_assessment="Extraction failed; cannot assess readability.",
            fairness_summary="Extraction failed",
            fairness_details="Extraction failed; cannot assess fairness.",
            red_flags=[],
            missing_clauses=[],
            clauses=clauses
        )

# ── Q&A ───────────────────────────────────────────────────────────────────────
def answer_question(question, context, chat_history, chunks_used=None):

    prompt = f"""
    You are a highly helpful, extremely user-friendly AI Contract Reviewer helping an everyday person understand their document.
    DISCLAIMER: You are a software tool, not a lawyer. You do not provide legal advice.
    Based ONLY on the context below, answer the user's question directly.
    - strictly NO repeating or continuing the user's question. Start your response immediately with the answer.
    - Format lists or multiple items using bullet points for readability.
    - NEVER use the word "you" or "your" (e.g. "You will get paid"). Instead, use the formal role from the document (e.g. "the Executive", "the Employee", "the Client").
    - strictly NO legal jargon. Instead of "Indemnification", say "Protecting from lawsuits".
    - If it's a yes/no question, strictly start your answer with a clear "Yes." or "No.".
    - If the context does NOT explicitly contain the answer, do not guess! You MUST firmly state: "The document does not specify."
    
    Context:
    {context}

    Question:
    {question}
    """

    result = call_llm(prompt)

    confidence = 0.5
    sources = []
    caveat = None
    
    if chunks_used:
        similarities = [float(c.get("similarity", 0.0)) for c in chunks_used if "similarity" in c]
        if similarities:
            confidence = max(similarities)
            
        for c in chunks_used[:3]:
            ct = c.get("metadata", {}).get("clause_type")
            if not ct or ct.lower() == "other":
                ct = "Document Section"
            if ct.title() not in sources:
                sources.append(ct.title())

    if "docs not specify" in result.lower() or "does not specify" in result.lower():
        confidence = 0.3
        caveat = "The contract text provided likely does not contain this information."

    return ChatAnswer(
        answer=result,
        confidence=confidence,
        sources=sources,
        caveat=caveat
    )

# ── Dynamic Q&A ───────────────────────────────────────────────────────────────
def generate_dynamic_questions(summary: str) -> List[str]:
    prompt = f"""
    You are an AI document analyst helping a regular person. Based ONLY on the document text, generate exactly 3 simple, important questions a LAYMAN (someone not a lawyer) would ask.
    
    CRITICAL RULES: 
    1. LAYMAN LANGUAGE: Use plain English (e.g., "Can I cancel this?", "When do I get paid?").
    2. PRACTICAL & SHORT: Focus on money, dates, and how to get out. Keep questions under 12 words.
    3. MIXED PHRASING: Include a mix of simple questions and one professional phrasing (e.g., "What confidential information is protected?").
    4. SPECIFIC: Don't be generic. If it's a rental, ask about "deposit".
    
    Document Text:
    {summary}
    
    Return EXACTLY 3 layman questions in valid JSON:
    {{"questions": ["Question 1", "Question 2", "Question 3"]}}
    """
    
    try:
        result = call_llm(prompt, json_mode=True)
        data = _parse_json(result)
        return data.get("questions", [])[:3]
    except Exception as e:
        print("Failed to generate dynamic questions via Groq:", e)
        return []

# ── Voice helper ──────────────────────────────────────────────────────────────
def answer_for_voice(answer: ChatAnswer) -> str:
    text = answer.answer
    if answer.caveat:
        text += f" Note: {answer.caveat}"
    if answer.sources:
        text += f" Based on {', '.join(answer.sources[:2])}."
    return text