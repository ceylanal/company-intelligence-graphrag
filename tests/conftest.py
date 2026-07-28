"""Shared hermetic test fixtures."""

from collections.abc import Iterator

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from company_graphrag.embeddings import TextEmbeddingEncoder
from company_graphrag.retrieval.vector_retriever import VectorRetriever
from company_graphrag.storage.qdrant import QdrantVectorStore


@pytest.fixture
def seeded_vector_retriever() -> Iterator[VectorRetriever]:
    """Return an in-memory retriever with deterministic records used by regression tests."""
    encoder = TextEmbeddingEncoder(mock=True)
    store = QdrantVectorStore()
    store._client = QdrantClient(":memory:")
    collection_name = "test_company_documents"
    store.ensure_collection(collection_name, vector_size=encoder.vector_size)

    samples = [
        ("gelir ve kârlılık", "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "ASELS", 2024, "annual_report"),
        ("havacılık gelirleri", "Türk Hava Yolları A.O.", "THYAO", 2024, "annual_report"),
        ("finansal sonuçlar", "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "ASELS", 2024, "annual_report"),
        ("faaliyet dönemi", "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "ASELS", 2024, "annual_report"),
        ("ASELSAN 2024 cirosu", "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "ASELS", 2024, "annual_report"),
        ("Turkcell 5G yatırımları", "Turkcell İletişim Hizmetleri A.Ş.", "TCELL", 2024, "annual_report"),
        ("Şişecam cam üretimi", "Türkiye Şişe ve Cam Fabrikaları A.Ş.", "SISE", 2024, "annual_report"),
        ("Tüpraş kapasite", "Türkiye Petrol Rafinerileri A.Ş.", "TUPRS", 2024, "annual_report"),
        ("ASELSAN 2024 kârı", "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "ASELS", 2024, "annual_report"),
        ("ASELSAN ciro", "Aselsan Elektronik Sanayi ve Ticaret A.Ş.", "ASELS", 2024, "annual_report"),
    ]
    vectors = encoder.embed_texts([sample[0] for sample in samples])
    points = [
        PointStruct(
            id=index,
            vector=vector,
            payload={
                "chunk_id": f"fixture-{index}",
                "text": f"{query} hakkında doğrulanmış faaliyet raporu bilgisi.",
                "company": company,
                "ticker": ticker,
                "year": year,
                "report_type": report_type,
                "page_number": index + 1,
                "source_file": f"{ticker}__{year}__{report_type}__tr.pdf",
                "document_id": f"{ticker}__{year}__{report_type}__tr",
                "language": "tr",
            },
        )
        for index, ((query, company, ticker, year, report_type), vector) in enumerate(
            zip(samples, vectors, strict=True)
        )
    ]
    store.upsert_points_batch(collection_name, points)
    retriever = VectorRetriever(encoder=encoder, store=store, collection_name=collection_name)
    yield retriever
    retriever.close()
