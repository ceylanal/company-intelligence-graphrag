# Day 2 Data Collection Infrastructure Documentation

## 1. Overview

This document describes the Day 2 data collection pipeline for the `company-intelligence-graphrag` repository. The goal is to collect official financial and sustainability reports from 10 major Turkish companies across diverse sectors, establishing a high-quality dataset for hybrid GraphRAG evaluation.

## 2. Target Scope

### 2.1 Target Companies & Sectors (10 Companies)

| Ticker | Company Name | Sector |
| :--- | :--- | :--- |
| **ASELS** | Aselsan Elektronik Sanayi ve Ticaret A.Ş. | Savunma Sanayii |
| **THYAO** | Türk Hava Yolları A.O. | Havacılık & Ulaştırma |
| **TUPRS** | Türkiye Petrol Rafinerileri A.Ş. | Enerji & Petrol |
| **FROTO** | Ford Otomotiv Sanayi A.Ş. | Otomotiv |
| **ARCLK** | Arçelik A.Ş. | Dayanıklı Tüketim |
| **TCELL** | Turkcell İletişim Hizmetleri A.Ş. | Telekomünikasyon |
| **SISE** | Türkiye Şişe ve Cam Fabrikaları A.Ş. | Cam & Kimyasallar |
| **AKBNK** | Akbank T.A.Ş. | Bankacılık |
| **KCHOL** | Koç Holding A.Ş. | Holding |
| **MGROS** | Migros Ticaret A.Ş. | Perakende |

### 2.2 Document Targets (3 per Company, 30 Total)

1. **2025 Annual / Integrated Report** (`annual_report`, period: `2025`)
2. **2025 Sustainability / TSRS Report** (`sustainability_report`, period: `2025`)
3. **2026 Q1 Investor Presentation** (`investor_presentation`, period: `2026_Q1`)

### 2.3 Official Sources & Anti-Duplication Policy

- **Sources**: Strictly restricted to official company Investor Relations (IR) websites and Kamuyu Aydınlatma Platformu (KAP).
- **Uniqueness**: Identical PDFs are never stored under two separate document classifications. SHA-256 hash checks enforce 100% uniqueness across the dataset.

---

## 3. Standard File Naming & Directory Structure

### 3.1 File Naming Standard

All downloaded raw PDF files follow the strict format:
```text
{ticker}__{document_type}__{period}__{language}__v1.pdf
```

*Example*:
- `ASELS__annual_report__2025__tr__v1.pdf`
- `FROTO__sustainability_report__2025__tr__v1.pdf`
- `TUPRS__investor_presentation__2026_Q1__tr__v1.pdf`

### 3.2 Workspace Layout

```text
company-intelligence-graphrag/
├── config/
│   └── companies.yaml          # Target companies & document URLs config
├── data/
│   ├── manifest.csv            # Central metadata manifest CSV
│   └── raw/                    # Git-ignored local raw PDF storage
│       ├── ASELS/
│       ├── THYAO/
│       ├── TUPRS/
│       └── ...
├── docs/
│   └── data_collection.md      # Data collection documentation
└── scripts/
    ├── download_pdfs.py        # Automated URL fetcher & manifest writer
    └── validate_pdfs.py        # PDF integrity & SHA-256 duplicate checker
```

### 3.3 Git Exclusion Policy

To prevent bloating the repository with binary data, `data/raw/` is added to `.gitignore`. Only configuration files, manifests, scripts, and documentation are tracked in Git.

---

## 4. Manifest Schema Reference (`data/manifest.csv`)

The manifest records full operational metadata for every document target:

| Column Header | Type | Description |
| :--- | :--- | :--- |
| `ticker` | String | Stock ticker symbol (e.g. `ASELS`) |
| `company` | String | Full legal name of company |
| `sector` | String | Primary industry sector |
| `document_type` | String | Document classification (`annual_report`, `sustainability_report`, `investor_presentation`) |
| `period` | String | Period covered (`2025`, `2026_Q1`) |
| `language` | String | ISO language code (`tr`, `en`) |
| `source_url` | String | Official IR or KAP URL |
| `local_path` | String | Workspace-relative path to downloaded PDF |
| `sha256` | String | 64-character hex SHA-256 checksum |
| `page_count` | Integer | Total page count |
| `file_size` | Integer | File size in bytes |
| `download_status` | String | Status (`success`, `failed`) |

---

## 5. Usage & Execution Instructions

### 5.1 Step 1: Run PDF Download Pipeline

To download all 30 target documents and generate `data/manifest.csv`:

```bash
python3 scripts/download_pdfs.py
```

### 5.2 Step 2: Validate PDF Integrity & Hash Uniqueness

To run automated checks (%PDF- magic signature, >10KB file size, >0 page count, and duplicate SHA-256 hash detection):

```bash
python3 scripts/validate_pdfs.py
```
