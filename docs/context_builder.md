# 📦 RAG Context Builder & Source Packaging Documentation

## 🎯 Architectural Overview

Company Intelligence GraphRAG projesinin 12. Günü kapsamında geliştirilen **`ContextBuilder`**, vektör arama motorundan (`VectorRetriever`) elde edilen ham sonuç parçalarını (**SearchHit**) temizleyen, mükerrer içerikleri ayıklayan, bütçe sınırlarını zorlamadan LLM promptlarına doğrudan enjekte edilebilir biçimde paketleyen (**ContextPackage**) üretim seviyesinde bir modüldür.

```mermaid
flowchart TD
    A[Vektör Arama Sonuçları<br>SearchHits / SearchResponse] --> B[ContextBuilder]
    B --> C{Chunk ID / Metin Mükerrer mi?}
    C -->|Evet| D[Dışarıda Bırak & excluded_duplicates++]
    C -->|Hayır| E{Metin Uzunluğu > Limit mi?}
    E -->|Evet| F[Cümle/Kelime Sınırında Kırp]
    E -->|Hayır| G[Blok Metni Oluştur<br>[Source N]]
    G --> H{Karakter Bütçesi Doldu mu?}
    H -->|Evet| I[Bütçe Sınırında Dur]
    H -->|Hayır| J[ContextPackage'e Ekle]
    J --> K[Formatted Context & SourceReference Listesi]
```

---

## ⚙️ Biçimlendirme Standardı ([Source N] Formatı)

Her kaynak bloğu LLM'in kaynak gösterimi yapabilmesi için aşağıdaki standartta üretilir:

```text
[Source 1] (Score: 0.7364)
Company: Aselsan Elektronik Sanayi ve Ticaret A.Ş. (ASELS) | Year: 2025 | Type: annual_report | Page: 22 | File: ASELS__2025__annual_report__tr.pdf (Chunk ID: 950427a255b1a35e)
Text:
Başlıca Göstergeler ASELSAN, 2025 yılında güçlü bir finansal performans göstermiş ve toplam varlıklarını 113,8 Milyar TL daha yükseltmiştir. Bakiye Sipariş (Milyar ABD Doları) 2025 20,4 ...
```

---

## 💻 CLI Kullanım Örnekleri

### 1. RAG Context Paketleme Komutu
```bash
uv run company-graphrag context "ASELSAN'ın 2024 gelir performansı nedir?" --top-k 5
```

### 2. Karakter Bütçesi Sınırlı Context Oluşturma
```bash
uv run company-graphrag context "Akbank kredi büyümesi" --ticker AKBNK --year 2024 --max-chars 2000
```

---

## 📊 RAG Context Çıktısı ve Metadata Özeti

- **Formatted Context:** LLM prompt `System/User` mesajına doğrudan eklenebilir metin.
- **Included Sources:** Bütçeye sığan aktif kaynak sayısı (`total_sources`).
- **Total Characters:** Context metninin toplam karakter boyutu (`total_characters`).
- **Excluded Duplicates:** Filtrelenen mükerrer chunk sayısı (`excluded_duplicates`).
- **SourceReference Metadata List:** Kaynak etiketleri, şirket adları, sayfa numaraları ve skor listesi.
