"""
evaluate.py

Batch RAGAS evaluation of RAG configurations against CUAD ground truth.

Metrics computed per configuration:
  - Faithfulness      : is the answer supported by the retrieved context?
  - AnswerRelevancy   : is the answer relevant to the question asked?
  - ContextPrecision  : are relevant chunks ranked higher?
  - ContextRecall     : do the retrieved chunks cover the ground truth?
  - Judge Correctness : LLM-as-a-Judge, does the answer match ground truth? (0-1)
  - Judge Conciseness : LLM-as-a-Judge, is the answer focused? (0-1)

The automated evaluation compares 3 chunking strategies against 2 language
models, giving 6 configurations:
  chunking : fixed, recursive, semantic
  model    : llama, mistral
Memory type (windowed, summary) is selectable but does not change the automated
scores, because each question runs in isolation with the memory cleared first.

Output files (written to results/):
  eval_results_<timestamp>.csv   per-question rows for every config
  eval_summary_<timestamp>.csv   one aggregated row per config

Usage (inside Docker):
    # Single config
    python src/evaluate.py \\
        --cuad_json data/CUADv1.json \\
        --chunking recursive --model llama --memory windowed \\
        --sample 20 --eval_model openai

    # Every chunking/model combination in sequence
    python src/evaluate.py --cuad_json data/CUADv1.json --all_configs --sample 20 --eval_model openai

Requirements:
    - CUAD JSON at data/CUADv1.json (from the CUAD GitHub repo or the
      HuggingFace dataset theatricusproject/cuad).
    - An evaluator LLM for RAGAS and LLM-as-a-Judge, chosen with --eval_model
      or auto-detected from the API keys in .env:
        openai : gpt-4o-mini, needs OPENAI_API_KEY (used for the thesis results)
        nvidia : Llama 3.1 70B via NVIDIA NIM, needs NVIDIA_API_KEY
        local  : the same HuggingFace model as --model, no API key
        rouge  : no LLM; RAGAS and the judge are skipped, only ROUGE-L is used
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# CUAD loading & sampling
# ---------------------------------------------------------------------------

def load_cuad(json_path: str) -> list[dict]:
    """
    Parse CUADv1.json and return a flat list of QA dicts:
      {
        "id":           str,
        "question":     str,
        "ground_truth": str,   # "" for is_impossible=True
        "is_impossible": bool,
        "contract_title": str,
      }
    """
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    records: list[dict] = []
    for article in raw["data"]:
        title = article.get("title", "")
        for para in article["paragraphs"]:
            for qa in para["qas"]:
                answers = qa.get("answers", [])
                gt = "\n\n".join(a["text"].strip() for a in answers) if answers else ""
                records.append({
                    "id": qa["id"],
                    "question": qa["question"],
                    "ground_truth": gt,
                    "is_impossible": qa.get("is_impossible", False),
                    "contract_title": title,
                })
    return records


def sample_questions(
    records: list[dict],
    n: int,
    seed: int = 42,
    impossible_ratio: float = 0.3,
) -> list[dict]:
    """
    Return a stratified sample of n questions.
    impossible_ratio controls the proportion of is_impossible=True rows
    (CUAD has ~50% impossible; we down-weight them to 30% by default so
    most questions test actual retrieval rather than absence detection).
    """
    rng = random.Random(seed)
    possible   = [r for r in records if not r["is_impossible"]]
    impossible = [r for r in records if r["is_impossible"]]

    n_impossible = min(int(n * impossible_ratio), len(impossible))
    n_possible   = min(n - n_impossible, len(possible))

    sample = rng.sample(possible, n_possible) + rng.sample(impossible, n_impossible)
    rng.shuffle(sample)
    return sample


# ---------------------------------------------------------------------------
# RAGAS setup
# ---------------------------------------------------------------------------

def build_ragas_metrics(eval_model: str, model_key: str = "llama"):
    """
    Return (metrics_list, use_ragas).

    Uses the RAGAS 0.4.x class-based API.

    eval_model:
      "openai" : gpt-4o-mini evaluator (requires OPENAI_API_KEY in .env).
                 Most reliable for the structured JSON verdicts RAGAS needs,
                 and the evaluator used for the thesis results.
      "nvidia" : Llama 3.1 70B via NVIDIA NIM (requires NVIDIA_API_KEY);
                 embeddings stay local with all-MiniLM-L6-v2.
      "local"  : the same local HuggingFace model used for the RAG answers
                 (no API key). 7B/8B models occasionally emit malformed JSON,
                 so some scores can come back as None.
      "rouge"  : skip RAGAS entirely and use ROUGE-L only.

    Computes the four RAGAS metrics: Faithfulness, AnswerRelevancy,
    ContextPrecision, and ContextRecall.
    """
    from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper

    if eval_model == "openai":
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        evaluator_llm = LangchainLLMWrapper(
            ChatOpenAI(model="gpt-4o-mini", temperature=0)
        )
        evaluator_embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())
        print("  [RAGAS] Evaluator: gpt-4o-mini (OpenAI)")

    elif eval_model == "nvidia":
        # NVIDIA NIM - OpenAI-compatible API, free credits at build.nvidia.com
        # Uses a 70B model for reliable structured JSON output in RAGAS.
        # Embeddings stay local (all-MiniLM-L6-v2) - no extra API needed.
        from langchain_openai import ChatOpenAI
        from langchain_huggingface import HuggingFaceEmbeddings
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        if not nvidia_key:
            print("  WARNING: NVIDIA_API_KEY not set - falling back to local evaluator.")
            eval_model = "local"
        else:
            nvidia_model = os.getenv("NVIDIA_EVAL_MODEL", "meta/llama-3.1-70b-instruct")
            evaluator_llm = LangchainLLMWrapper(
                ChatOpenAI(
                    model=nvidia_model,
                    base_url="https://integrate.api.nvidia.com/v1",
                    api_key=nvidia_key,
                    temperature=0,
                )
            )
            evaluator_embeddings = LangchainEmbeddingsWrapper(
                HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            )
            print(f"  [RAGAS] Evaluator: {nvidia_model} (NVIDIA NIM)")

    if eval_model == "local":
        import asyncio
        from llm import load_llm
        from langchain_huggingface import HuggingFaceEmbeddings
        print(f"  [RAGAS] Evaluator: local {model_key} model")

        chat_llm = load_llm(model_key)

        # HuggingFacePipeline raises NotImplementedError on async calls, which
        # RAGAS requires even with max_workers=1.  Patch the instance to run
        # the synchronous _generate inside a thread executor instead.
        _sync_generate = chat_llm._generate
        async def _async_generate(messages, stop=None, run_manager=None, **kwargs):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: _sync_generate(messages, stop=stop, **kwargs)
            )
        chat_llm._agenerate = _async_generate

        evaluator_llm = LangchainLLMWrapper(chat_llm)
        evaluator_embeddings = LangchainEmbeddingsWrapper(
            HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        )
    elif eval_model == "rouge":
        print("  [RAGAS] eval_model=rouge - skipping RAGAS, using ROUGE-L only.")
        return [], False

    metrics = [
        Faithfulness(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        ContextPrecision(llm=evaluator_llm),
        ContextRecall(llm=evaluator_llm),
    ]
    return metrics, True


# ---------------------------------------------------------------------------
# LLM-only baseline (no retrieval)
# ---------------------------------------------------------------------------

_BASELINE_PROMPT = """\
You are a legal assistant. Answer the following question about a commercial contract \
based on your general legal knowledge.
If you do not know the answer, respond with exactly: "Not found."
Be concise.

Question: {question}"""


def run_baseline(
    model_key: str,
    questions: list[dict],
) -> list[dict]:
    """
    Run every question through the LLM with NO retrieval context.

    This is the section 2.6 baseline - the LLM answers from its own training
    knowledge, with no contract chunks provided.  Comparing judge_correctness
    and rouge_l against the RAG results quantifies how much retrieval helps.

    Returns the same result-dict structure as run_config(), but:
      - contexts  is always []
      - RAGAS metrics (faithfulness, context_*) are not applicable and left None
    """
    sys.path.insert(0, str(ROOT / "src"))
    from llm import load_llm

    print(f"\n  Loading LLM for baseline: {model_key}")
    llm = load_llm(model_key)
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    parser = StrOutputParser()
    prompt_tpl = ChatPromptTemplate.from_messages([
        ("human", _BASELINE_PROMPT),
    ])
    chain = prompt_tpl | llm | parser

    results = []
    for i, qa in enumerate(questions, 1):
        t0 = time.perf_counter()
        try:
            answer = chain.invoke({"question": qa["question"]}).strip()
            latency = time.perf_counter() - t0
        except Exception as exc:
            answer = f"ERROR: {exc}"
            latency = time.perf_counter() - t0
            print(f"    [ERROR] Q{i}: {exc}")

        results.append({
            "question":            qa["question"],
            "ground_truth":        qa["ground_truth"],
            "is_impossible":       qa["is_impossible"],
            "contract_title":      qa["contract_title"],
            "answer":              answer,
            "contexts":            [],
            "standalone_question": qa["question"],
            "latency_s":           round(latency, 2),
        })

        if i % 10 == 0:
            print(f"    {i}/{len(questions)} baseline questions done")

    return results


# ---------------------------------------------------------------------------
# Run one configuration
# ---------------------------------------------------------------------------

def run_config(
    chunking: str,
    model_key: str,
    memory_type: str,
    questions: list[dict],
    k_docs: int = 5,
    k_messages: int = 5,
) -> list[dict]:
    """
    Run every question through one RAGChain configuration.

    Returns a list of result dicts (one per question) with fields:
      question, ground_truth, is_impossible, answer,
      contexts (list[str]), latency_s, standalone_question
    """
    sys.path.insert(0, str(ROOT / "src"))
    from rag_chain import build_rag_chain

    print(f"\n  Loading chain: chunking={chunking}, model={model_key}, memory={memory_type}")
    chain = build_rag_chain(
        chunking_strategy=chunking,
        model_key=model_key,
        memory_type=memory_type,
        k_messages=k_messages,
        k_docs=k_docs,
    )

    results = []
    for i, qa in enumerate(questions, 1):
        chain.clear_memory()          # each question is an independent session

        # CUAD questions say "this contract" without naming it.  Inject the
        # contract title in double quotes so _extract_contract_name in rag_chain
        # can trigger contract-specific retrieval instead of a generic search.
        eval_question = f'"{qa["contract_title"]}" — {qa["question"]}'

        t0 = time.perf_counter()
        try:
            out = chain.chat(eval_question)
            latency = time.perf_counter() - t0
            results.append({
                "question":            qa["question"],   # original - used by RAGAS
                "ground_truth":        qa["ground_truth"],
                "is_impossible":       qa["is_impossible"],
                "contract_title":      qa["contract_title"],
                "answer":              out["answer"],
                "contexts":            [d.page_content for d in out["source_documents"]],
                "standalone_question": out["standalone_question"],
                "latency_s":           round(latency, 2),
                "input_tokens":        out.get("input_tokens"),
                "output_tokens":       out.get("output_tokens"),
            })
        except Exception as exc:
            latency = time.perf_counter() - t0
            print(f"    [ERROR] Q{i}: {exc}")
            results.append({
                "question":       qa["question"],
                "ground_truth":   qa["ground_truth"],
                "is_impossible":  qa["is_impossible"],
                "contract_title": qa["contract_title"],
                "answer":         f"ERROR: {exc}",
                "contexts":       [],
                "standalone_question": "",
                "latency_s":      round(latency, 2),
                "input_tokens":   None,
                "output_tokens":  None,
            })

        if i % 10 == 0:
            print(f"    {i}/{len(questions)} questions done")

    return results


# ---------------------------------------------------------------------------
# RAGAS evaluation
# ---------------------------------------------------------------------------

def _rouge_l(prediction: str, reference: str) -> float:
    """ROUGE-L F1 using longest common subsequence (no external library needed)."""
    from difflib import SequenceMatcher
    if not prediction or not reference:
        return 0.0
    pred_tokens = prediction.lower().split()
    ref_tokens  = reference.lower().split()
    matcher = SequenceMatcher(None, pred_tokens, ref_tokens)
    lcs = sum(block.size for block in matcher.get_matching_blocks())
    if lcs == 0:
        return 0.0
    precision = lcs / len(pred_tokens)
    recall    = lcs / len(ref_tokens)
    return round(2 * precision * recall / (precision + recall), 4)


def ragas_evaluate(results: list[dict], metrics: list, use_ragas: bool) -> list[dict]:
    """
    Evaluate results and attach per-question scores.

    If use_ragas=True: uses RAGAS 0.2.x EvaluationDataset API.
    If use_ragas=False: computes ROUGE-L between answer and ground truth locally.

    Impossible questions (is_impossible=True) are skipped for all RAGAS metrics
    - RAGAS is not designed for negative questions (empty ground truth causes
    context_recall=0 and context_precision=0 which unfairly drag down averages).
    """
    if use_ragas:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate, RunConfig

        run_config = RunConfig(max_workers=1, max_retries=0, timeout=300)

        # Only evaluate answerable questions with RAGAS
        answerable_indices = [i for i, r in enumerate(results) if not r.get("is_impossible")]
        answerable = [results[i] for i in answerable_indices]

        # Pre-set all impossible questions to None
        impossible_indices = [i for i, r in enumerate(results) if r.get("is_impossible")]
        # (metric cols not known yet - will be set after first evaluation)

        if answerable:
            samples = [
                SingleTurnSample(
                    user_input=r["question"],
                    response=r["answer"],
                    retrieved_contexts=r["contexts"] if r["contexts"] else [""],
                    reference=r["ground_truth"] if r["ground_truth"] else "N/A",
                )
                for r in answerable
            ]
            dataset = EvaluationDataset(samples=samples)
            ragas_result = evaluate(dataset=dataset, metrics=metrics, run_config=run_config)
            scores_df = ragas_result.to_pandas()

            skip = {"user_input", "response", "retrieved_contexts", "reference"}
            metric_cols = [c for c in scores_df.columns if c not in skip]

            for df_idx, result_idx in enumerate(answerable_indices):
                for col in metric_cols:
                    val = scores_df[col].iloc[df_idx]
                    results[result_idx][col] = round(float(val), 4) if val == val else None

            # Set impossible question scores to None
            for result_idx in impossible_indices:
                for col in metric_cols:
                    results[result_idx][col] = None
    else:
        for r in results:
            r["rouge_l"] = _rouge_l(r["answer"], r["ground_truth"])

    return results


# ---------------------------------------------------------------------------
# LLM-as-a-Judge
# ---------------------------------------------------------------------------

_CORRECTNESS_PROMPT = """\
You are evaluating a legal Q&A system.

Question: {question}
Ground Truth: {ground_truth}
System Answer: {answer}

Score the system answer for CORRECTNESS AND COMPLETENESS.
Does it cover all key facts from the ground truth?

1 = completely wrong or missing all key facts
2 = partially correct, missing major facts
3 = mostly correct, missing some details
4 = correct and nearly complete
5 = completely correct and covers all key facts

Reply ONLY with a JSON object on one line, nothing else:
{{"score": <1-5>, "reason": "<one sentence>"}}"""

_CONCISENESS_PROMPT = """\
You are evaluating a legal Q&A system.

Question: {question}
System Answer: {answer}

Score the system answer for CONCISENESS.
Is it focused, or does it contain unnecessary text unrelated to the question?

1 = extremely verbose, mostly irrelevant content
2 = verbose with some relevant content
3 = mixed — relevant core but notable padding
4 = mostly concise, only minor padding
5 = perfectly concise, no unnecessary text

Reply ONLY with a JSON object on one line, nothing else:
{{"score": <1-5>, "reason": "<one sentence>"}}"""


def _parse_judge_score(text: str) -> float | None:
    """Parse a 1-5 score from the judge LLM response, return as 0-1 float."""
    import json, re
    try:
        m = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            score = int(data.get("score", 0))
            if 1 <= score <= 5:
                return round((score - 1) / 4, 4)
    except Exception:
        pass
    # Fallback: find standalone digit 1-5
    m = re.search(r'\b([1-5])\b', text)
    if m:
        return round((int(m.group(1)) - 1) / 4, 4)
    return None


def build_judge_llm(eval_model: str, model_key: str = "llama"):
    """
    Return a plain LangChain LLM suitable for LLM-as-a-Judge prompts.

    Uses the same provider priority as build_ragas_metrics so the caller
    can reuse whichever model is already available.
    """
    if eval_model == "nvidia":
        from langchain_openai import ChatOpenAI
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        if nvidia_key:
            return ChatOpenAI(
                model=os.getenv("NVIDIA_EVAL_MODEL", "meta/llama-3.1-70b-instruct"),
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=nvidia_key,
                temperature=0,
            )
    if eval_model == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini", temperature=0)
    # local - same model that ran the RAG answers
    from llm import load_llm
    return load_llm(model_key)


def _judge_call(llm, prompt: str, label: str, retries: int = 3) -> float | None:
    """
    Invoke the judge LLM with exponential backoff on 429 rate-limit errors.

    Waits 60 s on the first 429, 120 s on the second, then gives up.
    """
    for attempt in range(retries):
        try:
            resp = llm.invoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)
            return _parse_judge_score(text)
        except Exception as e:
            msg = str(e)
            if "429" in msg and attempt < retries - 1:
                wait = 60 * (2 ** attempt)   # 60 s, 120 s
                print(f"    [Judge] 429 on {label} - waiting {wait}s ...")
                time.sleep(wait)
            else:
                print(f"    [Judge] {label} error: {e}")
                return None
    return None


def judge_evaluate(
    results: list[dict],
    eval_model: str,
    model_key: str = "llama",
    call_delay: float = 5.0,
) -> list[dict]:
    """
    LLM-as-a-Judge: score each result for Correctness and Conciseness.

    Correctness (0-1, normalised from 1-5):
      Does the answer cover all key facts from the ground truth?
      Only scored for answerable (non-impossible) questions.

    Conciseness (0-1, normalised from 1-5):
      Is the answer focused without unnecessary text?
      Scored for all non-error answers regardless of is_impossible.

    call_delay: seconds to sleep between API calls (avoids 429 rate limits).
    """
    if eval_model == "rouge":
        for r in results:
            r["judge_correctness"] = None
            r["judge_conciseness"] = None
        return results

    print(f"  [Judge] Loading judge LLM ({eval_model}) ...")
    llm = build_judge_llm(eval_model, model_key)

    for i, r in enumerate(results, 1):
        r["judge_correctness"] = None
        r["judge_conciseness"] = None

        answer = r.get("answer", "")
        if not answer or answer.startswith("ERROR"):
            continue

        # -- Correctness (answerable questions only) ----------------------
        if not r.get("is_impossible") and r.get("ground_truth"):
            prompt = _CORRECTNESS_PROMPT.format(
                question=r["question"],
                ground_truth=r["ground_truth"][:1000],
                answer=answer[:1000],
            )
            r["judge_correctness"] = _judge_call(llm, prompt, f"correctness Q{i}")
            time.sleep(call_delay)

        # -- Conciseness (all non-error answers) --------------------------
        prompt = _CONCISENESS_PROMPT.format(
            question=r["question"],
            answer=answer[:1000],
        )
        r["judge_conciseness"] = _judge_call(llm, prompt, f"conciseness Q{i}")
        time.sleep(call_delay)

        if i % 5 == 0:
            print(f"    Judge: {i}/{len(results)} done")

    return results


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def write_results_csv(all_rows: list[dict], path: Path):
    """Write per-question results for every config."""
    if not all_rows:
        return
    fieldnames = [
        "config", "chunking", "model", "memory",
        "question_id", "contract_title", "is_impossible",
        "question", "ground_truth", "answer",
        "standalone_question", "latency_s",
        "input_tokens", "output_tokens",
        "faithfulness", "answer_relevancy", "context_precision", "context_recall", "rouge_l",
        "judge_correctness", "judge_conciseness",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nResults saved -> {path}")


def write_summary_csv(summary_rows: list[dict], path: Path):
    """Write one aggregated row per config."""
    if not summary_rows:
        return
    fieldnames = list(summary_rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Summary saved  -> {path}")


def aggregate(rows: list[dict], metric_keys: list[str]) -> dict[str, Any]:
    """Compute mean for each metric key, ignoring None values."""
    out = {}
    for key in metric_keys:
        vals = [r[key] for r in rows if r.get(key) is not None]
        out[f"avg_{key}"] = round(sum(vals) / len(vals), 4) if vals else None
    out["avg_latency_s"] = round(
        sum(r["latency_s"] for r in rows) / len(rows), 2
    ) if rows else None
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RAGAS evaluation for Legal RAG thesis")
    parser.add_argument("--cuad_json", default="data/CUADv1.json",
                        help="Path to CUADv1.json (relative to project root or absolute)")
    parser.add_argument("--sample", type=int, default=100,
                        help="Number of questions to evaluate (default: 100)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--k_docs", type=int, default=5)
    parser.add_argument("--k_messages", type=int, default=5)

    # Config selection
    parser.add_argument("--all_configs", action="store_true",
                        help="Run all 12 configurations sequentially")
    parser.add_argument("--chunking", choices=["fixed", "recursive", "semantic"],
                        default="recursive")
    parser.add_argument("--model", choices=["llama", "mistral"], default="llama")
    parser.add_argument("--memory", choices=["windowed", "summary"], default="windowed")

    # Evaluator LLM
    parser.add_argument(
        "--eval_model", choices=["openai", "nvidia", "local", "rouge"], default=None,
        help=(
            "RAGAS evaluator LLM: "
            "'nvidia' (Llama 3.1 70B via NVIDIA NIM, needs NVIDIA_API_KEY - recommended), "
            "'openai' (gpt-4o-mini, needs OPENAI_API_KEY), "
            "'local' (same HuggingFace model as --model, no API key), "
            "'rouge' (ROUGE-L only, no LLM). "
            "Auto-detects from available API keys if not specified."
        ),
    )

    # Re-run judge on an existing results CSV (skips RAG + RAGAS entirely)
    parser.add_argument(
        "--judge_only", metavar="RESULTS_CSV",
        help=(
            "Path to an existing eval_results CSV. Skips RAG chain and RAGAS - "
            "re-runs only LLM-as-a-Judge on the saved answers and overwrites the file."
        ),
    )

    # LLM-only baseline (section 2.6)
    parser.add_argument(
        "--baseline", action="store_true",
        help=(
            "Run the LLM-only baseline (no retrieval). "
            "Uses --model and --sample. Scores with ROUGE-L + LLM-as-a-Judge. "
            "Saves to results/baseline_results_<timestamp>.csv."
        ),
    )

    args = parser.parse_args()

    # Auto-detect evaluator from available keys
    if args.eval_model is None:
        if os.getenv("NVIDIA_API_KEY"):
            args.eval_model = "nvidia"
        elif os.getenv("OPENAI_API_KEY"):
            args.eval_model = "openai"
        else:
            args.eval_model = "local"
        print(f"  [RAGAS] Auto-selected eval_model: {args.eval_model}")

    # -- Judge-only mode: re-score an existing results CSV ----------------
    if args.judge_only:
        csv_path = Path(args.judge_only)
        if not csv_path.is_absolute():
            csv_path = ROOT / csv_path
        if not csv_path.exists():
            print(f"ERROR: results CSV not found at {csv_path}")
            sys.exit(1)

        print(f"Judge-only mode - loading {csv_path}")
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        # Convert string booleans/floats back to proper types
        for r in rows:
            r["is_impossible"] = r.get("is_impossible", "False").strip().lower() == "true"
            for col in ("latency_s", "faithfulness", "answer_relevancy",
                        "context_precision", "context_recall",
                        "judge_correctness", "judge_conciseness"):
                val = r.get(col, "")
                try:
                    r[col] = float(val) if val not in ("", "None") else None
                except ValueError:
                    r[col] = None

        model_key = rows[0].get("model", args.model) if rows else args.model
        scored = judge_evaluate(rows, eval_model=args.eval_model, model_key=model_key)

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(scored[0].keys()),
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(scored)
        print(f"Judge scores written back to {csv_path}")

        judge_keys = ["judge_correctness", "judge_conciseness"]
        agg = aggregate(scored, judge_keys)
        print(f"Judge averages: {agg}")
        sys.exit(0)

    # Resolve CUAD JSON path
    cuad_path = Path(args.cuad_json)
    if not cuad_path.is_absolute():
        cuad_path = ROOT / cuad_path
    if not cuad_path.exists():
        print(f"\nERROR: CUAD JSON not found at {cuad_path}")
        print("Download CUADv1.json from https://github.com/TheAtticusProject/cuad")
        print("and place it at data/CUADv1.json inside the project root.")
        sys.exit(1)

    # Load & sample questions
    print(f"Loading CUAD from {cuad_path} ...")
    all_records = load_cuad(str(cuad_path))
    print(f"  Total QA pairs: {len(all_records)}")
    questions = sample_questions(all_records, args.sample, seed=args.seed)
    print(f"  Sampled {len(questions)} questions "
          f"({sum(1 for q in questions if not q['is_impossible'])} answerable, "
          f"{sum(1 for q in questions if q['is_impossible'])} impossible)")

    # -- Baseline mode (section 2.6): LLM only, no retrieval --------------
    if args.baseline:
        print(f"\n{'='*60}")
        print(f"LLM-only baseline - model={args.model}")
        print(f"{'='*60}")

        raw = run_baseline(model_key=args.model, questions=questions)

        # ROUGE-L between answer and ground truth
        for r in raw:
            r["rouge_l"] = _rouge_l(r["answer"], r["ground_truth"])

        # Judge (correctness + conciseness) - no RAGAS since there's no context
        if args.eval_model == "local":
            import gc, torch
            gc.collect()
            torch.cuda.empty_cache()

        raw = judge_evaluate(raw, eval_model=args.eval_model, model_key=args.model)

        config_name = f"baseline_{args.model}"
        for i, row in enumerate(raw):
            row["config"]      = config_name
            row["chunking"]    = "none"
            row["model"]       = args.model
            row["memory"]      = "none"
            row["question_id"] = questions[i]["id"]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_path = RESULTS_DIR / f"baseline_results_{timestamp}.csv"
        write_results_csv(raw, base_path)

        agg = aggregate(raw, ["rouge_l", "judge_correctness", "judge_conciseness"])
        print(f"\nBaseline averages: {agg}")
        print("\nCompare judge_correctness here against RAG results to quantify RAG benefit.")
        sys.exit(0)

    # Determine metric keys (use_ragas decided per-config for local eval)
    use_ragas_flag = args.eval_model != "rouge"
    ragas_metric_keys = (
        ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
        if use_ragas_flag else ["rouge_l"]
    )
    judge_metric_keys = (
        ["judge_correctness", "judge_conciseness"]
        if args.eval_model != "rouge" else []
    )
    token_metric_keys = ["input_tokens", "output_tokens"]
    metric_keys = ragas_metric_keys + judge_metric_keys + token_metric_keys

    # Configurations to run
    if args.all_configs:
        configs = list(product(
            ["fixed", "recursive", "semantic"],
            ["llama", "mistral"],
            ["windowed", "summary"],
        ))
    else:
        configs = [(args.chunking, args.model, args.memory)]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_path = RESULTS_DIR / f"eval_results_{timestamp}.csv"
    summary_path = RESULTS_DIR / f"eval_summary_{timestamp}.csv"

    all_result_rows: list[dict] = []
    summary_rows:    list[dict] = []

    for chunking, model_key, memory_type in configs:
        config_name = f"{chunking}_{model_key}_{memory_type}"
        print(f"\n{'='*60}")
        print(f"Config: {config_name}")
        print(f"{'='*60}")

        raw_results = run_config(
            chunking, model_key, memory_type, questions,
            k_docs=args.k_docs, k_messages=args.k_messages,
        )

        # For local eval: free the RAG chain's GPU memory before loading the
        # evaluator LLM - both are 8B models and won't fit in VRAM simultaneously.
        if args.eval_model == "local":
            import gc, torch
            gc.collect()
            torch.cuda.empty_cache()
            print("  GPU memory freed - loading evaluator LLM ...")

        metrics, use_ragas = build_ragas_metrics(
            eval_model=args.eval_model,
            model_key=model_key,
        )

        print("  Running RAGAS evaluation ...")
        scored = ragas_evaluate(raw_results, metrics, use_ragas)

        # Free RAGAS evaluator LLM before judge LLM loads (local mode only)
        if args.eval_model == "local":
            import gc, torch
            del metrics
            gc.collect()
            torch.cuda.empty_cache()

        print("  Running LLM-as-a-Judge evaluation ...")
        scored = judge_evaluate(scored, eval_model=args.eval_model, model_key=model_key)

        # Free judge LLM before next config's RAG chain loads
        if args.eval_model == "local":
            import gc, torch
            gc.collect()
            torch.cuda.empty_cache()

        # Tag each row with config info
        for i, row in enumerate(scored):
            row["config"]      = config_name
            row["chunking"]    = chunking
            row["model"]       = model_key
            row["memory"]      = memory_type
            row["question_id"] = questions[i]["id"]
        all_result_rows.extend(scored)

        agg = aggregate(scored, metric_keys)
        summary_rows.append({"config": config_name, "chunking": chunking,
                              "model": model_key, "memory": memory_type,
                              "n_questions": len(scored), **agg})

        print(f"  Averages: {agg}")

        # Flush after each config so results aren't lost on crash
        write_results_csv(all_result_rows, results_path)
        write_summary_csv(summary_rows, summary_path)

    print(f"\nDone. {len(configs)} config(s) evaluated on {len(questions)} questions.")


if __name__ == "__main__":
    main()
