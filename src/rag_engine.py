import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer
from rich.console import Console

from . import config
from .corpus_builder import build_corpus

console = Console()

_embedding_model = None
_client = None


class SentenceTransformerEmbedding(EmbeddingFunction):
    def __init__(self, model_name):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            console.print("[dim]Loading embedding model...[/dim]")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def __call__(self, input: Documents) -> Embeddings:
        model = self._get_model()
        embeddings = model.encode(input)
        return embeddings.tolist()

    def name(self):
        return f"sentence-transformers-{self.model_name}"


def _get_embedding_function():
    return SentenceTransformerEmbedding(config.EMBEDDING_MODEL)


def _get_chroma_client():
    global _client
    if _client is None:
        config.CORPUS_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(config.CORPUS_DIR))
    return _client


def _get_collection(ticker):
    client = _get_chroma_client()
    collection_name = f"sec_{ticker.upper()}"
    ef = _get_embedding_function()

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def corpus_exists(ticker):
    client = _get_chroma_client()
    collection_name = f"sec_{ticker.upper()}"
    try:
        collection = client.get_collection(collection_name)
        return collection.count() > 0
    except Exception:
        return False


def build_and_store_corpus(ticker):
    documents, metadatas, ids = build_corpus(ticker)
    if not documents:
        console.print(f"[yellow]No documents found for {ticker.upper()}[/yellow]")
        return False

    collection = _get_collection(ticker)

    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]
        batch_ids = ids[i : i + batch_size]
        collection.add(
            documents=batch_docs,
            metadatas=batch_meta,
            ids=batch_ids,
        )

    console.print(f"[green]Stored {len(documents)} chunks in vector DB for {ticker.upper()}[/green]")
    return True


def query(ticker, question, top_k=config.TOP_K_RESULTS):
    if not corpus_exists(ticker):
        console.print(f"[yellow]Corpus not found for {ticker.upper()}, building now...[/yellow]")
        success = build_and_store_corpus(ticker)
        if not success:
            return []

    collection = _get_collection(ticker)
    results = collection.query(
        query_texts=[question],
        n_results=top_k,
        where={"ticker": ticker.upper()},
    )

    chunks = []
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else None
            chunks.append({
                "text": doc,
                "metadata": meta,
                "relevance_score": 1 - distance if distance is not None else None,
            })

    return chunks
