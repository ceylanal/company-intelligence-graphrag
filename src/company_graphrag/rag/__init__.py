"""RAG (Retrieval-Augmented Generation) subpackage."""

from company_graphrag.rag.context_builder import ContextBuilder, compute_text_similarity
from company_graphrag.rag.generator import RAGGenerator, extract_citations
from company_graphrag.rag.models import ContextPackage, RAGAnswer, SourceReference, VectorRAGResult
from company_graphrag.rag.pipeline import VectorRAGPipeline
from company_graphrag.rag.prompts import GROUNDED_RAG_SYSTEM_PROMPT, GROUNDED_RAG_USER_PROMPT_TEMPLATE

__all__ = [
    "ContextBuilder",
    "ContextPackage",
    "SourceReference",
    "RAGAnswer",
    "RAGGenerator",
    "VectorRAGPipeline",
    "VectorRAGResult",
    "extract_citations",
    "compute_text_similarity",
    "GROUNDED_RAG_SYSTEM_PROMPT",
    "GROUNDED_RAG_USER_PROMPT_TEMPLATE",
]
