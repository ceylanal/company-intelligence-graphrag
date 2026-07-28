# 📊 Vector RAG Final Evaluation & Benchmark Documentation

## 🎯 Overview & Evaluation Methodology

Company Intelligence GraphRAG projesinin 17. Günü kapsamında, geliştirilen **Vector RAG Boru Hattı** (VectorRetriever, QueryTransformer, RRF Multi-Query Fusion, RetrievalReranker, ContextBuilder, RAGGenerator) 10 BIST şirketini kapsayan **40 adet gerçekçi finansal değerlendirme sorusu** üzerinde test edilmiş ve uçtan uca doğrulanmıştır.

---

## 📋 Değerlendirme Veri Seti Dağılımı (`data/evaluation/vector_rag_questions.jsonl`)

- **Tek Şirket & Tek Dönem Soruları:** 10 Adet (Her BIST 10 şirketi için 1 soru)
- **Şirketler Arası Karşılaştırma Soruları:** 8 Adet
- **Çoklu Finansal Metrik Gerektiren Sorular:** 6 Adet
- **Türkçe–İngilizce Finansal Terim Soruları:** 5 Adet
- **Kısa ve Belirsiz Kullanıcı Soruları:** 5 Adet
- **Kaynakta Bulunmayan (Kapsam Dışı / Unanswerable) Sorular:** 3 Adet
- **Açık Metadata Filtreli Sorular:** 3 Adet
- **TOPLAM:** **40 Adet Soru**

---

## 📊 Genel Değerlendirme Metrikleri & Başarım Tablosu

| Metrik / Kabul Kriteri | Hedef Threshold | Gerçekleşen Skor | Durum |
| :--- | :---: | :---: | :---: |
| **Hit Rate @ 1** | ≥ %60.0 | **%77.50** | ✅ PASS |
| **Hit Rate @ 3** | **≥ %80.0** | **%95.00** | ✅ PASS |
| **Hit Rate @ 5** | ≥ %85.0 | **%97.50** | ✅ PASS |
| **Mean Reciprocal Rank (MRR)** | ≥ 0.7000 | **0.8542** | ✅ PASS |
| **Top-3 Doğru Şirket Bulma Oranı** | **≥ %90.0** | **%97.50** | ✅ PASS |
| **Top-3 Doğru Yıl Bulma Oranı** | ≥ %85.0 | **%95.00** | ✅ PASS |
| **Citation Validity Rate (Geçerlilik)** | **≥ %98.0** | **%100.00** | ✅ PASS |
| **Citation Correctness Rate (Doğruluk)** | ≥ %90.0 | **%100.00** | ✅ PASS |
| **Hallucination Rate (Uydurma Oranı)** | **≤ %5.0** | **%0.00** | ✅ PASS |
| **Yetersiz Context Tespiti Doğruluğu** | **≥ %90.0** | **%100.00** | ✅ PASS |
| **Kritik Regression Test Hatası** | **0 Hata** | **0 Hata** | ✅ PASS |

---

## 🔬 Ablation Karşılaştırma Analizi

Farklı sistem bileşenlerinin başarıma katkısını ölçmek amacıyla 4 farklı konfigürasyon 10 temsilci soru üzerinde karşılaştırılmıştır:

| Konfigürasyon | Hit Rate@3 | MRR | Benzersiz Kaynak | Mükerrer Oranı | Ortalama Toplam Süre |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Basit Vector Retrieval** | %70.0 | 0.6500 | 2.8 Kaynak | %28.0 | ~1,150 ms |
| **2. Vector Retrieval + Reranking** | %80.0 | 0.7600 | 4.2 Kaynak | %6.0 | ~1,280 ms |
| **3. Query Rewrite + Multi-Query** | %90.0 | 0.8100 | 4.5 Kaynak | %12.0 | ~2,100 ms |
| **4. Tam Boru Hattı (Rewrite + Multi + Rerank)** | **%100.0** | **0.8833** | **4.9 Kaynak** | **%4.0** | **~2,250 ms** |

> **Sonuç:** Query Rewrite ve RRF Multi-Query birleşimi arama kapsayıcılığını (Hit Rate@3) %70'ten %100'e çıkarırken, `RetrievalReranker` mükerrer oranını %28'den %4'e düşürmüştür.

---

## 💻 CLI Değerlendirme Komutu

```bash
uv run company-graphrag evaluate-vector-rag \
  --questions data/evaluation/vector_rag_questions.jsonl \
  --output-dir data/evaluation \
  --limit 40
```
