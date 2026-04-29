import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent directory to sys.path to allow importing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.doc_processor import process_raw_text
from modules.clause_matcher import match_chunks, summarize_risk_profile
from modules.embedder import index_chunks, semantic_search
from modules.llm_engine import extract_clauses, verify_document_type, answer_question, generate_dynamic_questions

app = FastAPI(title="ClauseWise API", description="Backend for ClauseWise Chrome Extension")

# Allow requests from Chrome Extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify the Chrome Extension ID
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeRequest(BaseModel):
    text: str
    source_url: str = "Webpage"

class QARequest(BaseModel):
    question: str
    source_url: str = "Webpage"

@app.post("/api/analyze")
async def analyze_document(req: AnalyzeRequest):
    try:
        # 1. Process Text
        if not req.text or len(req.text) < 100:
            if req.source_url.startswith("http") and req.source_url.lower().split("?")[0].endswith(".pdf"):
                import requests
                import tempfile
                try:
                    res = requests.get(req.source_url, timeout=15)
                    res.raise_for_status()
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(res.content)
                        tmp_path = tmp.name
                    from modules.doc_processor import process_contract
                    chunks = process_contract(tmp_path)
                    os.unlink(tmp_path)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Could not download PDF: {str(e)}")
            else:
                raise HTTPException(status_code=400, detail="Could not extract text. If you are viewing a PDF in Chrome, the extension cannot read it directly unless it has a public URL.")
        else:
            chunks = process_raw_text(req.text, source_file=req.source_url)
            
        chunk_texts = [c.text for c in chunks]
        
        # 2. Verify
        verification = verify_document_type(" ".join(chunk_texts[:3]))
        
        # 3. Match Clauses
        match_results = match_chunks(chunk_texts)
        
        # 4. Index for Q&A
        index_chunks(chunks, topic_labels=match_results)
        
        # 5. Extract Details
        analysis = extract_clauses(" ".join(chunk_texts[:8]), contract_name=req.source_url)
        
        # 6. Profile Summary
        profile = summarize_risk_profile(match_results)
        
        # 7. Dynamic Questions
        summary_text = analysis.executive_summary if hasattr(analysis, "executive_summary") else "A legal contract."
        dynamic_questions = generate_dynamic_questions(summary_text)
        
        return {
            "is_contract": verification.get("is_contract"),
            "verification_reason": verification.get("reason"),
            "analysis": analysis.model_dump() if hasattr(analysis, 'model_dump') else analysis.dict() if hasattr(analysis, 'dict') else analysis,
            "profile": profile,
            "dynamic_questions": dynamic_questions,
            "chunks_processed": len(chunks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/qa")
async def qa_document(req: QARequest):
    try:
        # Retrieve context
        retrieved = semantic_search(req.question, top_k=4)
        context = "\n\n".join([r["text"] for r in retrieved])
        
        # Answer question
        ans = answer_question(req.question, context, chat_history=[], chunks_used=retrieved)
        
        ans_data = ans.model_dump() if hasattr(ans, 'model_dump') else ans.dict() if hasattr(ans, 'dict') else ans
        return ans_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"status": "ClauseWise API is running"}
