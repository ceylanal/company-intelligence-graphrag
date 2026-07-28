# 🕸️ Multi-Hop Graph Retrieval Documentation

## 📌 Overview

Company Intelligence GraphRAG projesinin 23. Günü kapsamında, Neo4j Graph Veritabanında yer alan varlıklar (Node) ve ilişkiler (Edge) üzerinde **kontrollü, çok adımlı (1-hop, 2-hop, 3-hop) sorgulama ve kaynak izleme (Lineage)** altyapısı geliştirilmiştir.

Bu sistem:
- **Niyet Analizi (`GraphIntentExtractor`)**: Kullanıcı sorusundan aranan varlık tiplerini, borsa sembollerini (`ticker`), yıl ve metrik filtrelerini ve önerilen hop sayısını çıkarır.
- **Güvenli Parametrik Cypher Üretimi (`CypherQueryBuilder`)**: Kullanıcı metnini doğrudan Cypher dizesine eklemez; allowlist ve `$ticker`, `$year`, `$target_labels` parametreleri ile SQL/Cypher Injection saldırılarını tamamen engeller.
- **Hop ve Traversal Sınırlandırması**: Kontrolsüz graph traversal patlamasını önlemek için maksimum 3-hop, varsayılan 10 sonuç limiti ve zaman aşımı (`timeout_ms`) uygular.
- **Alaka Düzeyi Skorlaması (Relevance Scoring)**: İzlenen yolun uzunluğu (hop cezası), şirket eşleşmesi ve metrik uyumuna göre sonuçları sıralar.
- **Kaynak Kanıt İzlenebilirliği (Lineage Metadata)**: Her graph arama sonucu için türetildiği `chunk_id`, `source_file`, `page_number` ve `evidence_text` metadatalarını sunar.

---

## 🔍 Desteklenen Hop ve Sorgu Tipleri

### 1. 1-Hop Doğrudan Sorgular (Örn: Şirketin Ürünleri veya Yöneticisi)
- **Soru:** *"ASELSAN'ın ürünleri nelerdir?"*
- **İzlenen Yol:** `(:Company {ticker: "ASELS"})-[:PRODUCES]->(:Product)`
- **Lineage:** `ASELS__2024__annual_report__tr.pdf (Sayfa 14)`

### 2. 2-Hop Karşılaştırmalı veya Sektörel Sorgular (Örn: Aynı Sektördeki Şirketler)
- **Soru:** *"Akbank ile aynı sektörde faaliyet gösteren şirketler hangileridir?"*
- **İzlenen Yol:** `(:Company {ticker: "AKBNK"})-[:OPERATES_IN]->(:Sector)<-[:OPERATES_IN]-(:Company)`

### 3. 3-Hop Detaylı İlişki ve Metrik Sorguları
- **Soru:** *"ASELSAN'ın 2024 yılı ciro bilgisi hangi rapordan çekilmiştir?"*
- **İzlenen Yol:** `(:Company)-[:PUBLISHED]->(:Report)-[:CONTAINS_METRIC]->(:FinancialMetric)-[:SOURCED_FROM]->(:Chunk)`

---

## 💻 CLI Kullanım Komutları

### 1. Şirket Ürünleri Sorgusu (1-Hop)

```bash
uv run company-graphrag graph-search "ASELSAN'ın ürünleri nelerdir?" --max-hops 1
```

### 2. Aynı Sektördeki Şirketler Sorgusu (2-Hop)

```bash
uv run company-graphrag graph-search "Akbank ile aynı sektördeki şirketler" --max-hops 2
```

### 3. Finansal Metrik ve Dönem Sorgusu

```bash
uv run company-graphrag graph-search "THY 2024 yılı cirosu nedir?" --max-hops 2
```
