"""
app.py  -  Streamlit UI for the Legal RAG Assistant

Lets you interactively switch between every experimental axis from the thesis:
  - Chunking strategy : fixed | recursive | semantic
  - LLM               : llama (3.1 8B) | mistral (7B)
  - Memory type       : windowed | summary
  - Retrieval k       : number of chunks retrieved per query

Retrieval is hybrid: contract-scoped dense similarity search combined with a
BM25 keyword index, merged and deduplicated. See rag_chain.RAGChain for details.

LLMs and vectorstores are cached so switching one axis does not reload the other.
"""

import os
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Ensure all sibling modules (llm, retriever, rag_chain) are importable
# regardless of whether Streamlit is launched from the project root or src/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ------------------------------------------------------------------ #
# Page config  (must be the first Streamlit call)                     #
# ------------------------------------------------------------------ #

st.set_page_config(
    page_title="Legal RAG Assistant",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------ #
# Cached resource loaders                                             #
# cache_resource persists across reruns; only reloads on new params   #
# ------------------------------------------------------------------ #

@st.cache_resource(show_spinner=False)
def _load_llm(model_key: str):
    from llm import load_llm
    return load_llm(model_key)


@st.cache_resource(show_spinner=False)
def _load_retriever(chunking_strategy: str, k_docs: int, search_type: str):
    from retriever import get_retriever, get_embeddings
    embeddings = get_embeddings()
    return get_retriever(
        chunking_strategy,
        k=k_docs,
        search_type=search_type,
        embeddings=embeddings,
    )


@st.cache_resource(show_spinner=False)
def _load_bm25_retriever(chunking_strategy: str, k_docs: int):
    from retriever import get_bm25_retriever, get_embeddings
    embeddings = get_embeddings()
    return get_bm25_retriever(chunking_strategy, k=k_docs * 10, embeddings=embeddings)


# ------------------------------------------------------------------ #
# Helper - must be defined before the message-replay loop uses it     #
# ------------------------------------------------------------------ #

def _render_assistant_meta(msg: dict):
    """Render the retrieval-query caption and source expander for one assistant turn."""
    standalone_q = msg.get("standalone_q", "")
    original_q   = msg.get("original_q", "")
    sources      = msg.get("sources", [])

    # Show the reformulated retrieval query only when it differs from what the
    # user typed - this makes the memory's question-condensation step visible.
    if standalone_q and standalone_q != original_q:
        st.caption(f"🔍 Retrieval query: *\"{standalone_q}\"*")

    if sources:
        with st.expander(f"📄 Source Documents  ({len(sources)} chunks retrieved)"):
            for i, doc in enumerate(sources, 1):
                raw_source = doc.metadata.get("source", "unknown")
                filename = raw_source.replace("\\", "/").split("/")[-1]
                st.markdown(f"**Excerpt {i}** — `{filename}`")
                preview = doc.page_content.strip()
                if len(preview) > 500:
                    preview = preview[:500] + "…"
                st.text(preview)
                if i < len(sources):
                    st.divider()


# ------------------------------------------------------------------ #
# Session state defaults                                               #
# ------------------------------------------------------------------ #

def _init_state():
    defaults = {
        "messages":      [],    # {role, content, sources?, standalone_q?, original_q?}
        "chain":         None,  # active RAGChain instance
        "active_config": None,  # tuple describing the loaded config
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_state()

# ------------------------------------------------------------------ #
# Sidebar - configuration panel                                        #
# ------------------------------------------------------------------ #

with st.sidebar:
    st.title("⚙️ Configuration")

    if not os.getenv("HF_TOKEN"):
        st.warning(
            "**HF_TOKEN not set.**\n\n"
            "Add `HF_TOKEN=<your_token>` to your `.env` file — "
            "required for gated models (Llama 3.1).",
            icon="⚠️",
        )

    st.markdown("#### Model")
    model_key = st.selectbox(
        "LLM",
        ["llama", "mistral"],
        format_func=lambda x: (
            "Llama 3.1 8B" if x == "llama" else "Mistral 7B"
        ),
        help="Both models run locally with 4-bit NF4 quantization.",
    )

    st.markdown("#### Chunking Strategy")
    chunking_strategy = st.selectbox(
        "Strategy",
        ["fixed", "recursive", "semantic"],
        index=1,
        format_func=lambda x: {
            "fixed":     "Fixed",
            "recursive": "Recursive",
            "semantic":  "Semantic",
        }[x],
    )

    st.markdown("#### Memory")
    memory_type = st.selectbox(
        "Strategy",
        ["windowed", "summary"],
        format_func=lambda x: (
            "Windowed  (last k turns)"
            if x == "windowed"
            else "Conversation Summary  (LLM-compressed)"
        ),
        help=(
            "Windowed keeps the exact text of the last k turns.\n"
            "Summary compresses the full history into a short paragraph."
        ),
    )
    k_messages = st.slider(
        "Memory window  k  (turns)",
        min_value=1,
        max_value=10,
        value=5,
        disabled=(memory_type == "summary"),
        help="Only applies to Windowed memory.",
    )

    st.markdown("#### Retrieval")
    k_docs = st.slider("Chunks to retrieve  (k)", min_value=2, max_value=10, value=5)
    search_type = "mmr"

    st.markdown("---")

    col_load, col_clear = st.columns(2)

    with col_load:
        load_clicked = st.button(
            "🚀 Load Chain",
            use_container_width=True,
            help="LLMs are cached — switching chunking strategy does not reload the model.",
        )
    with col_clear:
        clear_clicked = st.button(
            "🗑️ Clear Chat",
            use_container_width=True,
            help="Resets conversation memory and chat history.",
        )

    if load_clicked:
        from rag_chain import RAGChain

        with st.spinner(f"Loading {model_key.capitalize()} (cached after first load)…"):
            llm = _load_llm(model_key)

        with st.spinner(f"Loading '{chunking_strategy}' vectorstore…"):
            retriever = _load_retriever(chunking_strategy, k_docs, search_type)

        with st.spinner("Building BM25 index (first load only)…"):
            bm25_retriever = _load_bm25_retriever(chunking_strategy, k_docs)

        st.session_state.chain = RAGChain(
            retriever=retriever,
            llm=llm,
            memory_type=memory_type,
            k_messages=k_messages,
            bm25_retriever=bm25_retriever,
            trace_metadata={
                "chunking_strategy": chunking_strategy,
                "model": model_key,
                "memory_type": memory_type,
                "k_messages": k_messages,
                "k_docs": k_docs,
                "search_type": search_type,
                "source": "streamlit-ui",
            },
        )
        st.session_state.messages = []
        st.session_state.active_config = (
            model_key, chunking_strategy, memory_type, k_messages, k_docs
        )
        st.success("Chain ready — start chatting!", icon="✅")

    if clear_clicked:
        if st.session_state.chain:
            st.session_state.chain.clear_memory()
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("#### Status")
    if st.session_state.active_config:
        cfg = st.session_state.active_config
        model_label  = "Llama 3.1 8B" if cfg[0] == "llama" else "Mistral 7B"
        memory_label = "Windowed" if cfg[2] == "windowed" else "Summary"
        st.success("✅  Chain loaded")
        st.caption(
            f"**Model:** {model_label}  \n"
            f"**Chunking:** {cfg[1]}  \n"
            f"**Memory:** {memory_label}  \n"
            f"**k_docs:** {cfg[4]}"
        )
    else:
        st.info("No chain loaded.\nClick **🚀 Load Chain** to begin.", icon="ℹ️")


# ------------------------------------------------------------------ #
# Main chat area                                                       #
# ------------------------------------------------------------------ #

st.title("⚖️ Legal RAG Assistant")
st.markdown(
    "<p style='font-size:1.25rem; color:#9aa0a6; margin-top:-0.25rem;'>"
    "Ask questions about the 510 CUAD commercial contracts. "
    "Answers are grounded exclusively in the retrieved contract excerpts."
    "</p>",
    unsafe_allow_html=True,
)

if not st.session_state.chain:
    st.markdown(
        """
        <div style="background-color: rgba(28,131,225,0.10); border-radius: 0.5rem;
                    padding: 1rem 1.25rem; line-height: 1.6;">
          <div style="font-size: 1.5rem; font-weight: 700; margin-bottom: 0.4rem;">
            👈 Getting started
          </div>
          <ol style="font-size: 1.25rem; margin: 0 0 0 1.4rem; padding: 0;">
            <li>Pick a configuration in the sidebar.</li>
            <li>Click 🚀 <strong>Load Chain</strong> (the first load downloads the
                model, subsequent loads are instant).</li>
            <li>Ask questions about the contracts below.</li>
          </ol>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

# Replay existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            _render_assistant_meta(msg)

# New user input
if user_input := st.chat_input("Ask a question about the contracts…"):

    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        with st.spinner("Retrieving and generating answer…"):
            result = st.session_state.chain.chat(user_input)

        answer       = result["answer"]
        sources      = result.get("source_documents", [])
        standalone_q = result.get("standalone_question", user_input)

        st.markdown(answer)

        assistant_msg = {
            "role":         "assistant",
            "content":      answer,
            "sources":      sources,
            "standalone_q": standalone_q,
            "original_q":   user_input,
        }
        _render_assistant_meta(assistant_msg)

    st.session_state.messages.append(assistant_msg)
