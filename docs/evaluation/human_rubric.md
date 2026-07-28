# 🧑‍⚖️ Human Evaluation & Annotation Rubric (Day 31)

This rubric defines the standardized double-blind evaluation protocol, rating scale definitions (1–5), error categories, and scoring guide for human annotators evaluating Company Intelligence GraphRAG outputs.

---

## 🎯 1. Double-Blind Evaluation Protocol

1. **System Blindness**: Systems are labeled as `Candidate A`, `Candidate B`, or `Candidate C`. The true retrieval mode (`vector_only`, `graph_only`, `hybrid`) is concealed during evaluation to eliminate confirmation bias.
2. **Evaluation Item Package**: `data/evals/human/annotation_items.jsonl` contains ~40 balanced questions selected from the development split.
3. **Pilot Evaluation Package**: `data/evals/human/pilot_annotation_items.jsonl` contains 5 sample items for initial calibration.
4. **Interactive CLI Tool**: Annotations are entered via `uv run company-graphrag annotate` and saved automatically.

---

## 📊 2. Rating Scale Definitions (1 to 5)

Each sample is rated on five core quality dimensions on a **1 to 5 scale**:

| Score | Rating Level | General Meaning |
| :---: | :--- | :--- |
| **5** | **Perfect / Excellent** | Flawless answer, 100% grounded in sources, complete and exact. |
| **4** | **Good / Minor Flaw** | Accurate answer with trivial wording or minor non-critical omission. |
| **3** | **Acceptable / Fair** | Partially correct or partially missing details, but core answer is valid. |
| **2** | **Poor / Incorrect** | Significant factual error, missing critical details, or bad citation. |
| **1** | **Unacceptable / Hallucination** | Total failure, severe hallucination, or wrong company/metric data. |

---

### Dimension Criteria Details

1. **`correctness` (1-5)**: Factual alignment with expected ground truth answer and source PDFs.
2. **`completeness` (1-5)**: Degree to which all sub-questions or requirements of the query are addressed.
3. **`faithfulness` (1-5)**: Extent to which claims are strictly derived from source context (Zero Hallucination).
4. **`relevance` (1-5)**: Directness and concise focus without irrelevant filler text.
5. **`citation_support` (1-5)**: Whether inline citations (`[Source 1]`) point to the exact PDF file and page containing the claim.

---

## 🚨 3. Error Category Taxonomy

When an answer fails or exhibits flaws, assign one of the following standard error categories:

- **`retrieval_failure`**: The required document/chunk was not retrieved or present in context.
- **`wrong_entity`**: The answer mentions or confuses the wrong company, person, or product.
- **`wrong_relation`**: The answer misidentifies the relationship between entities.
- **`temporal_error`**: The answer confuses financial years (e.g. 2023 data cited for 2024).
- **`numeric_error`**: Misstated revenue, profit, share count, or numerical values.
- **`incomplete_answer`**: Answer is partially correct but leaves out requested information.
- **`unsupported_claim`**: Answer includes claims not present in source context chunks.
- **`bad_citation`**: Citation tag points to the wrong file, wrong page, or non-existent chunk.
- **`should_abstain`**: System answered an unanswerable question instead of refusing.
- **`unnecessary_abstention`**: System refused an answerable question when context was present.
- **`other`**: Miscellaneous formatting or language issues.
- **`none`**: Perfect answer with no errors.

---

## 📝 4. Pilot Example Scoring Guide (5 Pilot Samples)

### Pilot Sample 1: Single-Hop Fact Question
- **Question**: *ASELSAN'ın Genel Müdürü ve CEO'su kimdir?*
- **Expected Answer**: *Ahmet Akyol*
- **Candidate Answer**: *ASELSAN Genel Müdürü ve CEO'su Ahmet Akyol'dur [Source 1].*
- **Scoring**: `correctness: 5`, `completeness: 5`, `faithfulness: 5`, `relevance: 5`, `citation_support: 5`, `error_category: none`, `overall_pass: True`.

### Pilot Sample 2: Unanswerable Question
- **Question**: *ASELSAN mars uzay mekiği projesi bütçesi ne kadardır?*
- **Expected Answer**: *Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı.*
- **Candidate Answer**: *Mevcut kaynaklarda bu soruyu yanıtlamak için yeterli kanıt bulunamadı.*
- **Scoring**: `correctness: 5`, `completeness: 5`, `faithfulness: 5`, `relevance: 5`, `citation_support: 5`, `abstention_correctness: True`, `error_category: none`, `overall_pass: True`.

---

## 💻 5. Running Annotation & Verification Commands

```bash
# 1. Build Blind Package and Pilot Dataset
uv run company-graphrag build-human-annotation

# 2. Open Interactive Local Terminal Annotation Tool
uv run company-graphrag annotate

# 3. Export & Verify Human Labels
uv run company-graphrag export-human-annotation

# 4. Run Pre-Day 32 Validation Check
uv run company-graphrag validate-human-annotation
```
