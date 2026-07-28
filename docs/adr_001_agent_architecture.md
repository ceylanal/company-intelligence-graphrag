# ADR 001: Pydantic-Based Typed State for Multi-Agent Research Assistant Architecture

- **Status**: Approved
- **Date**: 2026-07-28
- **Authors**: DeepMind Agentic Coding Team / Lead Architect

---

## 🎯 Context & Problem Statement

Company Intelligence GraphRAG projesi Gün 34 itibarıyla Vector RAG, Knowledge Graph RAG ve Evaluation modüllerini birleştiren çoklu ajanlı (multi-agent) bir araştırma asistanı mimarisi gerektirmektedir.

Ana ihtiyaçlar:
1. Altı ajan rolü (Supervisor, Planner, Vector Researcher, Graph Researcher, Evidence Verifier, Report Writer) arasında kesintisiz, strictly-typed veri paylaşımı.
2. Vektör ve grafik aramalarında kaynak takibi (provenance) zorunluluğu.
3. Sonsuz planlama/araştırma döngülerini ve kaynak tüketimini önleyen kesin bütçe kontrolü (`ExecutionBudget`).
4. Mevcut Qdrant ve Neo4j veri hatlarını değiştirmeden korumak.

Piyasada LangGraph, AutoGen, CrewAI gibi çeşitli multi-agent orkestrasyon kütüphaneleri bulunmaktadır. Soru şudur: **Projeye yeni bir dış orkestrasyon framework'ü eklemeli miyiz, yoksa mevcut `pydantic>=2.7.0` altyapısı ile yerel typed state ve soyutlama katmanı mı oluşturmalıyız?**

---

## 💡 Decision Drivers

- **Zero Over-Engineering & Minimum Dependencies**: Projede gereksiz dependency yükü oluşturmamak ve sürdürülebilirliği korumak.
- **Strict Type Validation & Serialization**: Pydantic v2 modellerinin sunduğu hızlı validation, JSON şema üretimi ve IDE tip desteği.
- **Full Control over State & Budget**: State mutasyonları, retry politikaları ve durma koşulları üzerinde %100 doğrudan kontrol.
- **Isolation of Database Drivers**: Ajanların doğrudan QdrantClient veya Neo4j Driver instancelarına erişmesini engelleyerek typed tool arayüzleri arkasında soyutlamak.

---

## ⚖️ Considered Options

1. **Option 1: Add LangGraph / AutoGen / CrewAI Frameworks**
   - *Pros*: Hazır graph düğüm yapıları ve görselleştirme araçları.
   - *Cons*: Ağır dependency yükü, sık değişen API kontratları, yüksek runtime overhead'i ve mevcut test suiti ile olası sürüm uyuşmazlıkları.

2. **Option 2: Pure Pydantic v2 Typed Shared State & Explicit Agent Contracts (Selected)**
   - *Pros*: Sıfır ek kütüphane bağımlılığı (`pydantic>=2.7.0` zaten projede mevcut), %100 tip güvenliği, milisaniye mertebesinde çalışma hızı, tam test edilebilirlik ve sıfır sürpriz davranış.
   - *Cons*: İş akışı durum geçiş mantığının (state machine) projede temiz bir şekilde kodlanması gerekir.

---

## 🏁 Decision Outcome

**Option 2 (Pure Pydantic v2 Typed Shared State)** seçilmiştir.

### Kararın Gerekçeleri:
1. Projenin bağımlılıklarında `pydantic>=2.7.0` zaten yer almaktadır. Pydantic v2'nin `@model_validator`, `BaseModel` ve JSON serialization yetenekleri, shared state ve agent kontratlarını eksiksiz karşılamaktadır.
2. Dış framework'ler projeye karmaşıklık getirirken, tip güvenliği ve kaynak takibi (provenance validation) garantisi vermemektedir.
3. `ResearchState` nesnesi; bütçe denetimi (`ExecutionBudget`), iddia doğrulama (`VerifiedClaim`, `RejectedClaim`), çelişki tespiti (`Contradiction`) ve denetim izini (`ToolCallRecord`) yerel olarak en yüksek performans ve güvenilirlikle yönetmektedir.

---

## 🔒 Security & Data Preservation Rules

- **No DB Leaks**: Ajanların hiçbir koşulda doğrudan veritabanı sürücülerini ilklendirmesine izin verilmez. Tüm aramalar typed tool kontratları üzerinden yapılır.
- **No Data Pipeline Mutations**: Mevcut PDF ayrıştırma, chunking, embedding, Qdrant koleksiyonları ve Neo4j veritabanı kesinlikle değiştirilmez veya yeniden üretilmez.
