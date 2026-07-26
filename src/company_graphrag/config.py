"""Configuration module using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Settings
    environment: str = Field(default="development", description="Execution environment")
    log_level: str = Field(default="INFO", description="Logging level")

    # Qdrant Local Connection Settings
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant gRPC/HTTP port")
    qdrant_url: str = Field(default="http://localhost:6333", description="Qdrant REST URL")
    qdrant_api_key: str = Field(default="", description="Qdrant API Key")
    qdrant_collection_name: str = Field(
        default="company_documents", description="Qdrant collection name"
    )

    # Neo4j Local Connection Settings
    neo4j_uri: str = Field(default="bolt://localhost:7687", description="Neo4j connection URI")
    neo4j_http_url: str = Field(default="http://localhost:7474", description="Neo4j HTTP URL")
    neo4j_username: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="password", description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")

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


settings = Settings()
