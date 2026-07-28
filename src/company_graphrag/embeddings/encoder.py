"""Embedding encoder wrapper using FastEmbed for ONNX-optimized vector generation."""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_VECTOR_SIZE = 384


class TextEmbeddingEncoder:
    """Text embedding encoder using FastEmbed or deterministic mock fallback."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, mock: bool = False) -> None:
        self.model_name = model_name
        self.mock = mock
        self._model: Any = None
        self._vector_size = DEFAULT_VECTOR_SIZE

        if not self.mock:
            self._init_fastembed_model()

    def _init_fastembed_model(self) -> None:
        """Initialize FastEmbed TextEmbedding model."""
        try:
            from fastembed import TextEmbedding

            logger.info("Initializing FastEmbed model", model_name=self.model_name)
            self._model = TextEmbedding(model_name=self.model_name)
            # Try embedding single dummy string to infer exact vector dimension
            dummy_generator = self._model.embed(["test"])
            first_vector = next(iter(dummy_generator))
            self._vector_size = len(first_vector)
            logger.info(
                "FastEmbed model initialized successfully",
                model=self.model_name,
                vector_size=self._vector_size,
            )
        except Exception as err:
            logger.warning(
                "Failed to initialize FastEmbed model directly, using mock fallback for test mode",
                error=str(err),
            )
            self.mock = True

    @property
    def vector_size(self) -> int:
        """Return the vector dimension size of the embedding model."""
        return self._vector_size

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate dense vector embeddings for a list of text strings."""
        if not texts:
            return []

        if self.mock or self._model is None:
            # Deterministic mock vectors for testing without model downloads
            import hashlib

            mock_vectors: list[list[float]] = []
            for t in texts:
                h = hashlib.sha256(t.encode("utf-8")).digest()
                # Expand 32 byte hash into vector_size float values normalized between -1.0 and 1.0
                vec = [(float(h[i % 32]) / 127.5) - 1.0 for i in range(self._vector_size)]
                # Normalize vector to unit length
                norm = sum(x * x for x in vec) ** 0.5 or 1.0
                norm_vec = [x / norm for x in vec]
                mock_vectors.append(norm_vec)
            return mock_vectors

        # FastEmbed model generator
        embeddings_gen = self._model.embed(texts)
        return [list(vec) for vec in embeddings_gen]
