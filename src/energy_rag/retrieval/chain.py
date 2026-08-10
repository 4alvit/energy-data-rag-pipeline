"""LangChain retrieval chain with citations."""

import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from energy_rag.config import settings
from energy_rag.retrieval.citations import extract_citations

logger = logging.getLogger(__name__)


# Prompt template for RAG
RAG_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert assistant for Victron Energy systems and renewable energy technology.
Answer questions based ONLY on the provided context documents.

Guidelines:
- Be precise and technical
- Cite sources using [doc_N] format where N is the document number
- If information is not in context, say "I don't have enough information from the provided sources"
- Include relevant specifications, part numbers, and configuration details when available""",
        ),
        (
            "human",
            """Context documents:
{context}

Question: {question}

Answer with citations:""",
        ),
    ]
)


def format_docs(docs: list[Document]) -> str:
    """Format documents for prompt context."""
    formatted = []
    for i, doc in enumerate(docs, 1):
        metadata = doc.metadata
        source_info = []
        if metadata.get("product"):
            source_info.append(f"Product: {metadata['product']}")
        if metadata.get("section_title"):
            source_info.append(f"Section: {metadata['section_title']}")
        if metadata.get("page_number"):
            source_info.append(f"Page: {metadata['page_number']}")
        if metadata.get("title"):
            source_info.append(f"Title: {metadata['title']}")

        src = f" [{', '.join(source_info)}]" if source_info else ""
        formatted.append(f"[doc_{i}]{src}\n{doc.page_content}")

    return "\n\n---\n\n".join(formatted)


def create_retrieval_chain(llm, retriever):
    """Create a LangChain retrieval chain with citations."""
    chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | RAG_PROMPT
        | llm
        | StrOutputParser()
    )
    return chain


class CitationExtractor:
    """Extract and format citations from LLM output."""

    def __init__(self, docs: list[Document]):
        self.docs = docs
        self.citation_map = {f"doc_{i}": doc for i, doc in enumerate(docs, 1)}

    def extract(self, answer: str) -> tuple[str, list[dict]]:
        """Extract citations from answer and return formatted citations."""
        return extract_citations(answer, self.citation_map)


def create_rag_chain(vector_store, llm, top_k: int | None = None):
    """Create complete RAG chain with vector store and LLM."""
    k = top_k or settings.default_top_k

    # Create retriever
    retriever = vector_store.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": k,
            "score_threshold": settings.similarity_threshold,
        },
    )

    # Create chain
    chain = create_retrieval_chain(llm, retriever)

    return chain


async def query_rag(
    vector_store,
    llm,
    question: str,
    top_k: int | None = None,
    filters: dict[str, Any] | None = None,
    include_citations: bool = True,
) -> dict[str, Any]:
    """Execute RAG query and return structured response."""
    import time

    start_time = time.perf_counter()

    k = top_k or settings.default_top_k

    # Retrieve documents
    retriever = vector_store.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={
            "k": k,
            "score_threshold": settings.similarity_threshold,
        },
    )

    # Apply metadata filters if provided
    if filters:
        retriever.search_kwargs["filter"] = filters

    docs = await retriever.ainvoke(question)

    if not docs:
        return {
            "answer": "I don't have enough information from the provided sources to answer this question.",
            "sources": [],
            "processing_time_ms": int((time.perf_counter() - start_time) * 1000),
        }

    # Create chain and get answer
    chain = create_retrieval_chain(llm, retriever)
    answer = await chain.ainvoke(question)

    # Extract citations
    sources = []
    if include_citations:
        extractor = CitationExtractor(docs)
        answer, sources = extractor.extract(answer)

    return {
        "answer": answer,
        "sources": sources,
        "processing_time_ms": int((time.perf_counter() - start_time) * 1000),
    }
