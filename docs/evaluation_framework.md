# 📊 Evaluation Framework Architecture & Metrics Documentation

## 📌 Overview

Company Intelligence GraphRAG projesinin 27. Günü kapsamında, Vector RAG, GraphRAG ve Hybrid RAG sistemlerini bağımsız, modüler, deterministik ve bilimsel standartlarda karşılaştırmak amacıyla **Evaluation Framework (`src/company_graphrag/evals`)** tasarlanmıştır.

Bu altyapı:
- Mevcut Qdrant vector verilerini ve Neo4j graph kayıtlarını bozmadan veya yeniden üretmeden çalışır.
- RAG pipeline davranışını değiştirmez.
- Ağır LLM API çağrıları veya zaman alıcı toplu işlemler gerektirmez.
- 4 temel başarım boyutunda (Retrieval, Answer, Citation, Graph Reasoning) 20+ metrik hesaplar.

---

## 🗂️ 1. Evaluation Veri Modeli (`EvaluationSample`)

Her bir değerlendirme sorusu kaydı aşağıdaki 16 alandan oluşmaktadır:

```json
{
  "id": "eval_001",
  "question": "ASELSAN'ın ürettiği elektro-optik ürün hangisidir?",
  "question_type": "single_hop_fact",
  "company": "Aselsan",
  "expected_answer": "Aselsan ASELFLIR-500 elektro-optik sistem üretmektedir.",
  "acceptable_answers": ["ASELFLIR-500"],
  "source_file": "ASELS__2024.pdf",
  "source_pages": [14],
  "source_chunk_ids": ["chk_asels_14"],
  "expected_entities": ["Aselsan", "ASELFLIR-500"],
  "expected_relations": ["PRODUCES"],
  "expected_graph_path": ["(ASELSAN) ➔ PRODUCES ➔ (ASELFLIR-500)"],
  "answerable": true,
  "difficulty": "medium",
  "split": "test",
  "metadata": {}
}
```

### Soru Taksonomisi (`QuestionType`)
1. **`single_hop_fact`**: Tek bir metin parçasından çıkarılan olgusal bilgi.
2. **`multi_hop_graph`**: Graph üzerinde 2 veya daha fazla adımlı ilişki takibi.
3. **`comparison`**: İki şirket veya iki farklı dönem arası karşılaştırma.
4. **`temporal`**: Yıllara veya dönemlere sari zaman serisi analizi.
5. **`aggregation`**: Toplam, ortalama veya sayısal birleştirme gerektiren sorular.
6. **`unanswerable`**: Faaliyet raporlarında kanıtı bulunmayan (reddetme testi) sorular.
7. **`citation_verification`**: Atıf ve sayfa numarası doğrulama soruları.

---

## 📐 2. Metrik Tanımları ve Formülleri

### A. Retrieval Metrikleri (`retrieval_metrics.py`)
- **Recall@K ($K=1, 3, 5, 10$)**: Getirilen ilk $K$ sonuç içindeki doğru chunk oranı.
$$\text{Recall}@K = \frac{|\text{Retrieved}_K \cap \text{GroundTruth}|}{|\text{GroundTruth}|}$$
- **Precision@K ($K=1, 3, 5, 10$)**: Getirilen ilk $K$ sonucun isabet oranı.
- **MRR (Mean Reciprocal Rank)**: İlk doğru sonucun sıralama tersi ($1 / \text{rank}$).
- **nDCG@K**: Sıralama kalitesini ölçen derecelendirilmiş kumülatif kazanç.
- **Source / Page / Chunk Lineage Recall**: Dosya adı, sayfa ve chunk seviyesinde izlenebilirlik recall'u.

### B. Cevap Kalite Metrikleri (`answer_metrics.py`)
- **Exact Match (EM)**: Normalize edilmiş tahminin birebir eşleşme oranı.
- **Token F1**: Tahmin ve referans cevap arasındaki kelime düzeyinde F1 çakışması.
- **Normalized Match**: Noktalama işaretsiz Jaccard benzerliği.
- **Numeric Accuracy**: Tahmin içinde doğru geçen sayısal verilerin (ciro, yıl, yüzde) oranı.
- **Abstention Accuracy**: Kapsam dışı sorularda reddetme ("yetersiz kanıt") kararının doğruluğu.

### C. Atıf Kalite Metrikleri (`citation_metrics.py`)
- **Citation Precision**: Üretilen cevapta atıf yapılan kaynakların doğruluk oranı.
- **Citation Recall**: Doğru kaynakların cevaba yansıma oranı.
- **Citation Coverage**: Cümle/iddia başına düşen atıf kapsama oranı.
- **Cited Page Accuracy**: Atıfta verilen sayfa numaralarının doğruluğu.

### D. Graph Reasoning Metrikleri (`graph_metrics.py`)
- **Entity Recall**: Çekilen graph yollarındaki varlıkların (düğümlerin) kapsama oranı.
- **Relation Recall**: Çekilen ilişkilerin (kenarların) kapsama oranı.
- **Graph Path Recall**: İlgili graph yollarının tam olarak bulunma oranı.

---

## 💻 CLI Kullanım Komutları

```bash
# Değerlendirme test paketini çalıştırma
uv run company-graphrag run-eval --sample-path data/evaluation/eval_samples.jsonl --output-dir data/evaluation/eval_reports
```
