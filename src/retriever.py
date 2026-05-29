import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# Must match the model used in chunking.py during indexing
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Map strategy names to their ChromaDB persist directories
CHROMA_DIRS = {
    "fixed":     "./chroma_db_fixed",
    "recursive": "./chroma_db_recursive",
    "semantic":  "./chroma_db_semantic",
}


def get_embeddings() -> HuggingFaceEmbeddings:
    """Load the MiniLM embedding model."""
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def load_vectorstore(strategy: str, embeddings: HuggingFaceEmbeddings = None) -> Chroma:
    """
    Connect to an existing ChromaDB for the given chunking strategy.
    Does NOT re-add documents — reads the persisted index only.

    Args:
        strategy:   One of 'fixed', 'recursive', 'semantic'
        embeddings: Optional pre-loaded embeddings (avoids reloading the model)

    Returns:
        A LangChain Chroma vectorstore instance
    """
    if strategy not in CHROMA_DIRS:
        raise ValueError(
            f"Unknown strategy '{strategy}'. Choose from: {list(CHROMA_DIRS.keys())}"
        )

    persist_dir = CHROMA_DIRS[strategy]

    if not os.path.exists(persist_dir):
        raise FileNotFoundError(
            f"ChromaDB for '{strategy}' not found at '{persist_dir}'. "
            "Run chunking.py first to build the vector databases."
        )

    if embeddings is None:
        embeddings = get_embeddings()

    return Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
    )


def get_retriever(
    strategy: str,
    k: int = 5,
    search_type: str = "mmr",
    embeddings: HuggingFaceEmbeddings = None,
):
    """
    Build a retriever for one chunking strategy.

    MMR (Maximal Marginal Relevance) is the default because legal contracts
    contain many near-identical clauses across documents — MMR diversifies the
    retrieved chunks so the LLM sees a broader context instead of five copies
    of the same sentence.

    Args:
        strategy:    One of 'fixed', 'recursive', 'semantic'
        k:           Number of chunks to return
        search_type: 'mmr' | 'similarity' | 'similarity_score_threshold'
        embeddings:  Optional pre-loaded embeddings to share across retrievers

    Returns:
        A LangChain VectorStoreRetriever
    """
    vectorstore = load_vectorstore(strategy, embeddings)

    search_kwargs: dict = {"k": k}

    if search_type == "mmr":
        # fetch_k: candidate pool size before MMR re-ranking
        # lambda_mult: 0 = max diversity, 1 = max relevance (0.7 = relevance-leaning)
        search_kwargs["fetch_k"] = k * 4
        search_kwargs["lambda_mult"] = 0.7

    elif search_type == "similarity_score_threshold":
        # Only return chunks whose cosine similarity exceeds this threshold.
        # 0.3 is intentionally lenient for legal text (domain-specific vocabulary
        # lowers similarity scores compared to general text).
        search_kwargs["score_threshold"] = 0.3

    return vectorstore.as_retriever(
        search_type=search_type,
        search_kwargs=search_kwargs,
    )


def get_bm25_retriever(
    strategy: str,
    k: int = 50,
    embeddings: HuggingFaceEmbeddings = None,
):
    """
    Build a BM25 keyword retriever from all documents stored in ChromaDB.

    BM25 catches exact and near-exact term matches that semantic search misses
    when the query and document use different but legally equivalent phrasing
    (e.g. "expiration date" vs "terminate upon 90 days notice").

    Args:
        strategy:   One of 'fixed', 'recursive', 'semantic'
        k:          Number of candidates to return (set high — caller filters)
        embeddings: Passed to load_vectorstore to avoid reloading the model

    Returns:
        A LangChain BM25Retriever over all chunks in the ChromaDB store
    """
    from langchain_community.retrievers import BM25Retriever
    from langchain_core.documents import Document

    vectorstore = load_vectorstore(strategy, embeddings)

    # Fetch in batches — SQLite (used by ChromaDB) has a hard limit on the
    # number of SQL variables per query (~999), so fetching all 50k+ chunks
    # at once raises "too many SQL variables". Batching of 5 000 stays safe.
    BATCH = 5_000
    all_texts, all_metas = [], []
    offset = 0
    while True:
        batch = vectorstore.get(
            include=["documents", "metadatas"],
            limit=BATCH,
            offset=offset,
        )
        if not batch["documents"]:
            break
        all_texts.extend(batch["documents"])
        all_metas.extend(batch["metadatas"])
        offset += len(batch["documents"])
        if len(batch["documents"]) < BATCH:
            break

    docs = [
        Document(page_content=text, metadata=meta or {})
        for text, meta in zip(all_texts, all_metas)
    ]
    retriever = BM25Retriever.from_documents(docs)
    retriever.k = k
    return retriever


def get_all_retrievers(
    k: int = 5,
    search_type: str = "mmr",
) -> dict:
    """
    Load all three retrievers, sharing one embedding model instance.

    Args:
        k:           Number of chunks each retriever returns
        search_type: Search method applied to all retrievers

    Returns:
        dict with keys 'fixed', 'recursive', 'semantic'
    """
    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    embeddings = get_embeddings()

    retrievers = {}
    for strategy in CHROMA_DIRS:
        print(f"  Loading '{strategy}' vectorstore...")
        retrievers[strategy] = get_retriever(
            strategy,
            k=k,
            search_type=search_type,
            embeddings=embeddings,
        )

    print("All retrievers ready.\n")
    return retrievers


if __name__ == "__main__":
    # Smoke test: run a sample legal query against all three retrievers
    TEST_QUERY = "What is the governing law of this contract?"

    print("=" * 60)
    print("RETRIEVER SMOKE TEST")
    print("=" * 60)

    retrievers = get_all_retrievers(k=5, search_type="mmr")

    print(f"Query: \"{TEST_QUERY}\"\n")
    for strategy, retriever in retrievers.items():
        print(f"--- {strategy.upper()} chunking ---")
        results = retriever.invoke(TEST_QUERY)
        print(f"Retrieved {len(results)} chunks")
        if results:
            print(f"Top chunk preview:\n  {results[0].page_content[:250].strip()}...")
            print(f"  Source: {results[0].metadata.get('source', 'unknown')}")
        print()
