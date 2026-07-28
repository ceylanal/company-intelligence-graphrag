# 🤖 GraphRAG Grounded Answer Generation Documentation

## 📌 Overview

Company Intelligence GraphRAG projesinin 25. Günü kapsamında, hibrit retrieval (Vector + Graph) sonuçlarını kullanan **%100 Kanıta Dayalı Cevap Üretim Katmanı (`GraphRAGGenerator`)** geliştirilmiştir.

Bu sistem:
- **Ortak Bağlam Paketleme (`GraphRAGContextBuilder`)**: Vector metin parçalarını (`chunks`) ve Neo4j graph ilişki yollarını (`graph paths`) numaralandırılmış `[Source N]` kaynak paketlerine dönüştürür.
- **Sıkı Kanıt Koşulu (Zero Hallucination)**: LLM'in yalnızca sağlanan kaynaklara dayanarak yanıt vermesini sağlar.
- **Ayrıntılı Kaynak Atfı (`GraphCitation`)**: Üretilen her iddianın yanına şirket adı, borsa sembolü (`ticker`), rapor yılı, rapor türü, kaynak dosya adı (`source_file`), sayfa numarası (`page_number`) ve `chunk_id` atıflarını ekler.
- **Graph İlişki Açıklanabilirliği (`used_relationships`)**: Çok adımlı (multi-hop) sorgularda izlenen graph ilişki yolunu kullanıcılara açıkça sunar.
- **Yetersiz Kanıt Koruması (`insufficient_context`)**: Sağlanan kaynaklar yetersiz kaldığında kesin cevap üretmeyip güvenle *"Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı."* yanıtını verir.
- **Çelişki Tespiti (`contradictions_found`)**: Sağlanan kaynaklar arasında tespit edilen finansal değer veya tarih çelişkilerini açıkça raporda vurgular.

---

## 📋 Üretilen Cevap Yapısı (`GraphRAGAnswer`)

```json
{
  "query": "ASELSAN 2024 cirosu ve ürün grupları nelerdir?",
  "short_answer": "Aselsan 2024 yılında 80 Milyar TL ciro elde etmiş ve elektro-optik sistem üretimi yapmıştır.",
  "detailed_explanation": "Aselsan 2024 faaliyet raporuna göre şirket 80 Milyar TL ciro elde etmiş [Source 1], ASELFLIR-500 elektro-optik sistemlerini üretmiştir [Source 2].",
  "used_relationships": [
    "(ASELSAN) ➔ PRODUCES ➔ (ASELFLIR-500)"
  ],
  "citations": [
    {
      "source_number": 1,
      "company": "Aselsan",
      "ticker": "ASELS",
      "year": 2024,
      "report_type": "Faaliyet Raporu",
      "source_file": "ASELS__2024__annual_report.pdf",
      "page_number": 14,
      "chunk_id": "chunk_asels_14_01",
      "evidence_snippet": "2024 yılında konsolide ciro 80 Milyar TL olarak gerçekleşmiştir."
    }
  ],
  "confidence_level": "HIGH",
  "insufficient_context": false,
  "contradictions_found": []
}
```

---

## 💻 CLI Kullanım Komutları

### 1. Uçtan Uca GraphRAG Cevap Üretimi (Grounding Testi)

```bash
uv run company-graphrag graphrag-ask "ASELSAN 2024 cirosu ve ürün grupları nelerdir?" --mock
```

### 2. Kapsam Dışı Soru (Yetersiz Kanıt Koruması Testi)

```bash
uv run company-graphrag graphrag-ask "Aselsan mars uzay mekiği projesi" --mock
```
