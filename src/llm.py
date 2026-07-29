"""
llm.py

Loads local HuggingFace LLMs (Llama 3.1 8B Instruct / Mistral 7B Instruct)
with 4-bit NF4 quantization via bitsandbytes so they fit on a single consumer GPU.

Usage:
    from llm import load_llm
    llm = load_llm("llama")   # or "mistral"
"""

import os
import torch
from dotenv import load_dotenv
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    pipeline,
)
from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline

load_dotenv()

# HuggingFace model IDs for the two LLMs being compared in the thesis
MODELS = {
    "llama":   "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistral": "mistralai/Mistral-7B-Instruct-v0.3",
}


def _check_cuda():
    if not torch.cuda.is_available():
        raise EnvironmentError(
            "No CUDA GPU detected. Running Llama 3.1 8B or Mistral 7B on CPU is "
            "impractically slow. Please run on a machine with a CUDA-capable GPU "
            "(at least 6 GB VRAM with 4-bit quantization)."
        )
    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"  GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)")


def load_llm(
    model_key: str,
    quantize_4bit: bool = True,
    max_new_tokens: int = 512,
    temperature: float = 0.1,
) -> HuggingFacePipeline:
    """
    Download (or load from cache) a local LLM and wrap it for LangChain.

    4-bit NF4 quantization is on by default - it reduces memory from ~16 GB to
    ~5 GB for an 8B model with negligible quality loss for extractive legal tasks.

    Args:
        model_key:      'llama' or 'mistral'
        quantize_4bit:  Use bitsandbytes NF4 quantization (requires CUDA)
        max_new_tokens: Maximum tokens to generate per answer
        temperature:    Sampling temperature - keep low (0.1) for legal accuracy

    Returns:
        A LangChain HuggingFacePipeline ready to use in a chain
    """
    if model_key not in MODELS:
        raise ValueError(
            f"Unknown model '{model_key}'. Choose from: {list(MODELS.keys())}"
        )

    model_id = MODELS[model_key]
    hf_token = os.getenv("HF_TOKEN")

    if not hf_token:
        print(
            "Warning: HF_TOKEN not set in .env. "
            "This is required for gated models (Llama 3.1). "
            "Set HF_TOKEN=<your_token> in your .env file."
        )

    print(f"\nLoading '{model_key}' - {model_id}")
    _check_cuda()

    # ------------------------------------------------------------------ #
    # Tokenizer                                                            #
    # ------------------------------------------------------------------ #
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        token=hf_token,
        trust_remote_code=False,
    )

    # Llama 3.1 has no pad token by default - required for batched generation
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # ------------------------------------------------------------------ #
    # Quantization config (4-bit NF4 - best quality-per-bit for LLMs)    #
    # ------------------------------------------------------------------ #
    bnb_config = None
    if quantize_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,   # extra ~0.4 bits saved
            bnb_4bit_quant_type="nf4",        # best for normally-distributed weights
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        print("  Quantization: 4-bit NF4 (bitsandbytes)")
    else:
        print("  Quantization: none (bfloat16 full precision)")

    # ------------------------------------------------------------------ #
    # Model                                                                #
    # ------------------------------------------------------------------ #
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        device_map="auto",                    # spreads across available GPUs/CPU
        torch_dtype=torch.bfloat16 if not quantize_4bit else None,
        token=hf_token,
        trust_remote_code=False,
    )
    model.eval()

    # ------------------------------------------------------------------ #
    # Pipeline                                                             #
    # ------------------------------------------------------------------ #
    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        do_sample=temperature > 0,
        repetition_penalty=1.1,   # reduces repetitive boilerplate in legal answers
        return_full_text=False,   # return only new tokens, not the echoed prompt
        pad_token_id=tokenizer.eos_token_id,
    )

    hf_pipeline = HuggingFacePipeline(pipeline=pipe)

    # ChatHuggingFace wraps the pipeline and automatically applies the
    # tokenizer's chat_template (e.g. Llama 3.1's <|begin_of_text|> / <|eot_id|>
    # tokens, Mistral's [INST]...[/INST] format).
    # Without this, instruction-tuned models echo the prompt back into the answer.
    print(f"  '{model_key}' ready.\n")
    return ChatHuggingFace(llm=hf_pipeline)


if __name__ == "__main__":
    # Quick sanity check - loads Mistral (smaller download) and runs one inference
    print("Loading Mistral for smoke test...")
    llm = load_llm("mistral", max_new_tokens=64)
    response = llm.invoke("What is a governing law clause in a contract?")
    print(f"\nResponse:\n{response}")
