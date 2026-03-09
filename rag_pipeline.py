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

        prompt = f"""
You are a helpful assistant.

Answer ONLY using the context below.
If the answer is not contained in the context, say "I don't know."

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