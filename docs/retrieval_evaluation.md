# 📊 Day 8: Semantic Retrieval Quality Evaluation Report

## 🎯 Executive Summary

Company Intelligence GraphRAG projesinin 8. Günü kapsamında, Qdrant vektör veritabanındaki **25.859 chunk** üzerinde 10 BIST şirketini kapsayan **22 adet finansal değerlendirme sorgusu** çalıştırılmış ve sonuçların ilgililiği detaylı olarak ölçümlenmiştir.

---

## 📈 Temel Kalite Metrikleri

| Metrik | Değer | Hedef / Başarım |
| :--- | :---: | :---: |
| **Toplam Test Sorgusu Sayısı** | **22** | 10 Şirket + Sektörel |
| **Top-1 İlgililik Oranı (Relevance Rate)** | **%100.0** | %90+ |
| **Top-3 Isabet Oranı (Hit Rate)** | **%100.0** | %95+ |
| **Top-5 Isabet Oranı (Hit Rate)** | **%100.0** | %100 |
| **Ortalama Top-1 Benzerlik Skoru (Cosine)** | **0.7318** | Yüksek Anlamsal Uygunluk |
| **Ortalama Genel Benzerlik Skoru** | **0.6933** | Güvenilir Eşik |
| **Şirket Filtresi Doğruluk Oranı (Ticker Filter Accuracy)** | **%100.0** | %100 Kusursuz |

---

## 🔍 Sorgu Bazlı Detaylı Değerlendirme Tablosu

| ID | Sorgu Metni | Ticker | Top-1 Skoru | Top-1 İlgili | Top-5 İlgili Sayısı |
| :-: | :--- | :-: | :-: | :-: | :-: |
| **q01** | ASELSAN 2025 yılı net satış gelirleri ve bakiye sipariş miktarı | `ASELS` | 0.7117 | ✅ Evet | 5/5 |
| **q02** | Akbank 2024 dijital bankacılık mobil müşteri sayısı ve TL kredi büyümesi | `AKBNK` | 0.7781 | ✅ Evet | 5/5 |
| **q03** | Ford Otosan EV investment battery plant and electric vehicle production 2024 | `FROTO` | 0.7245 | ✅ Evet | 5/5 |
| **q04** | Turkcell 2024 fiber omurga altyapısı ve Superbox abone sayısı | `TCELL` | 0.7654 | ✅ Evet | 5/5 |
| **q05** | Türk Hava Yolları 2023 toplam yolcu sayısı ve yolcu gelirleri | `THYAO` | 0.8208 | ✅ Evet | 5/5 |
| **q06** | Tüpraş 2025 yılı rafineri üretim kapasitesi ve kapasite kullanım oranı | `TUPRS` | 0.7556 | ✅ Evet | 5/5 |
| **q07** | Şişecam 2025 yılı net satışları ve küresel cam ihracatı | `SISE` | 0.6918 | ✅ Evet | 5/5 |
| **q08** | Koç Holding 2024 kombine gelirleri ve net aktif değeri büyümesi | `KCHOL` | 0.7702 | ✅ Evet | 5/5 |
| **q09** | Arçelik 2025 sürdürülebilirlik hedefleri ve karbon nötr yatırımları | `ARCLK` | 0.7881 | ✅ Evet | 5/5 |
| **q10** | Migros 2024 yılı mağaza sayısı ve online satış kanalları büyümesi | `MGROS` | 0.7675 | ✅ Evet | 5/5 |
| **q11** | Akbank 2023 yılı özkaynak kârlılığı ve sermaye yeterlilik rasyosu | `AKBNK` | 0.7651 | ✅ Evet | 5/5 |
| **q12** | ASELSAN 2024 Ar-Ge harcamaları ve teknoloji üssü yatırımları | `ASELS` | 0.6777 | ✅ Evet | 5/5 |
| **q13** | Ford Otosan 2023 toplam araç ihracatı ve ihracat gelirleri | `FROTO` | 0.7214 | ✅ Evet | 5/5 |
| **q14** | Turkcell 2025 yılı siber güvenlik ve veri merkezi çözümleri | `TCELL` | 0.7164 | ✅ Evet | 5/5 |
| **q15** | Türk Hava Yolları 2025 filodaki uçak sayısı ve kargo taşımacılığı | `THYAO` | 0.7939 | ✅ Evet | 5/5 |
| **q16** | Tüpraş 2024 yılı yeşil hidrojen ve sıfır karbon dönüşüm planı | `TUPRS` | 0.8785 | ✅ Evet | 5/5 |
| **q17** | Şişecam 2023 düzcam ve ambalaj camı üretim miktarları | `SISE` | 0.5961 | ✅ Evet | 5/5 |
| **q18** | Koç Holding 2025 yenilenebilir enerji yatırımları ve ESG performansı | `KCHOL` | 0.7007 | ✅ Evet | 5/5 |
| **q19** | Arçelik 2024 Avrupa pazarı pazar payı ve Beko marka performansı | `ARCLK` | 0.6055 | ✅ Evet | 5/5 |
| **q20** | Migros 2025 yılı Mion ve Makroonline yeni format büyümesi | `MGROS` | 0.6033 | ✅ Evet | 5/5 |
| **q21** | BIST şirketleri 2024 yılı enflasyon muhasebesi ve TMS 29 finansal etkileri | `ALL` | 0.7486 | ✅ Evet | 5/5 |
| **q22** | BIST 100 şirketlerinin 2025 yılı iklim riski ve sera gazı emisyon azaltım hedefleri | `ALL` | 0.7189 | ✅ Evet | 5/5 |

---

## ⚠️ Düşük Performans Gösteren veya Hatalı Sorguların Analizi

Tüm sorguların Top-1 sonuçları %100 ilgili bulunmuştur! Hiçbir başarısız sorgu tespit edilmemiştir.

---

## 🏆 Gün 8 Kabul Kararı

- **Karar:** **KABUL EDİLDİ (ACCEPTED)** ✅
- **Gerekçe:** Top-1 ilgililik oranı %100.0, Top-3 isabet oranı %100.0 ve Top-5 isabet oranı %100.0 seviyesine ulaşmış, metadata filtreleri %100.0 kusursuz doğrulukla çalışmıştır. Vektör arama motoru Day 9 GraphRAG entegrasyonu için tamamen hazırdır.
