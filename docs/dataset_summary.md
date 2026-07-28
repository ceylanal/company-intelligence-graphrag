# 📊 Company Intelligence GraphRAG - Baseline Dataset Summary

## 🎯 Overview

Company Intelligence GraphRAG projesinin 1. Aşaması (Phase 1: Data & Infrastructure) kapsamında BIST 100 endeksindeki **10 hedef şirket** için 2023, 2024 ve 2025 yıllarına ait **30 resmi faaliyet raporu (PDF)** eksiksiz olarak toplanmış, doğrulanmış ve veri işleme boru hattından geçirilmiştir.

---

## 📈 Veri Seti Metrikleri

| Metrik | Sayı / Değer | Açıklama |
| :--- | :---: | :--- |
| **Hedef Şirket Sayısı** | **10** | BIST 100 endeksindeki öncü şirketler |
| **Toplam Faaliyet Raporu Sayısı** | **30** | 2023, 2024 ve 2025 (30/30 verified) |
| **Toplam Çıkarılan Sayfa Sayısı** | **7,325** | PyMuPDF ile ayıklanan sayfa kayıtları |
| **Toplam Anlamsal Chunk Sayısı** | **25,859** | Sınır korumalı 500-token metin parçaları |
| **Qdrant Vektör Point Sayısı** | **25,859** | 384-boyutlu Cosine vektör koleksiyonu |
| **Eksik / Hatalı Kayıt Sayısı** | **0** | Birebir veri bütünlüğü |
| **Genel Aşama Durumu** | **PASS** | Phase 1 Başarıyla Tamamlandı |

---

## 🏢 Şirket ve Rapor Dağılım Tablosu

| Şirket Kodu | Şirket Unvanı | 2023 Raporu | 2024 Raporu | 2025 Raporu | Toplam Sayfa | Toplam Chunk | Rapor Dili |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **AKBNK** | Akbank T.A.Ş. | ✅ | ✅ | ✅ | 842 | 2,981 | TR |
| **ARCLK** | Arçelik A.Ş. | ✅ | ✅ | ✅ | 694 | 2,410 | TR |
| **ASELS** | Aselsan Elektronik Sanayi A.Ş. | ✅ | ✅ | ✅ | 788 | 2,754 | TR |
| **FROTO** | Ford Otomotiv Sanayi A.Ş. | ✅ | ✅ | ✅ | 712 | 2,504 | EN / TR |
| **KCHOL** | Koç Holding A.Ş. | ✅ | ✅ | ✅ | 750 | 2,680 | EN / TR |
| **MGROS** | Migros Ticaret A.Ş. | ✅ | ✅ | ✅ | 620 | 2,190 | TR / EN |
| **SISE** | Türkiye Şişe ve Cam Fabrikaları A.Ş. | ✅ | ✅ | ✅ | 740 | 2,610 | EN / TR |
| **TCELL** | Turkcell İletişim Hizmetleri A.Ş. | ✅ | ✅ | ✅ | 760 | 2,710 | TR / EN |
| **THYAO** | Türk Hava Yolları A.O. | ✅ | ✅ | ✅ | 715 | 2,520 | EN / TR |
| **TUPRS** | Türkiye Petrol Rafinerileri A.Ş. | ✅ | ✅ | ✅ | 704 | 2,500 | TR |

---

## 📄 Zorunlu Metadata Alanları

Her faaliyet raporu ve vektör kaydı için 8 temel metadata alanı eksiksiz saklanmaktadır:
1. `company`: Şirket ticari unvanı.
2. `ticker`: Şirket BIST borsa kodu (AKBNK, ASELS vb.).
3. `year`: Rapor yılı (2023, 2024, 2025).
4. `report_type`: Doküman türü (`annual_report`).
5. `language`: Doküman dili (`tr` veya `en`).
6. `source_url`: Orijinal indirme bağlantısı.
7. `source_file`: Standart dosya adı (`TICKER__YEAR__annual_report__LANG.pdf`).
8. `sha256`: SHA-256 dijital parmak izi.
