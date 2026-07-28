# 📊 GraphRAG Evaluation Framework Run Report

**Run Timestamp:** `2026-07-27T11:08:07.472942+00:00`
**Total Evaluation Samples:** `3`
**Splits Evaluated:** `test`

## 📌 1. Method Benchmark Performance Comparison

| Method | Samples | Overall Score | MRR | Recall@5 | Answer Token F1 | Numeric Acc | Abstention Acc | Citation Prec | Graph Path Recall | Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `vector_only` | 3 | **0.8667** | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.3333 | 45.00 ms |
| `hybrid` | 3 | **1.0000** | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 65.00 ms |

## 📋 2. Question Taxonomy Distribution

| Question Type | Sample Count | Percentage |
| :--- | :---: | :---: |
| `single_hop_fact` | 1 | 33.3% |
| `multi_hop_graph` | 1 | 33.3% |
| `unanswerable` | 1 | 33.3% |
