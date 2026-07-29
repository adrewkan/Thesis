"""
rag_chain.py

Conversational RAG chain for legal document Q&A.

Each RAGChain instance pairs:
  - A retriever (one of: fixed / recursive / semantic chunking)
  - A local LLM  (one of: llama / mistral)
  - A memory strategy (one of: windowed / summary)

This covers all experimental dimensions from the thesis:
  3 chunking x 2 LLMs x 2 memory types = 12 configurations total.

Usage:
    from retriever import get_retriever
    from llm      import load_llm
    from rag_chain import RAGChain

    llm      = load_llm("llama")
    retriever = get_retriever("recursive")
    chain    = RAGChain(retriever, llm, memory_type="windowed", k_messages=5)

    result = chain.chat("What is the governing law?")
    print(result["answer"])
    for doc in result["source_documents"]:
        print(doc.metadata["source"])
"""

import os
import re
import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# ---------------------------------------------------------------------------
# Langfuse client - initialised once, None if keys are missing
# ---------------------------------------------------------------------------

_langfuse = None

def _get_langfuse():
    """Return a shared Langfuse client, or None if keys are not configured."""
    global _langfuse
    if _langfuse is not None:
        return _langfuse
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sec = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not pub or not sec:
        return None
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=pub,
            secret_key=sec,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception:
        pass
    return _langfuse


# ------------------------------------------------------------------ #
# Prompt Templates                                                     #
# ------------------------------------------------------------------ #

# Reformulates a follow-up question into a self-contained retrieval query.
# This is critical for conversational RAG: the retriever has no memory, so
# "What about the termination clause?" must become "What is the termination
# clause in the contract previously discussed?"
CONDENSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful assistant. Your only task is to rephrase a follow-up "
     "question into a standalone question that can be understood without the "
     "conversation history. Output only the rephrased question, nothing else. "
     "If the conversation history mentions a contract by its exact filename "
     "(e.g. COMPANYNAME_DATE-EX-NUMBER-AGREEMENT NAME), preserve that exact "
     "filename in double quotes in the standalone question."),
    ("human",
     "Conversation history:\n{chat_history}\n\n"
     "Follow-up question: {question}\n\n"
     "Standalone question:"),
])

# Main QA prompt - system message carries the instructions, human message
# carries the context + question.  Using ChatPromptTemplate ensures the model
# receives its own native chat tokens (Llama's <|begin_of_text|> / <|eot_id|>,
# Mistral's [INST]...[/INST]) so it knows exactly where to start and stop.
QA_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a legal assistant performing extractive question answering on contracts.\n\n"
     "Each excerpt is labelled with its source filename, e.g. [Excerpt 1 — CONTRACTNAME.txt].\n"
     "If the question names a specific contract, use ONLY excerpts from that contract.\n\n"
     "HOW TO INTERPRET THE QUESTIONS:\n"
     "Questions follow the pattern: 'Highlight parts related to CATEGORY'. "
     "The Details field explains what CATEGORY means. "
     "Find and quote the exact text from the excerpts that represents that category.\n\n"
     "CRITICAL RULES:\n"
     "- Do NOT look for a field literally labelled with the category name.\n"
     "- Find the text that REPRESENTS that concept and quote it directly.\n"
     "- For 'Document Name': quote ONLY the title line (e.g. 'Manufacturing Agreement'). "
     "Do NOT quote the opening paragraph or party names. One line is enough. "
     "If you can read a document title, QUOTE IT — never say "
     "'Not found' for Document Name if a title is visible.\n"
     "- For 'Parties': quote the names of the companies or individuals listed "
     "as parties (e.g. 'Between Antares Pharma, Inc. and ...').\n"
     "- For 'Governing Law': quote the clause stating which state/country law applies.\n"
     "- For 'Expiration Date' or 'Renewal Term': quote termination or renewal clauses "
     "even if they do not use the word 'expiration'.\n\n"
     "WHEN TO ANSWER VS. DECLINE: Reply with "
     "'Not found: this contract does not appear to contain a [CATEGORY] clause.' "
     "ONLY when the excerpts contain no clause related to the category at all. "
     "If a related clause IS present but does not state the exact value asked for "
     "(for example a specific date, amount, or duration), still QUOTE that clause "
     "as the answer -- do not decline just because a precise value is missing. "
     "Do NOT speculate, infer, or paraphrase unrelated sections. "
     "ANSWER DIRECTLY: when a relevant clause is present, lead with it and commit "
     "to it as the answer. Do NOT hedge with phrases such as 'it is not explicitly "
     "stated', 'this could potentially', 'this might be relevant', or 'a lawyer "
     "should review to determine whether this qualifies', and do NOT list several "
     "possibly-relevant clauses with uncertainty -- give the single most relevant "
     "quote. Evasive, non-committal phrasing makes an otherwise correct answer "
     "score as no answer at all. "
     "KEEP THE ANSWER FOCUSED: quote only the minimal span that answers the "
     "question -- the specific sentence or clause -- not the whole excerpt. Leave "
     "out surrounding material such as tables, addresses, section headers, or "
     "unrelated disclaimers that happen to appear in the same excerpt. After the "
     "quote, do NOT add explanation, commentary, or recommendations. "
     "Be concise. Stop after answering."),
    ("human",
     "Contract Excerpts:\n{context}\n\n"
     "Conversation History:\n{chat_history}\n\n"
     "Question: {question}"),
])

# Prompt for the summary memory strategy - compresses conversation history
# while preserving key legal facts (clause names, parties, dates, etc.)
SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are a helpful assistant that summarizes legal Q&A conversations. "
     "Structure the summary as a numbered list of exchanges: "
     "'Q1: [what the user asked] → A1: [what you answered]. Q2: ...' and so on. "
     "Preserve key legal details in the answers. Output only the updated summary."),
    ("human",
     "Previous summary:\n{summary}\n\n"
     "Latest exchange:\n"
     "Human: {question}\n"
     "Assistant: {answer}\n\n"
     "Updated summary:"),
])


# ------------------------------------------------------------------ #
# RAGChain                                                             #
# ------------------------------------------------------------------ #

class RAGChain:
    """
    Conversational RAG chain for legal document Q&A.

    Memory strategies
    -----------------
    windowed : keeps the last `k_messages` human/AI turns verbatim.
               Simple, guarantees exact recall of recent context,
               but older turns are lost.

    summary  : uses the LLM to maintain a running summary of the full
               conversation. Token-efficient but loses fine-grained detail
               from older turns.
    """

    def __init__(
        self,
        retriever,
        llm,
        memory_type: str = "windowed",
        k_messages: int = 5,
        bm25_retriever=None,
        trace_metadata: dict = None,
    ):
        """
        Args:
            retriever:      A LangChain VectorStoreRetriever (from retriever.py)
            llm:            A HuggingFacePipeline LLM (from llm.py)
            memory_type:    'windowed' or 'summary'
            k_messages:     Number of past turns kept (windowed mode only)
            bm25_retriever: Optional BM25Retriever for hybrid keyword+semantic search
            trace_metadata: Dict of config info attached to every Langfuse trace
                            (e.g. chunking_strategy, model, memory_type)
        """
        if memory_type not in ("windowed", "summary"):
            raise ValueError("memory_type must be 'windowed' or 'summary'")

        self.retriever = retriever
        self.bm25_retriever = bm25_retriever
        self.llm = llm
        self.memory_type = memory_type
        self.k_messages = k_messages
        self._trace_metadata = trace_metadata or {}

        # Full turn-by-turn history - always kept regardless of memory type
        # so callers can inspect the complete conversation
        self._history: list[tuple[str, str]] = []

        # Running summary text - updated after each turn in summary mode
        self._summary: str = ""

        # Cache of every chunk in this chain's vector store, pulled once and
        # reused for contract-scoped BM25 (see _get_all_docs).
        self._all_docs_cache = None

        self._parser = StrOutputParser()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def chat(self, question: str) -> dict:
        """
        Process one conversational turn end-to-end.

        Steps:
          1. Build the chat history string from memory
          2. Condense the follow-up question -> standalone retrieval query
          3. Retrieve relevant contract chunks
          4. Generate an answer grounded in the retrieved context
          5. Update memory (windowed: automatic; summary: LLM call)

        Returns:
            answer            : str   - the LLM's answer
            source_documents  : list  - retrieved LangChain Documents
            standalone_question: str  - the reformulated query used for retrieval
            chat_history_used : str   - the history string passed to the LLM
        """
        lf = _get_langfuse()
        trace_id = lf.create_trace_id() if lf else None

        chat_history = self._get_chat_history()

        # Step 1: Condense follow-up question -> standalone query
        standalone_q = self._condense_question(question, chat_history)

        # Step 2: Retrieve relevant contract chunks
        t0_retrieve = time.time()
        docs = self._retrieve_docs(standalone_q, question)
        retrieve_latency = time.time() - t0_retrieve
        context = self._format_docs(docs)

        # Step 3: Generate grounded answer
        t0_gen = time.time()
        qa_chain = QA_PROMPT | self.llm | self._parser
        answer = qa_chain.invoke({
            "context": context,
            "chat_history": chat_history,
            "question": question,
        }).strip()
        answer = self._clean_answer(answer)
        gen_latency = time.time() - t0_gen

        # Step 4: Update memory
        self._history.append((question, answer))
        if self.memory_type == "summary":
            self._update_summary(question, answer)

        # Step 5: Count tokens (always - used for both Langfuse and CSV).
        # ChatHuggingFace(llm=HuggingFacePipeline(pipeline=pipe)) - the real
        # HF pipeline is two layers in.
        input_tokens = None
        output_tokens = None
        try:
            tokenizer = self.llm.llm.pipeline.tokenizer
            prompt_text = context + "\n" + chat_history + "\n" + question
            input_tokens = len(tokenizer.encode(prompt_text))
            output_tokens = len(tokenizer.encode(answer))
        except Exception as exc:
            print(f"  [tokens] counting failed: {exc}")

        # Step 6: Log trace to Langfuse (Langfuse SDK v4 API)
        if lf and trace_id:
            try:
                root = lf.start_observation(
                    name="legal-rag-chat",
                    as_type="chain",
                    trace_context={"trace_id": trace_id},
                    input=question,
                    metadata=self._trace_metadata,
                )

                root.start_observation(
                    name="retrieval",
                    as_type="retriever",
                    input=standalone_q,
                    output=[
                        {
                            "source": d.metadata.get("source", "").split("/")[-1].split("\\")[-1],
                            "preview": d.page_content[:200],
                        }
                        for d in docs
                    ],
                    metadata={
                        "n_chunks": len(docs),
                        "latency_s": round(retrieve_latency, 3),
                    },
                ).end()

                gen_kwargs: dict = {
                    "name":     "llm-generation",
                    "as_type":  "generation",
                    "input":    question,
                    "output":   answer,
                    "model":    self._trace_metadata.get("model", "unknown"),
                    "metadata": {"latency_s": round(gen_latency, 3)},
                }
                if input_tokens is not None and output_tokens is not None:
                    gen_kwargs["usage_details"] = {
                        "input":  input_tokens,
                        "output": output_tokens,
                    }

                root.start_observation(**gen_kwargs).end()
                root.update(output=answer).end()
                lf.flush()
            except Exception:
                pass

        return {
            "answer": answer,
            "source_documents": docs,
            "standalone_question": standalone_q,
            "chat_history_used": chat_history,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def clear_memory(self):
        """Reset conversation state (call between independent sessions)."""
        self._history.clear()
        self._summary = ""

    @property
    def history(self) -> list[tuple[str, str]]:
        """Read-only view of the full conversation history."""
        return list(self._history)

    # ------------------------------------------------------------------ #
    # Memory helpers                                                       #
    # ------------------------------------------------------------------ #

    def _get_chat_history(self) -> str:
        """Return the chat history string for the current memory strategy."""
        if not self._history:
            return ""

        if self.memory_type == "windowed":
            recent = self._history[-self.k_messages:]
            lines = []
            for human, ai in recent:
                lines.append(f"Human: {human}")
                lines.append(f"Assistant: {ai}")
            return "\n".join(lines)

        else:  # summary
            return (
                f"Conversation summary:\n{self._summary}"
                if self._summary
                else ""
            )

    def _update_summary(self, question: str, answer: str):
        """Run the LLM to update the running conversation summary."""
        summary_chain = SUMMARY_PROMPT | self.llm | self._parser
        self._summary = summary_chain.invoke({
            "summary": self._summary,
            "question": question,
            "answer": answer,
        }).strip()

    # ------------------------------------------------------------------ #
    # Chain helpers                                                        #
    # ------------------------------------------------------------------ #

    # Phrases the LLM sometimes appends even after giving a valid answer
    _FALLBACK_PHRASES = [
        "The provided contracts do not contain information about this.",
        "The retrieved excerpts do not include the specified contract.",
    ]

    def _clean_answer(self, answer: str) -> str:
        """
        Remove a contradictory fallback phrase if real content precedes it.

        Llama 3.1 8B sometimes appends the 'not found' phrase at the end of a
        valid answer. Strip it only when there is substantive content before it.
        """
        for phrase in self._FALLBACK_PHRASES:
            if phrase in answer:
                before = answer[: answer.index(phrase)].strip()
                if before:           # real content exists -> drop the trailing phrase
                    return before
        return answer

    # CUAD metadata categories that are always found near the top of a contract
    _TOP_OF_DOC_CATEGORIES = {
        "document name", "parties", "agreement date", "effective date",
        "date", "contract name", "title",
    }

    # Matches CUAD boilerplate: "Highlight the parts (if any) of this contract
    # related to "<Category>" that should be reviewed by a lawyer. Details: ..."
    _CUAD_RE = re.compile(
        r'related\s+to\s+"([^"]+)".*?Details:\s*(.+)',
        re.IGNORECASE | re.DOTALL,
    )

    # Legal synonyms per CUAD category - appended to BM25 queries only.
    # Bridges the gap between category names and how clauses are actually worded
    # in contracts (e.g. "Expiration Date" -> contracts say "terminate upon notice").
    _CUAD_SYNONYMS: dict[str, str] = {
        "Expiration Date":                   "terminate termination expire end of term notice period duration",
        "Renewal Term":                      "renew renewal extension automatic continuation evergreen",
        "Notice Period to Terminate Renewal":"cancellation notice non-renewal opt-out termination notice",
        "Governing Law":                     "construed governed jurisdiction applicable law laws of the state",
        "Termination for Convenience":       "terminate at will without cause convenience termination right",
        "Anti-Assignment":                   "assign assignment transfer successor novation consent required",
        "Change of Control":                 "merger acquisition change of control takeover sale of company",
        "Exclusivity":                       "exclusive exclusivity sole supplier preferred non-compete restrictions",
        "Non-Compete":                       "compete competition competing business restraint of trade",
        "No-Solicit of Customers":           "solicit solicitation poach customers client non-solicitation",
        "No-Solicit of Employees":           "solicit hire employees poach staff non-solicitation",
        "Non-Disparagement":                 "disparage defame negative statements reputation",
        "Source Code Escrow":                "escrow source code deposit software escrow release",
        "Audit Rights":                      "audit inspection examine records review books access",
        "Cap on Liability":                  "liability cap maximum liability limit ceiling aggregate",
        "Uncapped Liability":                "unlimited liability no cap without limitation full liability",
        "Liquidated Damages":                "liquidated damages penalty predetermined fixed damages",
        "Insurance":                         "insurance coverage policy indemnification insure maintain",
        "Minimum Commitment":                "minimum payment minimum purchase minimum order floor commitment",
        "Revenue/Profit Sharing":            "revenue share profit sharing royalty commission percentage",
        "IP Ownership Assignment":           "intellectual property assign IP ownership work for hire invention",
        "License Grant":                     "license grant right to use sublicense permission",
        "Warranty Duration":                 "warranty guarantee warrants representation defect period",
        "Covenant Not to Sue":               "covenant not to sue release waiver claims discharge",
        "Third Party Beneficiary":           "third party beneficiary rights intended benefit",
        "Post-Termination Services":         "post-termination transition services wind-down survival",
        "Price Restrictions":                "price pricing restriction increase most favored nation MFN",
        "Most Favored Nation":               "most favored nation best price MFN pricing parity",
        "Volume Restriction":                "volume quantity restriction purchase limit cap usage",
        "Competitive Restriction Exception": "carve-out exception permitted activities competitive",
        "ROFR/ROFO/ROFN":                   "right of first refusal right of first offer first negotiation",
    }

    @staticmethod
    def _build_retrieval_query(question: str) -> str:
        """
        Produce a focused retrieval query from a CUAD-format question.

        CUAD questions follow the pattern:
          "Highlight the parts (if any) of this contract related to
           "<Category>" that should be reviewed by a lawyer. Details: ..."

        The boilerplate ("Highlight the parts...reviewed by a lawyer") adds noise
        to embedding similarity without adding meaning. Keeping only the clause
        category name and the Details description gives the vector store a much
        cleaner signal.

        Returns "<Category>: <Details>" for CUAD questions, or the original
        question unchanged for anything else.
        """
        m = RAGChain._CUAD_RE.search(question)
        if not m:
            return question
        category = m.group(1).strip()
        details = m.group(2).strip()
        # Collapse internal newlines in the Details blob
        details = re.sub(r"\s+", " ", details)
        return f"{category}: {details}"

    @staticmethod
    def _build_bm25_query(question: str) -> str:
        """
        Extend the focused retrieval query with legal synonyms for BM25 search.

        BM25 is a keyword matcher - it can't bridge vocabulary gaps on its own.
        Appending known synonyms for each CUAD category makes BM25 find clauses
        that are legally equivalent but worded differently from the category name
        (e.g. "Expiration Date" query finds "terminate upon 90 days notice" text).

        The synonyms are only appended for BM25; semantic search keeps the clean
        "Category: Details" query so embeddings are not diluted.
        """
        base = RAGChain._build_retrieval_query(question)
        m = RAGChain._CUAD_RE.search(question)
        if not m:
            return base
        category = m.group(1).strip()
        synonyms = RAGChain._CUAD_SYNONYMS.get(category, "")
        if synonyms:
            return f"{base} {synonyms}"
        return base

    def _retrieve_docs(self, query: str, original_question: str) -> list:
        """
        Retrieve chunks for a named contract.

        Strategy when a contract name is detected:
          1. Global similarity search (k*10 candidates) post-filtered to chunks
             whose source path matches the contract name.
          2. For metadata categories (Document Name, Parties, Date) that always
             appear at the top, prepend the first 2 filesystem chunks.
          3. Merge and deduplicate up to k results.

        Falls back to standard retrieval if no contract name is detected.
        """
        contract_name = (self._extract_contract_name(original_question)
                         or self._extract_contract_name(query))
        retrieval_query = self._build_retrieval_query(query)
        bm25_query = self._build_bm25_query(query)
        k = self.retriever.search_kwargs.get("k", 5)

        if contract_name:
            key = re.sub(r"[\s\-_.]", "", contract_name).lower()
            # Word-level fallback: significant words (5+ chars, non-generic) that
            # must all appear in the source - handles human-readable names like
            # "Antares Pharma, Inc. - Manufacturing Agreement" where the CUAD
            # filename has dates/numbers between the words.
            _GENERIC = {"agreement", "contract", "amendment", "exhibit", "annex"}
            key_words = [
                w.lower() for w in re.split(r"[\s\-_.,;]+", contract_name)
                if len(w) >= 5 and w.lower() not in _GENERIC
            ]

            def _matches(doc):
                src_raw = doc.metadata.get("source", "")
                src = re.sub(r"[\s\-_.]", "", src_raw).lower()
                if key in src or src in key:
                    return True
                if key_words:
                    src_lower = src_raw.lower()
                    return all(w in src_lower for w in key_words)
                return False

            # Header categories (Document Name, Parties, Agreement Date, etc.)
            # are always at the top of the contract, so skip vector search
            # entirely and load directly from the filesystem for speed and
            # reliability. Match the extracted CUAD category exactly rather than
            # testing whether any header word appears anywhere in the question,
            # which would misroute "Expiration Date" (contains "date") to the
            # top-of-document loader and miss the termination clause deeper in
            # the contract.

            m_cat = self._CUAD_RE.search(original_question)
            category = m_cat.group(1).strip().lower() if m_cat else ""
            is_header_category = category in self._TOP_OF_DOC_CATEGORIES
            if is_header_category:
                docs = self._load_from_filesystem(contract_name, k)
                if docs:
                    return docs


            # Semantic search over a large global pool, then filter to this contract
            vectorstore = self.retriever.vectorstore
            semantic = [
                d for d in vectorstore.similarity_search(retrieval_query, k=k * 10)
                if _matches(d)
            ]

            # Contract-scoped BM25 - always run so the legal-synonym keyword bridge
            # fires even when semantic search already returned k chunks. This is
            # what catches clauses worded differently from the category name
            # (e.g. an "Expiration Date" query finding "shall terminate upon 90
            # days notice"). The full-document scan is cached in _get_all_docs so
            # the cost is paid once per chain, not once per query.
            bm25_hits = []
            try:
                from langchain_community.retrievers import BM25Retriever
                contract_docs = [d for d in self._get_all_docs() if _matches(d)]
                if contract_docs:
                    local_bm25 = BM25Retriever.from_documents(contract_docs)
                    local_bm25.k = min(k * 2, len(contract_docs))
                    bm25_hits = local_bm25.invoke(bm25_query)
            except Exception:
                pass

            # Interleave semantic and BM25 so both retrievers contribute to the
            # final k, deduplicated.
            merged = self._interleave(semantic, bm25_hits, k)
            if merged:
                return merged

            # Last resort: filesystem read (covers contracts not yet in ChromaDB)
            return self._load_from_filesystem(contract_name, k)

        # No contract name detected - combine semantic + BM25 in parallel
        semantic_docs = self.retriever.invoke(retrieval_query)
        if self.bm25_retriever is None:
            return semantic_docs

        bm25_docs = self.bm25_retriever.invoke(bm25_query)
        return self._interleave(semantic_docs, bm25_docs, k)

    def _get_all_docs(self) -> list:
        """
        Return every chunk in this chain's vector store as LangChain Documents.

        Pulled once and cached on the instance. Used to build a contract-scoped
        BM25 index without re-scanning ChromaDB on every query. Fetched in
        batches because SQLite (ChromaDB's backend) caps SQL variables per query.
        """
        if self._all_docs_cache is not None:
            return self._all_docs_cache

        from langchain_core.documents import Document as LCDocument
        vectorstore = self.retriever.vectorstore
        BATCH = 5_000
        texts, metas = [], []
        offset = 0
        while True:
            batch = vectorstore.get(
                include=["documents", "metadatas"],
                limit=BATCH,
                offset=offset,
            )
            if not batch["documents"]:
                break
            texts.extend(batch["documents"])
            metas.extend(batch["metadatas"])
            offset += len(batch["documents"])
            if len(batch["documents"]) < BATCH:
                break

        self._all_docs_cache = [
            LCDocument(page_content=t, metadata=m or {})
            for t, m in zip(texts, metas)
        ]
        return self._all_docs_cache

    @staticmethod
    def _interleave(primary: list, secondary: list, k: int) -> list:
        """
        Merge two ranked lists by alternating between them, deduplicating on the
        first 80 characters of each chunk, and trimming to k results. The primary
        list (semantic search) is given the first slot at each round.
        """
        from itertools import zip_longest
        seen = set()
        merged = []
        for a, b in zip_longest(primary, secondary):
            for doc in (a, b):
                if doc is None:
                    continue
                sig = doc.page_content[:80]
                if sig in seen:
                    continue
                seen.add(sig)
                merged.append(doc)
                if len(merged) >= k:
                    return merged
        return merged

    def _load_from_filesystem(self, contract_name: str, k: int) -> list:
        """
        Read the contract file directly from disk and return its first k chunks.

        Used as a guaranteed fallback when vector search cannot find the contract.
        Returns chunks of ~1 500 chars starting from the top of the document
        (sufficient for CUAD questions about Document Name, Parties, Date, etc.)
        """
        import os
        from langchain_core.documents import Document

        key = re.sub(r"[\s\-_.]", "", contract_name).lower()

        for data_dir in ["./data/full_contract_txt", "/app/data/full_contract_txt"]:
            if not os.path.isdir(data_dir):
                continue
            for filename in os.listdir(data_dir):
                if not filename.endswith(".txt"):
                    continue
                file_key = re.sub(r"[\s\-_.]", "", filename[:-4]).lower()
                if key in file_key or file_key in key:
                    filepath = os.path.join(data_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        chunk_size = 1500
                        return [
                            Document(
                                page_content=content[i : i + chunk_size].strip(),
                                metadata={"source": filepath},
                            )
                            for i in range(0, min(len(content), chunk_size * k), chunk_size)
                        ][:k]
                    except OSError:
                        continue
        return []

    @staticmethod
    def _extract_contract_name(question: str) -> str | None:
        """
        Extract a CUAD contract filename from a question.

        Handles two CUAD formats:
          1. Quoted   - "LIMEENERGYCO_09_09_1999-EX-10-DISTRIBUTOR AGREEMENT"
          2. Unquoted - BNCMORTGAGEINC_05_17_1999-EX-10.4-LICENSING AND WEB
                        SITE HOSTING AGREEMENT__Document Name
        All CUAD filenames contain -EX- and end with AGREEMENT or CONTRACT.
        """
        # Format 1: inside double or single quotes - handles both _EX- and -EX- separators
        match = re.search(
            r'["\']([^"\']*[_\-]EX-[^"\']*?(?:AGREEMENT|CONTRACT))[^"\']*["\']',
            question, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Format 2: unquoted, followed by __ CUAD category separator
        # e.g. BNCMORTGAGEINC_05_17_1999-EX-10.4-LICENSING AND WEB SITE HOSTING AGREEMENT__Document Name
        # e.g. EtonPharmaceuticalsInc_20191114_10-Q_EX-10.1_11893941_EX-10.1_Development Agreement__Expiration Date
        match = re.search(
            r'([A-Z0-9][A-Z0-9_.\-]+[_\-]EX-[\w.\-]+[\w _\-]+(?:AGREEMENT|CONTRACT))(?=__)',
            question, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        # Format 3: human-readable name ending with Agreement/Contract, either
        # at the start of the question (evaluate.py injection format) or after
        # "this contract" (UI format).
        # e.g. "Antares Pharma, Inc. - Manufacturing Agreement" - Highlight...
        # e.g. ...this contract "Antares Pharma, Inc. - Manufacturing Agreement" related to...
        match = re.search(
            r'(?:^|contract\s+)"([^"]{4,}?(?:Agreement|Contract)s?)"',
            question, re.IGNORECASE
        )
        if match:
            return match.group(1).strip()

        return None

    def _condense_question(self, question: str, chat_history: str) -> str:
        """Reformulate a follow-up question into a standalone retrieval query."""
        if not chat_history:
            return question  # First turn - no history to resolve

        condense_chain = CONDENSE_PROMPT | self.llm | self._parser
        return condense_chain.invoke({
            "chat_history": chat_history,
            "question": question,
        }).strip()

    @staticmethod
    def _format_docs(docs) -> str:
        """Format retrieved Documents into a numbered context string."""
        if not docs:
            return "No relevant contract excerpts found."

        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "unknown")
            # Use just the filename for readability
            filename = source.split("/")[-1].split("\\")[-1]
            parts.append(
                f"[Excerpt {i} — {filename}]\n{doc.page_content.strip()}"
            )
        return "\n\n---\n\n".join(parts)


# ------------------------------------------------------------------ #
# Factory helper                                                       #
# ------------------------------------------------------------------ #

def build_rag_chain(
    chunking_strategy: str,
    model_key: str,
    memory_type: str = "windowed",
    k_messages: int = 5,
    k_docs: int = 5,
    search_type: str = "mmr",
    use_bm25: bool = True,
) -> "RAGChain":
    """
    Convenience factory: loads the LLM and retriever, returns a ready RAGChain.

    This is the single entry point used by app.py (Streamlit UI).

    Args:
        chunking_strategy : 'fixed', 'recursive', or 'semantic'
        model_key         : 'llama' or 'mistral'
        memory_type       : 'windowed' or 'summary'
        k_messages        : number of past turns kept (windowed mode)
        k_docs            : number of chunks retrieved per query
        search_type       : 'mmr' (default), 'similarity', or
                            'similarity_score_threshold'
        use_bm25          : whether to add BM25 keyword retrieval alongside
                            semantic search (hybrid retrieval, default True)

    Returns:
        A fully initialised RAGChain ready for .chat() calls
    """
    from llm import load_llm
    from retriever import get_retriever, get_embeddings, get_bm25_retriever

    print(f"Building RAG chain:")
    print(f"  chunking  = {chunking_strategy}")
    print(f"  LLM       = {model_key}")
    print(f"  memory    = {memory_type} (k={k_messages})")
    print(f"  retrieval = {search_type}, k={k_docs}, bm25={use_bm25}\n")

    # Load LLM first to claim GPU VRAM before BM25 fills system RAM
    llm = load_llm(model_key)

    embeddings = get_embeddings()
    retriever = get_retriever(
        chunking_strategy,
        k=k_docs,
        search_type=search_type,
        embeddings=embeddings,
    )

    bm25_retriever = None
    if use_bm25:
        print("  Building BM25 index (this may take ~30s on first load)...")
        bm25_retriever = get_bm25_retriever(
            chunking_strategy,
            k=k_docs * 10,
            embeddings=embeddings,
        )
        print("  BM25 index ready.")

    return RAGChain(
        retriever, llm,
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
            "bm25": use_bm25,
        },
    )


if __name__ == "__main__":
    # End-to-end smoke test - requires GPU and HF_TOKEN in .env
    print("Building RAG chain for smoke test...")
    chain = build_rag_chain(
        chunking_strategy="recursive",
        model_key="mistral",
        memory_type="windowed",
        k_messages=5,
        k_docs=5,
    )

    questions = [
        "What is the governing law of this contract?",
        "Does it have a non-compete clause?",
        "What about the termination conditions?",  # tests memory - uses "What about"
    ]

    for q in questions:
        print(f"\nQ: {q}")
        result = chain.chat(q)
        print(f"A: {result['answer']}")
        print(f"   (standalone query: '{result['standalone_question']}')")
        print(f"   ({len(result['source_documents'])} chunks retrieved)")
