"""Versioned prompt registry with content-hash enforcement."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from company_graphrag.config import settings


class PromptDefinition(BaseModel):
    """One immutable prompt revision."""

    prompt_id: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=1)
    input_variables: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=10)
    change_reason: str = Field(min_length=1)
    content: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def calculated_hash(self) -> str:
        """Hash the exact prompt content."""
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class PromptRegistry:
    """Load prompts and reject content edits without a registry update."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.bundle_version = str(raw.get("bundle_version", ""))
        self.prompts = {
            item.prompt_id: item
            for item in (PromptDefinition.model_validate(value) for value in raw.get("prompts", []))
        }
        if not self.bundle_version or not self.prompts:
            raise ValueError(f"Prompt registry is incomplete: {self.path}")

    def get(self, prompt_id: str) -> PromptDefinition:
        """Return a verified prompt definition."""
        prompt = self.prompts[prompt_id]
        if prompt.calculated_hash() != prompt.content_hash:
            raise ValueError(
                f"Prompt '{prompt.prompt_id}' content changed without a version/hash update "
                f"(declared version {prompt.version})"
            )
        return prompt

    def validate(self) -> list[str]:
        """Return all registry consistency errors."""
        errors: list[str] = []
        for prompt_id in sorted(self.prompts):
            try:
                self.get(prompt_id)
            except ValueError as exc:
                errors.append(str(exc))
        return errors

    def bundle_fingerprint(self) -> str:
        """Create a stable fingerprint over prompt IDs, versions, and contents."""
        material = "\n".join(
            f"{item.prompt_id}:{item.version}:{item.calculated_hash()}"
            for item in sorted(self.prompts.values(), key=lambda value: value.prompt_id)
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@lru_cache
def get_prompt_registry(path: str | None = None) -> PromptRegistry:
    """Load the configured registry once per process."""
    return PromptRegistry(path or settings.prompt_registry_path)
