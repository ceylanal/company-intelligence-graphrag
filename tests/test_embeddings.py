"""Unit tests for vector embedding and Qdrant storage pipeline."""

from pathlib import Path

from qdrant_client.models import Distance
from typer.testing import CliRunner

from company_graphrag.cli import app
from company_graphrag.embeddings import (
    EmbeddingConfig,
    TextEmbeddingEncoder,
    embed_and_ingest_chunks,
    generate_deterministic_point_id,
)
from company_graphrag.embeddings.encoder import LEGACY_CLS_MODEL_NAME
from company_graphrag.storage import get_qdrant_distance

runner = CliRunner()


def test_generate_deterministic_point_id() -> None:
    """Test deterministic UUID generation from chunk_id."""
    chunk_id = "6c8a6b63b3168288"
    p_id1 = generate_deterministic_point_id(chunk_id)
    p_id2 = generate_deterministic_point_id(chunk_id)

    assert p_id1 == p_id2
    assert len(p_id1) == 36  # Standard UUID string length
    assert "-" in p_id1


def test_get_qdrant_distance() -> None:
    """Test Qdrant distance metric enum mapping."""
    assert get_qdrant_distance("Cosine") == Distance.COSINE
    assert get_qdrant_distance("dot") == Distance.DOT
    assert get_qdrant_distance("euclid") == Distance.EUCLID


def test_mock_text_embedding_encoder() -> None:
    """Test mock vector encoder generation."""
    encoder = TextEmbeddingEncoder(mock=True)
    assert encoder.vector_size == 384

    texts = ["Aselsan 2025 yılı finansal raporu", "Akbank bilanço detayları"]
    vectors = encoder.embed_texts(texts)

    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert len(vectors[1]) == 384
    # Check unit length normalization
    norm = sum(x * x for x in vectors[0]) ** 0.5
    assert abs(norm - 1.0) < 1e-5


def test_default_model_preserves_legacy_cls_pooling(monkeypatch) -> None:
    """Use the CLS-compatible FastEmbed alias for existing Qdrant indexes."""
    captured: dict[str, str] = {}

    class FakeEmbedding:
        @staticmethod
        def list_supported_models() -> list[dict[str, str]]:
            return [{"model": LEGACY_CLS_MODEL_NAME}]

        def __init__(self, model_name: str) -> None:
            captured["model_name"] = model_name

        def embed(self, texts: list[str]):
            return iter([[0.0] * 384 for _ in texts])

    import fastembed

    monkeypatch.setattr(fastembed, "TextEmbedding", FakeEmbedding)
    encoder = TextEmbeddingEncoder()

    assert encoder.vector_size == 384
    assert captured["model_name"] == LEGACY_CLS_MODEL_NAME


def test_embed_pipeline_dry_run(tmp_path: Path) -> None:
    """Test embedding pipeline in dry-run mode without Qdrant ingestion."""
    chunks_dir = tmp_path / "chunks"
    ticker_dir = chunks_dir / "AKBNK"
    ticker_dir.mkdir(parents=True)

    chunk_file = ticker_dir / "AKBNK__2024__annual_report__tr_chunks.jsonl"
    sample_json = (
        '{"chunk_id":"c123456789012345","document_id":"AKBNK__2024__annual_report__tr",'
        '"company":"Akbank T.A.Ş.","ticker":"AKBNK","year":2024,"report_type":"annual_report",'
        '"language":"tr","page_number":1,"chunk_index":0,"text":"Sample chunk text content.",'
        '"token_count":15,"source_file":"AKBNK__2024__annual_report__tr.pdf"}\n'
    )
    chunk_file.write_text(sample_json, encoding="utf-8")

    config = EmbeddingConfig(collection_name="test_dry_run")
    summary = embed_and_ingest_chunks(input_path=chunks_dir, config=config, dry_run=True, mock_encoder=True)

    assert summary.total_chunks == 1
    assert summary.total_points_upserted == 0


def test_cli_embed_command_mock(tmp_path: Path) -> None:
    """Test CLI embed command with --mock option."""
    chunks_dir = tmp_path / "chunks_cli"
    ticker_dir = chunks_dir / "ASELS"
    ticker_dir.mkdir(parents=True)

    chunk_file = ticker_dir / "ASELS__2025__annual_report__tr_chunks.jsonl"
    sample_json = (
        '{"chunk_id":"asels12345678901","document_id":"ASELS__2025__annual_report__tr",'
        '"company":"Aselsan A.Ş.","ticker":"ASELS","year":2025,"report_type":"annual_report",'
        '"language":"tr","page_number":1,"chunk_index":0,"text":"Sample Aselsan text content.",'
        '"token_count":12,"source_file":"ASELS__2025__annual_report__tr.pdf"}\n'
    )
    chunk_file.write_text(sample_json, encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "embed",
            str(chunks_dir),
            "--collection-name",
            "test_cli_mock",
            "--mock",
            "--dry-run",
        ],
    )
    assert res.exit_code == 0
    assert "Starting Vector Embedding" in res.output
    assert "Embedding & Qdrant Ingestion Summary" in res.output
