import os
from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# Import our custom data loader function
from data_loader import load_local_contracts

def process_and_store_chunks():
    # Load the documents using the function we built earlier
    print("Loading documents from data directory...")
    docs = load_local_contracts("./data")
    
    if not docs:
        print("No documents found. Exiting process.")
        return

    # Initialize the embedding model (Free HuggingFace model for testing)
    print("\nInitializing embedding model...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # 1. Fixed-size Chunking
    print("\nApplying Fixed-size Chunking...")
    fixed_splitter = CharacterTextSplitter(
        separator="\n\n",
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    fixed_chunks = fixed_splitter.split_documents(docs)
    print(f"Created {len(fixed_chunks)} fixed-size chunks.")

    # 2. Recursive Character Chunking
    print("\nApplying Recursive Character Chunking...")
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    recursive_chunks = recursive_splitter.split_documents(docs)
    print(f"Created {len(recursive_chunks)} recursive chunks.")

    # 3. Semantic Chunking
    print("\nApplying Semantic Chunking...")
    semantic_splitter = SemanticChunker(embeddings)
    semantic_chunks = semantic_splitter.split_documents(docs)
    print(f"Created {len(semantic_chunks)} semantic chunks.")

    # Storing chunks in Chroma DB
    print("\nStoring chunks in 3 separate Chroma databases...")

    db_configs = [
        ("Fixed",     fixed_chunks,     "./chroma_db_fixed"),
        ("Recursive", recursive_chunks, "./chroma_db_recursive"),
        ("Semantic",  semantic_chunks,  "./chroma_db_semantic"),
    ]

    for name, chunks, persist_dir in db_configs:
        if os.path.exists(persist_dir):
            print(f"Skipping {name} DB — already exists at '{persist_dir}'.")
            continue
        print(f"Saving {name} Chunks DB...")
        Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=persist_dir,
        )

    print("\nAll 3 vector databases have been successfully created and saved locally.")

if __name__ == "__main__":
    process_and_store_chunks()