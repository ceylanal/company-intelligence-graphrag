# 🤖 Grounded Answer Generation & Citation Tracking Documentation

## 🎯 Architectural Overview

Company Intelligence GraphRAG projesinin 13. Günü kapsamında geliştirilen **`RAGGenerator`**, vektör arama motorundan (`VectorRetriever`) elde edilen kaynakları `ContextBuilder` ile paketleyip LLM (Large Language Model) istemlerine (prompts) bağlam (context) olarak sunan ve yanıtların **%100 kanıtlı (grounded)** ve **kaynak gösterimli (cited)** olmasını sağlayan üretim seviyesinde bir yanıt üretici modüldür.

```mermaid
flowchart TD
    A[Kullanıcı Sorgusu / CLI Ask] --> B[RAGGenerator]
    B --> C[VectorRetriever & ContextBuilder]
    C --> D{Context Yeterli mi?}
    D -->|Hayır / 0 Kaynak| E[İstisnai Yanıt:<br>Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı.]
    D -->|Evet| F[Katı Grounded System Prompt<br>+ Context + Query]
    F --> G[LLM Yanıt Üretimi<br>Mock / Gemini / OpenAI]
    G --> H[Citation Validator & Extractor<br>Extract & Verify [Source N]]
    H --> I[RAGAnswer Payload<br>answer, citations, sources, insufficient_context]
```

---

## ⚙️ Katı Grounded Prompting ve Hallucinated Veri Engelleme

Sistem istemi (`GROUNDED_RAG_SYSTEM_PROMPT`) LLM'in uydurma veri üretmesini engellemek için şu katı kuralları uygular:

1. **Sadece Bağlam Kullanımı:** Model yalnızca kendisine verilen `[BAĞLAM]` içerisindeki verileri kullanabilir. Dış bilgi ekleyemez.
2. **Yetersiz Bağlam Koruması:** Eğer bağlamda sorunun cevabı yoksa, model istintisiz olarak şu standart cümleyi söyler:
   `"Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli bilgi bulunamadı."`
3. **Zorunlu Kaynak Gösterimi:** Cevaptaki her finansal iddia veya rakam için `[Source 1]`, `[Source 2]` şeklinde parantez içi etiketleme yapılır.
4. **Citation Doğrulaması:** Üretilen metindeki kaynak etiketleri regex ile ayıklanır ve sadece gerçekten sunulmuş kaynak numaraları ile eşleşenler kabul edilir (geçersiz/uydurma kaynak numaraları elenir).

---

## 🔧 Yapılandırma ve Bağımlılık Yönetimi (.env)

LLM sağlayıcısı ve model adı `.env` dosyası üzerinden veya kod içinden dinamik olarak ayarlanabilir:

```env
LLM_PROVIDER=gemini        # Seçenekler: mock, gemini, openai, ollama
LLM_MODEL=gemini-2.5-flash # Model kimliği
LLM_API_KEY=your_api_key_here
```

API anahtarı bulunmadığında veya ağ hatası oluştuğunda sistem çökmez; otomatik olarak güvenli mock yanıt üreticisine düşer (`mock_mode`).

---

## 💻 CLI Kullanım Örnekleri

### 1. Grounded Cevap Üretme Komutu
```bash
uv run company-graphrag ask "ASELSAN'ın 2024 gelir performansı nasıldı?" --top-k 5
```

### 2. Filtreli ve Belirli Şirket İçi Yanıt Üretimi
```bash
uv run company-graphrag ask "2024 yılı dijital bankacılık büyümesi" --ticker AKBNK --year 2024
```

---

## 📊 Örnek Çıktı

```text
=== GROUNDED ANSWER ===

Aselsan Elektronik Sanayi ve Ticaret A.Ş. (ASELS) 2024 yılı raporu verilerine göre; Başlıca Göstergeler ASELSAN’ın 2024 yılında Cirosu bir önceki yıla göre %13 büyüyerek 120 Milyar TL’ye ulaşmıştır. [Source 1]

══════════════════════════════════════════════════════════════════════
     RAG Generation & Citation Metadata
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Metric / Status           ┃ Value        ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ LLM Provider / Model      │ mock (mock-v1)│
│ Cited Source Numbers      │ [Source 1]   │
│ Used Sources Count        │ 1            │
│ Insufficient Context Flag │ False        │
└───────────────────────────┴──────────────┘
```
