# 🚀 Hybrid Vector & Graph Retrieval Documentation

## 📌 Overview

Company Intelligence GraphRAG projesinin 24. Günü kapsamında, **Qdrant Vector RAG** (anlamsal metin arama) ile **Neo4j Graph RAG** (yapısal varlık ve multi-hop ilişki sorgulama) retriever altyapıları tek bir birleşik arama arayüzü (`HybridRetriever`) altında birleştirilmiştir.

Bu sistem:
- **4 Desteklenen Arama Modu**: `vector_only`, `graph_only`, `hybrid`, `auto`.
- **Otomatik Yönlendirme (Auto-routing)**: Soru anlamsal/açıklayıcı ise `vector`, yapısal/ilişkisel ise `graph`, karmaşık ise `hybrid` moduna yönlendirir.
- **Reciprocal Rank Fusion (RRF) & Tekilleştirme (Deduplication)**: Vector ve Graph arama sonuçlarını RRF algoritması ($1 / (60 + rank)$) ile birleştirir ve mükerrer kaynakları tekilleştirir.
- **Güvenli Fallback Mekanizması**: Graph veritabanı veya network hatasında kesinti yaratmadan güvenle Vector RAG sonucuna düşer.
- **Kaynak Etiketleme (Attribution)**: Her arama sonucunun hangi arama motorundan geldiğini (`vector`, `graph`, `fused`) açıkça gösterir.

---

## 🔍 Retrieval Modları ve Çalışma Mantığı

| Mod | Tanım | Kullanım Senaryosu |
| :--- | :--- | :--- |
| **`vector_only`** | Yalnızca Qdrant Vector veritabanında embedding bazlı anlamsal arama yapar. | Açıklayıcı, anlatısal, strateji ve vizyon soruları. |
| **`graph_only`** | Yalnızca Neo4j Graph veritabanında Cypher multi-hop traversal yapar. | Ürünler, yöneticiler, rakipler ve sektörel bağlar. |
| **`hybrid`** | Hem Vector hem Graph arama yapar; sonuçları **RRF** ile harmanlar. | Ciro, kârlılık ve stratejileri aynı anda içeren sorular. |
| **`auto`** | Soru metnini analiz ederek otomatik olarak `vector`, `graph` veya `hybrid` seçer. | Varsayılan genel kullanıcı kullanımı. |

---

## 💻 CLI Kullanım Komutları

### 1. Otomatik Yönlendirme ile Hibrit Arama (Auto Mode)

```bash
uv run company-graphrag hybrid-search "ASELSAN 2024 cirosu ve ürün grupları nelerdir?" --mode auto --mock
```

### 2. Yalnızca Vector Arama (Vector Only)

```bash
uv run company-graphrag hybrid-search "ASELSAN'ın sürdürülebilirlik vizyonunu açıkla" --mode vector_only
```

### 3. Yalnızca Graph Arama (Graph Only)

```bash
uv run company-graphrag hybrid-search "Akbank ile aynı sektördeki şirketler" --mode graph_only --mock
```
