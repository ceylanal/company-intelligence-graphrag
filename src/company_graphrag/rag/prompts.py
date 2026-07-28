"""Compatibility constants backed by the versioned prompt registry."""

from company_graphrag.versioning.prompts import get_prompt_registry

_registry = get_prompt_registry()
GROUNDED_RAG_SYSTEM_PROMPT = _registry.get("grounded_rag.system").content
GROUNDED_RAG_USER_PROMPT_TEMPLATE = _registry.get("grounded_rag.user").content
