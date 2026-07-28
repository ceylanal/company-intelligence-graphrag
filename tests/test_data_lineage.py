"""Unit and integration tests for end-to-end data lineage verification (Day 9)."""

import json
from pathlib import Path

from company_graphrag.retrieval import SearchQuery, VectorSearchEngine
from company_graphrag.storage import QdrantVectorStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
PAGES_DIR = PROJECT_ROOT / "data" / "processed" / "pages"
RAW_DIR = PROJECT_ROOT / "data" / "raw"


def test_qdrant_and_chunk_count_match() -> None:
    """Verify that total chunks in JSONL files match Qdrant collection point count."""
    total_chunks = 0
    for fpath in CHUNKS_DIR.rglob("*.jsonl"):
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    total_chunks += 1

    store = QdrantVectorStore(path="data/vector_store/qdrant_db")
    info = store.get_collection_info("company_documents")
    store.close()

    assert total_chunks == 25859
    assert info.get("points_count") == total_chunks


def test_end_to_end_search_smoke_and_trace() -> None:
    """Smoke test: execute search query and trace top hit back to Chunk, Page, and PDF."""
    engine = VectorSearchEngine(collection_name="company_documents")
    query = SearchQuery(query="ASELSAN bakiye sipariş", top_k=1, ticker="ASELS", year=2025)

    response = engine.search(query)
    assert response.total_hits == 1

    hit = response.hits[0]
    assert hit.ticker == "ASELS"
    assert hit.year == 2025

    # Trace 1: Verify source PDF exists
    pdf_path = RAW_DIR / hit.ticker / hit.source_file
    if not pdf_path.exists():
        pdf_path = RAW_DIR / hit.source_file
    assert pdf_path.exists()

    # Trace 2: Verify page JSONL exists and contains matching page
    doc_id = hit.document_id
    page_jsonl_path = PAGES_DIR / hit.ticker / f"{doc_id}.jsonl"
    if not page_jsonl_path.exists():
        page_jsonl_path = PAGES_DIR / f"{doc_id}.jsonl"
    assert page_jsonl_path.exists()

    page_found = False
    with open(page_jsonl_path, encoding="utf-8") as pf:
        for line in pf:
            if line.strip():
                pobj = json.loads(line)
                if pobj.get("page_number") == hit.page_number:
                    page_found = True
                    break
    assert page_found

    # Trace 3: Verify chunk JSONL exists and contains matching chunk_id
    chunk_jsonl_path = CHUNKS_DIR / hit.ticker / f"{doc_id}.jsonl"
    if not chunk_jsonl_path.exists():
        chunk_jsonl_path = CHUNKS_DIR / f"{doc_id}.jsonl"
    if not chunk_jsonl_path.exists():
        matches = list(CHUNKS_DIR.rglob(f"*{doc_id}*.jsonl"))
        assert len(matches) > 0
        chunk_jsonl_path = matches[0]

    assert chunk_jsonl_path.exists()

    chunk_found = False
    with open(chunk_jsonl_path, encoding="utf-8") as cf:
        for line in cf:
            if line.strip():
                cobj = json.loads(line)
                if cobj.get("chunk_id") == hit.chunk_id:
                    chunk_found = True
                    assert cobj.get("ticker") == hit.ticker
                    assert cobj.get("page_number") == hit.page_number
                    break
    assert chunk_found
    engine.store.close()
