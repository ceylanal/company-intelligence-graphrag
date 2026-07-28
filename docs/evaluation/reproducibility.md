# 🔄 Evaluation Reproducibility & Benchmark Execution Guide

This document outlines the step-by-step instructions to deterministically reproduce all RAG evaluation scorecards across Vector RAG, GraphRAG, and Hybrid RAG.

---

## ⚙️ 1. Environment & Model Specifications

- **Python Version**: `3.12+`
- **Embedding Model**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (FastEmbed)
- **Vector DB**: Qdrant (Embedded Local Storage `data/vector_store/qdrant_db`)
- **Graph DB**: Neo4j (Bolt `bolt://localhost:7687` with local fallback)
- **Random Seed**: `42`

---

## 🚀 2. Step-by-Step Reproduction Commands

```bash
# 1. Validate Dataset Integrity & Manifest SHA-256 Checksum
uv run company-graphrag validate-eval-dataset

# 2. Run Retrieval Benchmark Suite (Recall@k, MRR, nDCG)
uv run company-graphrag eval-retrieval-run

# 3. Run Answer & Citation Evaluation Suite
uv run company-graphrag eval-answers-run

# 4. Run Fast Regression Gate Check (<5% metric drop allowed)
uv run company-graphrag eval-regression-check

# 5. Run Day 33 Final Evaluation Audit & Generate Scorecards
uv run company-graphrag eval-final-run
```
