# 🔄 Company Intelligence GraphRAG - Data Pipeline Documentation

## 🎯 Architectural Architecture & Flow

Company Intelligence GraphRAG veri işleme boru hattı 4 ana katmandan oluşmaktadır:

```mermaid
flowchart TD
    subgraph DataCollection["1. Veri Toplama & Envanter (Gün 1-3)"]
        A[PDF Faaliyet Raporları<br>data/raw/TICKER/] --> B[Validation Pipeline<br>validate_reports.py]
        B --> C[Master Manifest Register<br>data/manifest.json & report_manifest.jsonl]
    end

    subgraph IngestionParsing["2. Parsing & Sayfa Ayıklama (Gün 4)"]
        C --> D[PyMuPDF Page Parser<br>company-graphrag parse]
        D --> E[Page JSONL Records<br>data/processed/pages/]
    end

    subgraph SemanticChunking["3. Anlamsal Metin Bölümleme (Gün 5)"]
        E --> F[Token Chunker<br>company-graphrag chunk]
        F --> G[Chunk JSONL Records<br>data/processed/chunks/]
    end

    subgraph IndexingStorage["4. FastEmbed & Qdrant Yükleme (Gün 6-10)"]
        G --> H[FastEmbed ONNX Encoder<br>sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2]
        H --> I[(Qdrant Vector DB<br>collection: company_documents)]
    end
```

---

## ⚙️ Boru Hattı Katmanları ve Kuralları

### Katman 1: Veri Toplama ve Doğrulama
- 10 hedef şirket için 3 Yıl (2023-2025) PDF faaliyet raporları indirilir.
- SHA-256 dijital parmak izleri hesaplanır, mükerrer dosyalar karantinaya alınır.
- Standart isimlendirme kuralı: `{TICKER}__{YEAR}__{REPORT_TYPE}__{LANGUAGE}.pdf`

### Katman 2: PDF Parsing (Sayfa Ayrıştırma)
- PyMuPDF (`fitz`) kütüphanesi kullanılarak her PDF sayfa bazında ayrıştırılır.
- Boş sayfalar veya görsel ağırlıklı sayfalar `needs_ocr=true` olarak işaretlenir.
- Her PDF için 1 adet `data/processed/pages/{TICKER}/{doc_id}.jsonl` dosyası oluşturulur.

### Katman 3: Semantic Chunking (Metin Bölümleme)
- Paragraf ve cümle sınırları korunarak token hesabı yapılır.
- Target chunk boyutu: **500 token**, Overlap boyutu: **50 token**.
- `data/processed/chunks/{TICKER}/{doc_id}_chunks.jsonl` formatında kaydedilir.

### Katman 4: Vektör İndeksleme (Qdrant Vector DB)
- FastEmbed ONNX `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` modeli ile 384-boyutlu vektörler üretilir.
- Deterministik UUIDv5 point ID ile Qdrant veritabanındaki `company_documents` koleksiyonuna yüklenir.
- 11 metadata alanı payload içinde saklanır.
