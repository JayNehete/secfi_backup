import os
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pickle

DATA_PATH = "data"
INDEX_PATH = "faiss_index"
CHUNKS_PATH = "chunks.pkl"

def load_text_files():
    texts = []
    for file in os.listdir(DATA_PATH):
        if file.endswith(".txt"):
            with open(os.path.join(DATA_PATH, file), "r", encoding="utf-8") as f:
                texts.append(f.read())
    return "\n".join(texts)

def chunk_text(text):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    return splitter.split_text(text)

def create_vector_store(chunks):
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(chunks)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings))

    faiss.write_index(index, INDEX_PATH)

    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(chunks, f)

    print("✅ Vector store created successfully!")

if __name__ == "__main__":
    print("Loading text...")
    text = load_text_files()

    print("Chunking...")
    chunks = chunk_text(text)

    print("Creating embeddings + FAISS index...")
    create_vector_store(chunks)