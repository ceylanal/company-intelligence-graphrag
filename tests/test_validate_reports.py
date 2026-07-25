import pytest
import hashlib
from pathlib import Path
import fitz
from scripts.validate_reports import validate_pdf_content, infer_year_from_filename_or_text, infer_document_type


@pytest.fixture
def sample_company_cfg():
    return {
        "id": "akbank",
        "name": "Akbank T.A.Ş.",
        "aliases": ["Akbank", "Akbank T.A.Ş.", "Akbank T.A.S."],
        "official_domains": ["akbank.com", "akbankinvestorrelations.com"],
        "years": [2023, 2024, 2025]
    }


def create_dummy_pdf(tmp_path: Path, content_lines: list[str], filename: str) -> Path:
    pdf_path = tmp_path / filename
    doc = fitz.open()
    for p in range(3):
        page = doc.new_page()
        for i, line in enumerate(content_lines):
            page.insert_text((50, 50 + i * 20), line)
    doc.save(str(pdf_path))
    doc.close()

    # Ensure size > 10KB by appending valid PDF comment padding
    with open(pdf_path, "ab") as f:
        f.write(b"\n% PADDING " + b"0" * 15000 + b"\n")

    return pdf_path


def test_validate_pdf_content_success(tmp_path, sample_company_cfg):
    pdf_path = create_dummy_pdf(
        tmp_path,
        ["Akbank T.A.Ş. 2025 Yılı Entegre Faaliyet Raporu", "Finansal Tablolar ve Sorumluluk Beyanı"],
        "Akbank_Faaliyet_Raporu_2025.pdf"
    )

    res = validate_pdf_content(pdf_path, sample_company_cfg)
    assert res["status"] == "verified"
    assert res["year"] == 2025
    assert res["detected_company"] == "Akbank T.A.Ş."


def test_validate_pdf_content_rejection_mismatched_company(tmp_path, sample_company_cfg):
    """Test that a report from a different institution (e.g. Albaraka Türk) is rejected and quarantined for Akbank."""
    pdf_path = create_dummy_pdf(
        tmp_path,
        ["ALBARAKA TÜRK KATILIM BANKASI A.Ş. 2025 Yılı Finansal Raporu", "Konsolide Bilanço"],
        "AKBNK__annual_report__2025__tr__v1.pdf"
    )

    res = validate_pdf_content(pdf_path, sample_company_cfg)
    assert res["status"] == "quarantined"
    assert "Company mismatch" in res["reason"]


def test_infer_document_type():
    assert infer_document_type("Akbank_Faaliyet_Raporu_2025.pdf", "") == "annual_report"
    assert infer_document_type("Akbank_Surdurulebilirlik_Raporu.pdf", "") == "sustainability_report"
    assert infer_document_type("Akbank_Investor_Presentation_2026_Q1.pdf", "") == "investor_presentation"


def test_infer_year_from_filename():
    assert infer_year_from_filename_or_text("Akbank_Report_2024.pdf", "Some text") == 2024
    assert infer_year_from_filename_or_text("Report.pdf", "Akbank 2023 Annual Report") == 2023
