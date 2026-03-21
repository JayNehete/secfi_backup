import faiss
import pickle
import numpy as np
import ollama
from sentence_transformers import SentenceTransformer

INDEX_PATH = "faiss_index"
CHUNKS_PATH = "chunks.pkl"

class RAGPipeline:
    def __init__(self):
        print("🔄 Loading embedding model...")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

        print("🔄 Loading FAISS index...")
        self.index = faiss.read_index(INDEX_PATH)

        print("🔄 Loading text chunks...")
        with open(CHUNKS_PATH, "rb") as f:
            self.chunks = pickle.load(f)

        print("✅ RAG system ready!")

    def retrieve(self, query, k=4):
        query_embedding = self.embedder.encode([query])
        distances, indices = self.index.search(
            np.array(query_embedding), k
        )

        retrieved_chunks = [self.chunks[i] for i in indices[0]]
        return retrieved_chunks

    def generate_answer(self, query):
        retrieved_chunks = self.retrieve(query)

        context = "\n\n".join(retrieved_chunks)

        # UPDATED PROMPT: Tailored for financial narrative + numerical data
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

        response = ollama.chat(
            model="deepseek-r1:latest",
            messages=[{"role": "user", "content": prompt}]
        )

        return response["message"]["content"]


if __name__ == "__main__":
    rag = RAGPipeline()

    while True:
        query = input("\nAsk a question (or type 'exit'): ")

        if query.lower() == "exit":
            break

        answer = rag.generate_answer(query)
        print("\n🤖 Answer:\n")
        print(answer)