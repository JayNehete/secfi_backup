import os
import faiss
import pickle
import numpy as np
import ollama
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

# --- Configuration ---
INDEX_PATH = "faiss_index"
CHUNKS_PATH = "chunks.pkl"

# --- Pydantic Data Models ---
# These ensure the API only accepts and returns strictly formatted JSON
class QueryRequest(BaseModel):
    query: str
    k: int = 4  # Default to top 4 chunks, but allows the user to request more

class QueryResponse(BaseModel):
    answer: str
    sources_used: int

# --- Core RAG Logic ---
class RAGPipeline:
    def __init__(self):
        print("🔄 Loading embedding model into server memory...")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        print("🔄 Loading FAISS index into server memory...")
        if not os.path.exists(INDEX_PATH) or not os.path.exists(CHUNKS_PATH):
            raise FileNotFoundError("FAISS index or chunks not found. Run ingest.py first.")
            
        self.index = faiss.read_index(INDEX_PATH)

        print("🔄 Loading text chunks...")
        with open(CHUNKS_PATH, "rb") as f:
            self.chunks = pickle.load(f)

        print("✅ RAG engine initialized and ready for API requests!")

    def retrieve(self, query: str, k: int = 4):
        query_embedding = self.embedder.encode([query])
        distances, indices = self.index.search(
            np.array(query_embedding), k
        )
        return [self.chunks[i] for i in indices[0]]

    def generate_answer(self, query: str, k: int = 4):
        retrieved_chunks = self.retrieve(query, k)
        context = "\n\n".join(retrieved_chunks)

        prompt = f"""
You are an expert financial AI assistant.

Answer ONLY using the provided context below. The context contains a mix of narrative text from SEC filings (like MD&A) and structured numerical metrics (Income Statement, Balance Sheet).

Rules:
1. If the context contains numerical data, be precise with the numbers and Year-over-Year (YoY) changes.
2. If the user asks for a specific metric (e.g., "Total Revenue"), quote the exact value and the YoY change provided in the context.
3. If the answer is not contained in the context, say "I don't know based on the provided documents."

Context:
{context}

Question:
{query}

Answer:
"""
        # Note: We are still pointing to the local Ollama instance for DeepSeek.
        # In Phase 3, this will point to a dedicated cloud inference endpoint.
        response = ollama.chat(
            model="deepseek-r1:latest",
            messages=[{"role": "user", "content": prompt}]
        )

        return response["message"]["content"], len(retrieved_chunks)

# --- FastAPI Initialization & Lifespan ---
# Global variable to hold the initialized RAG pipeline
rag_system = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs exactly once when the server starts
    global rag_system
    try:
        rag_system = RAGPipeline()
    except Exception as e:
        print(f"❌ Failed to start RAG system: {e}")
    yield
    # This runs when the server is shutting down
    print("🛑 Shutting down API and clearing memory...")
    rag_system = None

app = FastAPI(
    title="SEC Financial RAG API", 
    description="API for querying highly structured SEC financial data.",
    lifespan=lifespan
)

# --- API Endpoints ---
@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    if not rag_system:
        raise HTTPException(status_code=503, detail="RAG Pipeline is currently offline or failed to load.")
    
    try:
        print(f"Processing query: '{request.query}'")
        answer, chunk_count = rag_system.generate_answer(request.query, request.k)
        
        return QueryResponse(
            answer=answer,
            sources_used=chunk_count
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Simple endpoint to verify the API is running."""
    status = "healthy" if rag_system else "degraded"
    return {"status": status, "rag_loaded": rag_system is not None}

if __name__ == "__main__":
    import uvicorn
    # Run the server on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)