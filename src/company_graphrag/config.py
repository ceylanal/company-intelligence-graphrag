"""Typed, environment-driven application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentType = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Settings
    environment: EnvironmentType = Field(default="development", description="Execution environment")
    log_level: str = Field(default="INFO", description="Logging level")
    app_host: str = Field(default="0.0.0.0", description="FastAPI server host")
    app_port: int = Field(default=8000, ge=1, le=65535, description="FastAPI server port")
    app_version: str = Field(default="0.1.0", description="Deployed application version")
    git_commit_sha: str = Field(default="unknown", description="Build-time source revision")
    checkpoint_dir: str = Field(default="data/checkpoints", description="Durable workflow checkpoint directory")
    shutdown_grace_period_seconds: float = Field(default=10.0, gt=0)
    health_timeout_seconds: float = Field(default=3.0, gt=0)
    request_max_bytes: int = Field(default=1_048_576, ge=1024)
    api_key: str = Field(default="", description="Optional public API key")

    # Qdrant Connection Settings (Local & Cloud)
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant gRPC/HTTP port")
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant REST URL")
    qdrant_api_key: str = Field(default="", description="Qdrant API Key")
    qdrant_collection_name: str = Field(default="company_documents", description="Qdrant collection name")
    qdrant_use_cloud: bool = Field(default=False, description="Enable cloud Qdrant cluster mode")

    # Neo4j Connection Settings (Local & Cloud)
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j connection URI")
    neo4j_http_url: str = Field(default="http://localhost:7474", description="Neo4j HTTP URL")
    neo4j_username: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="password", description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")
    neo4j_use_cloud: bool = Field(default=False, description="Enable cloud Neo4j Aura mode")

    # LLM & RAG Settings
    llm_provider: str = Field(default="mock", description="LLM provider name (mock, gemini, openai, ollama)")
    llm_model: str = Field(default="mock-v1", description="LLM model identifier")
    llm_api_key: str = Field(default="", description="LLM API Key")
    llm_fallback_model: str = Field(default="", description="Explicit fallback model, empty disables fallback")
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    qdrant_timeout_seconds: float = Field(default=5.0, gt=0)
    neo4j_timeout_seconds: float = Field(default=5.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_base_seconds: float = Field(default=0.25, gt=0)

    # Research safety budgets
    max_concurrent_research_tasks: int = Field(default=2, ge=1, le=32)
    rate_limit_requests: int = Field(default=30, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    research_max_duration_seconds: float = Field(default=300.0, gt=0)
    research_max_model_calls: int = Field(default=12, ge=1)
    research_max_input_tokens: int = Field(default=64_000, ge=1)
    research_max_output_tokens: int = Field(default=16_000, ge=1)
    research_max_total_tokens: int = Field(default=80_000, ge=1)
    research_max_cost_usd: float | None = Field(default=None, gt=0)

    # Versioned AI artifacts
    prompt_registry_path: str = Field(default="config/prompts.yaml")
    run_manifest_dir: str = Field(default="artifacts/run_manifests")
    embedding_model: str = Field(default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    chunk_target_tokens: int = Field(default=500, ge=1)
    chunk_overlap_tokens: int = Field(default=50, ge=0)
    qdrant_collection_version: str = Field(default="1.0.0")
    graph_schema_version: str = Field(default="1.0.0")
    retrieval_version: str = Field(default="1.0.0")
    workflow_version: str = Field(default="1.0.0")
    citation_validation_version: str = Field(default="1.0.0")
    eval_dataset_version: str = Field(default="1.0.0")
    eval_rubric_version: str = Field(default="1.0.0")

    # Optional, fail-open telemetry
    telemetry_enabled: bool = Field(default=False)
    telemetry_exporter: Literal["none", "console", "otlp"] = Field(default="none")
    otel_service_name: str = Field(default="company-graphrag-api")
    otel_exporter_otlp_endpoint: str = Field(default="")
    otel_exporter_otlp_headers: str = Field(default="")
    opik_enabled: bool = Field(default=False)
    opik_api_key: str = Field(default="")
    opik_workspace: str = Field(default="")
    telemetry_capture_prompts: bool = Field(default=False)

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, v: str) -> str:
        """Normalize environment name and ensure valid environment value."""
        env_clean = str(v).strip().lower()
        if env_clean == "testing":
            env_clean = "test"
        valid_envs = {"development", "test", "staging", "production"}
        if env_clean not in valid_envs:
            raise ValueError(f"Invalid environment '{v}'. Must be one of {sorted(valid_envs)}")
        return env_clean

    @property
    def is_production(self) -> bool:
        """Check if environment is production."""
        return self.environment == "production"

    @property
    def is_staging(self) -> bool:
        """Check if environment is staging."""
        return self.environment == "staging"

    @property
    def is_test(self) -> bool:
        """Check if environment is test or testing."""
        return self.environment == "test"

    @property
    def is_development(self) -> bool:
        """Check if environment is development."""
        return self.environment == "development"

    @property
    def effective_qdrant_url(self) -> str:
        """Return canonical Qdrant REST URL."""
        if self.qdrant_url:
            return self.qdrant_url.rstrip("/")
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def effective_neo4j_http_url(self) -> str:
        """Return canonical Neo4j HTTP URL."""
        if self.neo4j_http_url:
            return self.neo4j_http_url.rstrip("/")
        return "http://localhost:7474"


@lru_cache
def get_settings() -> Settings:
    """Return the immutable process-wide settings instance."""
    return Settings()


settings = get_settings()
