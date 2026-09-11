# Legal Contract Question Answering with RAG

A retrieval-augmented generation (RAG) system that answers questions about commercial
legal contracts from the CUAD dataset. It runs two open-weight language models locally,
Llama 3.1 8B Instruct and Mistral 7B Instruct, both under 4-bit quantization so they fit
on a single consumer GPU. A Streamlit interface lets you ask questions about the loaded
contracts and see the passages each answer was drawn from.

This repository is the code for a diploma thesis at the Department of Electrical and
Computer Engineering, University of Thessaly. The written thesis is under
`overleaf_thesis/`.

## What it does

Given a question about a named contract, the system retrieves the most relevant passages
from that contract and passes them to a language model, which answers from the retrieved
text rather than from its training data. Because the answer is built from specific
passages, it can be traced back to the part of the contract it came from.

The pipeline has the following stages:

1. **Chunking.** Each contract is split into passages using one of three strategies:
   fixed-size (1,000 characters, 200 overlap), recursive character splitting, or semantic
   splitting based on sentence-embedding similarity. Each strategy is stored in its own
   Chroma database.
2. **Embedding.** Passages and queries are embedded with `all-MiniLM-L6-v2` (384
   dimensions) from Sentence Transformers.
3. **Retrieval.** Dense similarity search over Chroma runs alongside a BM25 keyword index.
   BM25 queries are expanded with a hand-written list of legal synonyms so that a query
   for a CUAD category such as *Expiration Date* also matches wording like *terminate upon
   90 days notice*. Every question is scoped to the named contract, and the two result
   lists are interleaved and de-duplicated down to the top `k` passages (`k = 10` in the
   experiments).
4. **Generation.** The retrieved passages, the conversation history, and the question are
   sent to the selected model with a prompt that instructs it to quote the relevant clause
   and to reply with a fixed "Not found" phrase when no related clause is present.
5. **Memory.** Multi-turn conversations use either a windowed memory (the last `k` turns
   kept verbatim) or a running summary produced by the model.

## Dataset

The system uses CUAD (Contract Understanding Atticus Dataset): 510 commercial contracts
with expert annotations across 41 clause categories, in SQuAD format. The data is not
included in this repository. Download it from the Atticus Project
(https://www.atticusprojectai.org/cuad) or the Hugging Face dataset `theatticusproject/cuad`
and place it as:

```
data/CUADv1.json
data/full_contract_txt/*.txt
```

## Requirements

- An NVIDIA GPU with about 8 GB of memory. The thesis experiments used an RTX 3060 Ti.
  Both models load at roughly 5 GB each under 4-bit NF4 quantization, one at a time.
- Docker with the NVIDIA Container Toolkit, or a local Python 3.10 environment.
- A Hugging Face account with access to the gated Llama 3.1 models.
- An OpenAI API key if you want to run the evaluation (GPT-4o-mini is the RAGAS and
  LLM-as-a-judge evaluator). The interactive app does not need it.

## Setup

Clone the repository and add the dataset as shown above. Then create a `.env` file in the
project root:

```
HF_TOKEN=your_huggingface_token
OPENAI_API_KEY=your_openai_key          # only needed for evaluation
LANGFUSE_PUBLIC_KEY=...                  # optional, for latency/token tracing
LANGFUSE_SECRET_KEY=...                  # optional
LANGFUSE_HOST=https://cloud.langfuse.com # optional
```

Build the three vector databases from the contract texts. This reads `data/`, chunks every
contract with the three strategies, and writes `chroma_db_fixed/`, `chroma_db_recursive/`,
and `chroma_db_semantic/`:

```bash
python src/chunking.py
```

### Run with Docker

```bash
docker compose up --build
```

The Streamlit app is served on http://localhost:8501 and a Jupyter server on
http://localhost:8888. Downloaded model weights are kept in a named volume, so they are
downloaded once and reused across restarts.

### Run locally

Install PyTorch for your CUDA version first (see https://pytorch.org/get-started/locally/),
then the rest of the dependencies:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
streamlit run src/app.py
```

## Using the app

Pick a model, chunking strategy, memory type, and `k` in the sidebar, then press **Load
Chain** to assemble the pipeline for that configuration. The first load downloads the
model weights; later loads reuse the cached model. Ask a question that names a contract,
for example:

```
In the contract "VERICELCORP_08_06_2019-EX-10.10-SUPPLY AGREEMENT", what is the governing law?
```

Each answer shows the reformulated retrieval query (when memory rewrites the question) and
an expander listing the retrieved passages with their source filenames.

## Evaluation

`src/evaluate.py` runs the automated evaluation. It draws a fixed stratified sample of CUAD
questions (14 answerable, 6 unanswerable by default at seed 42) and scores each answer with
four RAGAS metrics (Faithfulness, Answer Relevancy, Context Precision, Context Recall) and
two LLM-as-a-judge metrics (correctness and conciseness). Results are written to
`results/` as per-question and per-configuration CSV files.

Run one configuration:

```bash
python src/evaluate.py --chunking recursive --model llama --sample 20 --seed 42 --eval_model openai
```

Run the no-retrieval baseline for one model (the model answers from general knowledge
only, which measures how much retrieval contributes):

```bash
python src/evaluate.py --baseline --model llama --sample 20 --seed 42 --eval_model openai
```

The three chunking strategies and two models give six configurations. The two memory
strategies are not part of the automated scores, because each question is evaluated in
isolation with the memory cleared first; they are compared separately through a multi-turn
session in the app. Full results, tables, and analysis are in the thesis under
`overleaf_thesis/`.

## Repository layout

```
src/app.py           Streamlit interface
src/rag_chain.py     conversational RAG chain: retrieval, prompts, memory
src/retriever.py     Chroma dense retriever and BM25 keyword retriever
src/chunking.py      builds the three vector databases from the contract texts
src/data_loader.py   loads the contract text files
src/llm.py           loads Llama or Mistral with 4-bit quantization
src/evaluate.py      RAGAS and LLM-as-a-judge evaluation, and the no-retrieval baseline
data/                CUAD dataset (not tracked)
chroma_db_*/         vector databases, created by src/chunking.py (not tracked)
results/             evaluation output (not tracked)
overleaf_thesis/     the written thesis
Dockerfile           image with CUDA PyTorch and the dependencies
docker-compose.yml   app and Jupyter services with GPU passthrough
```

## Limitations

Answer quality depends on the retriever returning the correct passage; when it returns a
topically adjacent clause instead, the model can produce an answer that is grounded in the
retrieved text but wrong against the ground truth. Semantic chunking with Llama gives the
best answer quality but is the slowest configuration, with the largest contracts taking
well over a minute per query. Generation uses sampling, so the same question can produce
slightly different answers on different runs.

## Author

Andreas Kanachalidis, Department of Electrical and Computer Engineering, University of
Thessaly. Supervisor: Eleni Tousidou.
