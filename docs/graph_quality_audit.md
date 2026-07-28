# 🔍 Knowledge Graph Quality Audit & Auto-Repair Documentation

## 📌 Overview

Company Intelligence GraphRAG projesinin 22. Günü kapsamında, Neo4j Graph Veritabanında yer alan varlık (Node) ve ilişki (Edge) kayıtlarının veri bütünlüğünü, şema uyumunu ve kaynak kanıt güvenilirliğini ölçen **Graph Quality Audit & Repair Engine** geliştirilmiştir.

Bu modül, mevcut graph verilerini baştan üretmeden **8 temel kalite boyutunda** denetler ve güvenli olan anomalileri otomatik onarır.

---

## 🔍 Denetlenen 8 Kalite Boyutu (Quality Dimensions)

1. **Mükerrer Düğüm ve İlişkiler (Duplicate Nodes & Relations)**:
   - Aynı ID veya mantıksal tanıma sahip birden fazla node veya aynı source-target arasında tekrar eden edge kontrolü.
2. **Kopuk İlişkiler (Dangling Relations)**:
   - Kaynak (`source_id`) veya hedef (`target_id`) node'u veritabanında bulunmayan kopuk ilişki kenarlarının tespiti (CRITICAL).
3. **Bağlantısız Düğümler (Orphan Nodes)**:
   - Gelen veya giden hiçbir ilişki kenarına sahip olmayan yalnız düğümlerin tespiti.
4. **Eksik Kaynak / Kanıt Metadataları (Missing Grounding Lineage)**:
   - `source_chunk_id`, `source_file`, `page_number` veya `evidence_text` bilgisi bulunmayan veya jenerik placeholder ("chunk_unknown") içeren kayıtlar.
5. **Şema İhlalleri (Schema Violations)**:
   - `schema.yaml` ontolojisine aykırı düğüm-ilişki-düğüm kombinasyonları (Örn: `Person` -> `PUBLISHED` -> `FinancialMetric`) (CRITICAL).
6. **Geçersiz Özellik Formatları (Invalid Properties)**:
   - Negatif sayfa numaraları (`page_number < 1`), mantıksız yıllar (`year < 1900` veya `> 2030`) ve boş isim alanları.
7. **Çelişkili Varlık Bilgileri (Conflicting Entity Data)**:
   - Aynı borsa sembolüne (ticker) sahip ancak farklı şirket adlarına atanmış çelişkili kayıtlar.
8. **Düşük Güvenilirlik Skorları (Low Confidence Records)**:
   - Güvenilirlik skoru belirlenen eşik değerin (`confidence < 0.50`) altında kalan kayıtlar.

---

## 🛠️ Otomatik Onarım (Repair) ve İnceleme Kuyruğu (Human Review Queue)

- **Güvenli Otomatik Onarım**:
  - Kopuk ilişkiler (`Dangling Relations`) otomatik silinir.
  - Mükerrer ilişkiler (`Duplicate Relations`) elenir.
  - Eksik grounding metadataları varsayılan değerlerle yamanır (`Missing Grounding`).
  - Düşük güvenilirlikli kayıtlar `low_confidence_flag = true` olarak etiketlenir.
- **İnceleme Kuyruğu (`human_review_queue.jsonl`)**:
  - Şema ihlalleri, çelişkili şirket adları ve yalnız düğümler otomatik silinmez; insan denetimine sunulmak üzere `data/graph/audit/human_review_queue.jsonl` dosyasına aktarılır.

---

## 💻 CLI Kullanım Komutları

### 1. Kalite Denetimi Çalıştırma ve Raporlama

```bash
uv run company-graphrag audit-graph --input-dir data/graph/sample_day20
```

### 2. Otomatik Onarım (Repair) ve İnceleme Kuyruğu Üretme

```bash
uv run company-graphrag audit-graph --repair --output-dir data/graph/audit
```
