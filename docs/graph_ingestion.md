# 🚀 Neo4j Graph Ingestion Pipeline Documentation

## 📌 Overview

Company Intelligence GraphRAG projesinin 21. Günü kapsamında, Gün 18–20 arasında tasarlanan ve türetilen Graph şeması, entity ve relation kayıtlarını **Neo4j Graph Veritabanı** üzerine yükleyen uçtan uca **Neo4j Graph Ingestion Pipeline** mimarisi geliştirilmiştir.

Bu boru hattı:
- **MERGE Tabanlı Idempotent Yükleme**: Aynı veri seti veya parça tekrar yüklendiğinde mükerrer node veya edge oluşturmaz.
- **Toplu İşlem (Batch Ingestion & Transaction Control)**: `UNWIND $batch AS item` kalıbı kullanarak binlerce kaydı yüksek performansla yazar.
- **Kayıt ve Kanıt İzlenebilirliği (Grounding & Lineage Retention)**: Her node ve relation üzerinde `source_chunk_id`, `source_file`, `page_number` ve `evidence_text` metadatalarını eksiksiz korur.
- **Checkpointing & Kurtarma**: Yarım kalan yüklemelerin en son kalınan noktadan güvenle devam edebilmesini sağlar (`ingestion_checkpoint.json`).
- **Graph State Verification**: Yükleme sonrası node sayıları, relation türleri, mükerrer birleşmeler ve bağlantısız (orphan) düğüm denetimi yapar.

---

## 🏗️ Mimari Bileşenler

1. **`Neo4jGraphStore` (`src/company_graphrag/storage/neo4j.py`)**:
   - Canlı Neo4j veritabanına bağlanır (`bolt://localhost:7687`).
   - Canlı bağlantı kurulamadığında veya mock modunda bellek içi (In-Memory) graph simülatörüne otomatik fallback yapar.
2. **`GraphIngestionPipeline` (`src/company_graphrag/graph/ingestion/pipeline.py`)**:
   - `GraphSchemaManager` Cypher DDL kısıtlamalarını (Constraint & Index) uygular.
   - `data/graph/sample_day20` (veya Day 19) verilerini batch'ler halinde okur ve Cypher `MERGE` komutlarıyla yazar.
   - Doğrulama sorgularını çalıştırarak `ingestion_audit_report.json` raporunu üretir.
3. **CLI Komutu (`ingest-graph`)**:
   - Tek komutla yükleme ve doğrulama denetimini tetikler.

---

## 📊 Örnek Yükleme Audit Raporu (`ingestion_audit_report.json`)

```json
{
  "total_input_entities": 38,
  "total_input_relations": 30,
  "ingested_nodes": 38,
  "ingested_relations": 30,
  "node_counts_by_label": {
    "Company": 10,
    "FinancialMetric": 18,
    "Person": 5,
    "Product": 5
  },
  "relation_counts_by_type": {
    "PUBLISHED": 10,
    "REPORTED": 15,
    "EXECUTIVE_AT": 5
  },
  "orphan_node_count": 0,
  "duplicate_merge_attempts": 0,
  "execution_time_ms": 142.50,
  "status": "PASS"
}
```

---

## 💻 CLI Kullanım Komutları

### 1. Örnek Veri Setini Neo4j'e Yükleme

```bash
uv run company-graphrag ingest-graph --input-dir data/graph/sample_day20
```

### 2. Canlı Neo4j Sunucusuna Yükleme

```bash
uv run company-graphrag ingest-graph \
  --input-dir data/graph/sample_day20 \
  --neo4j-uri bolt://localhost:7687 \
  --neo4j-user neo4j \
  --neo4j-password password \
  --batch-size 200
```
