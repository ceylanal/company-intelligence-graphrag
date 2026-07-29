from scripts.staging_baseline import build_summary, evaluate_sample


def test_staging_baseline_marks_supported_answer_as_correct() -> None:
    sample = {
        "id": "sample-1",
        "question_type": "single_hop_fact",
        "answerable": True,
        "expected_answer": "Turkcell 1994 yılında kurulmuştur.",
        "acceptable_answers": ["1994"],
        "source_file": "TCELL__2024__annual_report__tr.pdf",
    }

    result = evaluate_sample(
        sample,
        "Turkcell 1994 yılında kurulmuştur [Source 1] TCELL__2024__annual_report__tr.pdf",
        12.3,
    )

    assert result["correct"] is True
    assert result["citation_source_match"] is True
    assert result["hallucinated"] is False


def test_staging_baseline_summary_keeps_proxy_labels() -> None:
    summary = build_summary(
        [
            {
                "http_status": 200,
                "correct": True,
                "token_f1": 0.8,
                "faithfulness_proxy": True,
                "citation_count": 1,
                "citation_source_match": True,
                "retrieval_recall_proxy": True,
                "question_type": "multi_hop_graph",
                "hallucinated": False,
                "latency_ms": 10.0,
            }
        ],
        "sha256:" + "a" * 64,
    )

    assert summary["correctness_rate"] == 1.0
    assert summary["multi_hop_success_rate"] == 1.0
    assert "proxy" in summary["methodology"]["faithfulness"]
