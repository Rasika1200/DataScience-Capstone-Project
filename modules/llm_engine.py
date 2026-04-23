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
    text = raw.strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    raise ValueError("Could not parse JSON")


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
        import json
        data = json.loads(result)
        return dict(
            is_contract=data.get("is_contract", True),
            reason=data.get("reason", "Analysis passed.")
        )
    except Exception as e:
        print("Verification failed, assuming it is a contract:", e)
        return {"is_contract": True, "reason": "Verification bypassed due to error."}

# ── Clause extraction (SAFE) ───────────────────────────────────────────────────
def extract_clauses(text, contract_name="Contract"):
    prompt = f"""
    Act as an expert legal reviewer. Extract the 3 to 5 most critical clauses from this contract text.
    For each clause, provide:
    - clause_type (e.g. Liability, Termination, Payment, Confidentiality, IP)
    - summary (a concise 1-sentence summary of the clause's effect)
    - risk_level (low, medium, or high)
    - extracted_text (the actual verbatim phrase or sentence from the text)
    - risk_explanation (1 brief sentence explaining why it is this risk level)
    - confidence_score (a float from 0.0 to 1.0 indicating your certainty in this extraction)

    Contract Text:
    {text}

    Return strictly valid JSON in this exact structure:
    {{"executive_summary": "...", "red_flags": ["Optional array of critical legal issues"], "clauses": [{{"clause_type": "...", "summary": "...", "risk_level": "low/medium/high", "extracted_text": "...", "risk_explanation": "...", "confidence_score": 0.9}}]}}
    """

    try:
        result = call_llm(prompt, json_mode=True)
        data = json.loads(result)
        
        parsed_clauses = []
        for c in data.get("clauses", []):
            conf = c.get("confidence_score", 0.85)
            if not isinstance(conf, (int, float)):
                conf = 0.85
            parsed_clauses.append(SimpleNamespace(
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
        
        # High overall risk: Has actual red flags, or 3+ high-risk clauses.
        if actual_red_flags or high_count >= 3:
            overall_risk_level = "high"
        # Medium overall risk: Has 1-2 high-risk clause, or 2+ medium-risk clauses.
        elif high_count >= 1 or med_count >= 2:
            overall_risk_level = "medium"
        elif med_count == 1:
            overall_risk_level = "low" # Single medium risk is often standard

        return SimpleNamespace(
            contract_name=contract_name,
            overall_risk_level=overall_risk_level,
            executive_summary=data.get("executive_summary", "Contract analysis complete."),
            red_flags=actual_red_flags,
            missing_clauses=[],
            clauses=parsed_clauses
        )
    except Exception as e:
        print("Intelligent extraction failed, using fallback:", e)
        # Fallback if the AI fails
        clauses = [
            SimpleNamespace(
                clause_type="general clause",
                confidence=0.8,
                summary="Fallback extraction.",
                risk_level="medium",
                risk_explanation="Generated using intelligent model extraction.",
                extracted_text="Extraction failed structure parsing."
            )
        ]
        return SimpleNamespace(
            contract_name=contract_name,
            overall_risk_level="medium",
            executive_summary="Fallback summary.",
            red_flags=[],
            missing_clauses=[],
            clauses=clauses
        )

# ── Q&A ───────────────────────────────────────────────────────────────────────
def answer_question(question, context, chat_history, chunks_used=None):

    prompt = f"""
    You are a highly helpful, extremely user-friendly legal assistant helping an everyday person understand their contract.
    Based ONLY on the context below, answer the user's question directly.
    - strictly NO repeating or continuing the user's question. Start your response immediately with the answer.
    - Explain things simply and conversationally in 2-4 sentences.
    - Use bullet points if listing multiple requirements or dates.
    - Bold important terms or deadlines so they are easy to spot.
    - strictly NO legal jargon. Instead of "Indemnification", say "Protecting from lawsuits".
    - If it's a yes/no question, strictly start your answer with a clear "Yes." or "No.".
    - If the context does NOT explicitly contain the answer, do not guess! You MUST firmly state: "The contract does not specify."
    
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
            if ct and ct.lower() != "other" and ct.title() not in sources:
                sources.append(ct.title())

    if "docs not specify" in result.lower() or "does not specify" in result.lower():
        confidence = 0.3
        caveat = "The contract text provided likely does not contain this information."

    return SimpleNamespace(
        answer=result,
        confidence=confidence,
        sources=sources,
        caveat=caveat
    )

# ── Dynamic Q&A ───────────────────────────────────────────────────────────────
def generate_dynamic_questions(summary: str) -> List[str]:
    prompt = f"""
    You are an AI contract analyst helping a regular person. Based ONLY on the contract text, generate exactly 3 simple, important questions a LAYMAN (someone not a lawyer) would ask.
    
    CRITICAL RULES: 
    1. LAYMAN LANGUAGE: Use plain English (e.g., "Can I cancel this?", "When do I get paid?", "What are my risks?").
    2. PRACTICAL & SHORT: Focus on money, dates, and how to get out. Keep questions under 12 words.
    3. SPECIFIC: Don't be generic. If it's an NDA, ask about "secrets". If it's a rental, ask about "pests" or "deposit".
    
    Contract Text:
    {summary}
    
    Return EXACTLY 3 layman questions in valid JSON:
    {{"questions": ["Question 1", "Question 2", "Question 3"]}}
    """
    
    try:
        result = call_llm(prompt, json_mode=True)
        data = json.loads(result)
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