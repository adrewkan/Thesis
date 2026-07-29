from langchain_community.document_loaders import DirectoryLoader, TextLoader

def load_local_contracts(data_dir="./data"):
    print(f"Reading all .txt files from directory {data_dir} and its subdirectories...")
    
    loader = DirectoryLoader(
        data_dir, 
        glob="**/*.txt", 
        loader_cls=TextLoader, 
        show_progress=True
    )
    
    docs = loader.load()
    
    if not docs:
        print("Warning: No documents were loaded.")
        return []
        
    print(f"\nSuccessfully loaded {len(docs)} legal contracts.")
    print("\n" + "="*50)
    print("EXAMPLE (First 500 characters of the first contract):")
    print("="*50)
    print(docs[0].page_content[:500] + "...\n")
    print("="*50)
    print(f"File source metadata: {docs[0].metadata['source']}")
    
    return docs

if __name__ == "__main__":
    # If run directly, just load and print, we don't need to save the variable
    load_local_contracts()