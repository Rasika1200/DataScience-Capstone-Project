# AI-Powered ContractOps Copilot

## Overview
**ContractOps Copilot** is a high-performance, full-stack enterprise application designed to ingest, analyze, and interrogate complex legal contracts instantly. Built for the DATS 6501 Capstone project at GWU, the platform seamlessly replaces hours of manual legal review with a robust Retrieval-Augmented Generation (RAG) pipeline and mathematical risk mapping.

## Key Features

1. **Intelligent Document Extraction**
   - Automatically parses dense unstructured PDF and Word (.docx) documents.
   - Converts legal jargon into deterministic, overlapping semantic chunks mapped against canonical clause definitions.
   
2. **Dynamic Risk Dashboarding**
   - Heuristically scores the liability and threat vectors (0.0 to 1.0) of extracted clauses.
   - Instantly aggregates the contract's posture into an overarching **Overall Risk Level** with natively generated visual distribution charts (Pandas/Plotly).

3. **Semantic RAG Conversational Engine**
   - Embeds document chunks using HuggingFace's `all-MiniLM-L6-v2` dense local index (via ChromaDB).
   - Generates answers using Groq Cloud's *Llama 3.1 8B* architecture with absolute hallucination barriers (`"If context does not contain the answer, do not guess."`).

4. **Speech-to-Text & Text-to-Speech (STT/TTS)**
   - Speak directly to your document using an integrated frontend microphone tied to **OpenAI Whisper** for natural language translation.
   - **Offline Pyttsx3 TTS** dynamically auto-generates readable `.wav` audio to speak the contract's summaries entirely offline.

5. **Human-In-The-Loop (HITL) Validation**
   - Legal operators aren't sidelined. Users actively 'Accept', 'Edit', or 'Reject' the AI's determinations.
   - Audits are persisted indefinitely utilizing a discrete SQLite database architecture for real-time human reliability indexing.

6. **Hybrid System Resiliency**
   - In the event of network disruption or Cloud API rate limits, the platform's backend catches the pipeline exception and instantly triggers a local, offline **Ollama** engine (`Llama 3.2 3B`) with expanded 8K token context scaling to maintain 100% operational uptime.

## Tech Stack
*   **Frontend/Orchestration:** Streamlit, Custom Glassmorphism CSS, Plotly
*   **AI Models:** Groq Cloud API (Llama 3.1), Local Ollama (Llama 3.2), Whisper
*   **Information Retrieval:** ChromaDB, HuggingFace SentenceTransformers
*   **Data Processing:** PyMuPDF (`fitz`), Python-docx, Pandas, NumPy
*   **State Persistence:** SQLite3