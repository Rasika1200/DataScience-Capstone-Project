# ClauseWise Technical Architecture

## 1. System Overview
ClauseWise is a multi-tier application designed for high-speed legal document analysis. It utilizes a **Decoupled RAG (Retrieval-Augmented Generation)** architecture.

## 2. Core Components

### 2.1 Document Processing (`modules/doc_processor.py`)
- **Extraction:** Uses PyMuPDF and Python-Docx to handle unstructured data.
- **Chunking:** Implements a sliding-window algorithm (500-word window, 80-word overlap) to preserve semantic context at sentence boundaries.

### 2.2 Embedding & Retrieval (`modules/embedder.py`, `modules/rag_pipeline.py`)
- **Model:** `all-MiniLM-L6-v2` (384-dimensional dense vectors).
- **Vector Store:** ChromaDB with Cosine Similarity indexing.
- **RAG Pipeline:** Performs semantic search, context assembly, and metadata-aware retrieval.

### 2.3 AI Engine (`modules/llm_engine.py`)
- **Primary:** Groq Cloud (Llama 3.1 8B) for sub-second cloud inference.
- **Resiliency:** Automated fallback to local Ollama (Llama 3.2 3B) during network failure or rate-limiting.
- **Guardrails:** Deterministic prompting (Temperature = 0.0) with strict source-grounding instructions.

### 2.4 User Interfaces
- **Streamlit (`app/main_app.py`):** The primary analytical workspace featuring glassmorphism UI and Plotly risk gauges.
- **Chrome Extension (`extension/`):** A frontend overlay that connects to the FastAPI backend (`api/main.py`) for on-the-fly webpage analysis.

## 3. Data Flow
1. **User Uploads** contract -> **Processor** chunks text.
2. **Embedder** generates vectors -> **ChromaDB** stores index.
3. **User Asks Question** -> **Pipeline** retrieves relevant chunks.
4. **LLM Engine** generates grounded answer -> **UI** displays response with citations.
5. **Human Reviewer** validates finding -> **SQLite** stores decision for audit.
