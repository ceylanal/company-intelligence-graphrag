"""Tests for output secret, citation, and grounding guardrails."""

import pytest

from company_graphrag.safety.models import GuardrailAction
from company_graphrag.safety.output_guardrails import SAFE_BLOCKED_ANSWER, OutputGuardrails


def decision_codes(result: object) -> set[str]:
    """Extract codes without coupling assertions to decision ordering."""
    return {decision.code for decision in result.decisions}  # type: ignore[attr-defined]


def test_fake_api_key_is_redacted() -> None:
    fake_key = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"

    result = OutputGuardrails().evaluate(f"Tanılama anahtarı: {fake_key}")

    assert result.action == GuardrailAction.REDACT
    assert fake_key not in result.text
    assert "[REDACTED]" in result.text
    assert "secret_redacted" in decision_codes(result)


def test_password_connection_string_and_private_key_are_redacted() -> None:
    output = (
        "password=super-secret-value\n"
        "postgresql://admin:unsafe-password@db.internal/finance\n"
        "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
    )

    result = OutputGuardrails().evaluate(output)

    assert result.action == GuardrailAction.REDACT
    assert "super-secret-value" not in result.text
    assert "unsafe-password" not in result.text
    assert "BEGIN PRIVATE KEY" not in result.text


def test_uncited_financial_claim_is_blocked() -> None:
    result = OutputGuardrails().evaluate(
        "ASELS'in 2024 cirosu 120 milyar TL olarak gerçekleşti.",
        valid_citations={1},
        retrieved_context="ASELS yıllık raporu.",
    )

    assert result.action == GuardrailAction.BLOCK
    assert result.text == SAFE_BLOCKED_ANSWER
    assert "uncited_financial_claim" in decision_codes(result)


def test_valid_citation_answer_is_not_modified() -> None:
    answer = "ASELS'in 2024 cirosu 120 milyar TL olarak gerçekleşti [Source 1]."
    context = "ASELS 2024 yılında 120 milyar TL ciro elde etti."

    result = OutputGuardrails().evaluate(
        answer,
        valid_citations={1},
        retrieved_context=context,
    )

    assert result.action == GuardrailAction.ALLOW
    assert result.text == answer
    assert result.citations == [1]
    assert result.decisions == []


def test_fabricated_citation_is_removed() -> None:
    result = OutputGuardrails().evaluate(
        "Yönetim stratejik önceliklerini açıkladı [Source 99].",
        valid_citations={1, 2},
    )

    assert result.action == GuardrailAction.REDACT
    assert "[Source 99]" not in result.text
    assert "invalid_citation_redacted" in decision_codes(result)


def test_system_prompt_leak_is_blocked() -> None:
    result = OutputGuardrails().evaluate("System prompt: You are an internal financial research assistant.")

    assert result.blocked
    assert result.text == SAFE_BLOCKED_ANSWER
    assert "internal_configuration_leak" in decision_codes(result)


def test_claim_outside_context_is_warned() -> None:
    result = OutputGuardrails().evaluate(
        "Şirket yeni bir uzay turizmi programını küresel müşteriler için başlattı.",
        retrieved_context="Şirketin enerji verimliliği ve sürdürülebilirlik yatırımları raporda açıklandı.",
    )

    assert result.action == GuardrailAction.WARN
    assert result.text.startswith("[UYARI: Retrieved context ile doğrulanamadı]")
    assert "outside_retrieved_context" in decision_codes(result)


def test_safe_error_does_not_echo_exception_details() -> None:
    payload = OutputGuardrails.safe_error("err_123")

    assert payload["error_id"] == "err_123"
    assert "password" not in str(payload).lower()
    assert "traceback" not in str(payload).lower()


def test_unexpected_output_guardrail_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    guardrails = OutputGuardrails()

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated guardrail failure")

    monkeypatch.setattr(guardrails, "_evaluate", fail)
    result = guardrails.evaluate("Normal cevap")

    assert result.blocked
    assert result.text == SAFE_BLOCKED_ANSWER
    assert "output_guardrail_failure" in decision_codes(result)
