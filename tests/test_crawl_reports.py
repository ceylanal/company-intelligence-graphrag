import pytest
from scripts.crawl_reports import is_official_domain, is_report_link


def test_is_official_domain():
    domains = ["akbank.com", "akbankinvestorrelations.com"]

    assert is_official_domain("https://www.akbank.com/tr/reports/2025.pdf", domains) is True
    assert is_official_domain("https://akbankinvestorrelations.com/reports.aspx", domains) is True
    assert is_official_domain("https://www.kap.org.tr/tr/Bildirim/1234", domains) is False
    assert is_official_domain("https://malicious-site.com/akbank.pdf", domains) is False


def test_is_report_link():
    assert is_report_link("https://akbank.com/2025-faaliyet-raporu.pdf", "2025 Faaliyet Raporu") is True
    assert is_report_link("https://akbank.com/doc.pdf", "Annual Report 2024") is True
    assert is_report_link("https://akbank.com/surdurulebilirlik-raporu-2025.pdf", "Sürdürülebilirlik Raporu") is True
    assert is_report_link("https://akbank.com/contact.html", "İletişim") is False
