"""Unit tests for Evaluation Framework metrics and EvaluationEngine (Day 27)."""

from pathlib import Path

from company_graphrag.evals import (
    EvaluationEngine,
    QuestionType,
    calculate_abstention_accuracy,
    calculate_answer_completeness,
    calculate_citation_coverage,
    calculate_citation_precision,
    calculate_citation_recall,
    calculate_cited_page_accuracy,
    calculate_entity_recall,
    calculate_exact_match,
    calculate_graph_path_recall,
    calculate_mrr,
    calculate_ndcg_at_k,
    calculate_normalized_match,
    calculate_numeric_accuracy,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_relation_recall,
    calculate_token_f1,
    evaluate_answer,
    evaluate_citations,
    evaluate_graph_reasoning,
    evaluate_retrieval,
)


def test_retrieval_metrics() -> None:
    """Test retrieval metrics: Recall@k, Precision@k, MRR, nDCG@k."""
    retrieved = ["c1", "c2", "c3", "c4", "c5"]
    gt = ["c2", "c6"]

    assert calculate_recall_at_k(retrieved, gt, k=1) == 0.0
    assert calculate_recall_at_k(retrieved, gt, k=3) == 0.5
    assert calculate_precision_at_k(retrieved, gt, k=2) == 0.5
    assert calculate_mrr(retrieved, gt) == 0.5  # First hit 'c2' at rank 2
    assert calculate_ndcg_at_k(retrieved, gt, k=5) > 0.0

    res = evaluate_retrieval(
        retrieved_chunk_ids=retrieved,
        expected_chunk_ids=gt,
        retrieved_sources=["doc1.pdf"],
        expected_sources=["doc1.pdf"],
        retrieved_pages=[1, 2],
        expected_pages=[2, 3],
    )
    assert res.recall_at_3 == 0.5
    assert res.source_recall == 1.0
    assert res.page_recall == 0.5


def test_answer_metrics() -> None:
    """Test answer quality metrics: EM, Token F1, Numeric Accuracy, Abstention."""
    pred = "Aselsan 2024 cirosu 80 Milyar TL olarak gerçekleşti."
    gt = "Aselsan 2024 yılı cirosu 80 Milyar TL olmuştur."

    assert calculate_exact_match("80", "80", acceptable_answers=["80 Milyar"]) == 1.0
    assert calculate_token_f1(pred, gt) > 0.70
    assert calculate_normalized_match(pred, gt) > 0.50
    assert calculate_numeric_accuracy(pred, gt) == 1.0  # Matches 2024 and 80
    assert calculate_answer_completeness(pred, gt) > 0.70
    assert calculate_abstention_accuracy(is_abstained=True, answerable=False) == 1.0
    assert calculate_abstention_accuracy(is_abstained=False, answerable=True) == 1.0
    assert calculate_abstention_accuracy(is_abstained=False, answerable=False) == 0.0

    ans_res = evaluate_answer(pred, gt, is_abstained=False, answerable=True)
    assert ans_res.numeric_accuracy == 1.0
    assert ans_res.abstention_accuracy == 1.0


def test_citation_metrics() -> None:
    """Test citation metrics: Precision, Recall, Coverage, Page Accuracy."""
    cited_src = ["doc1.pdf", "doc2.pdf"]
    rel_src = ["doc1.pdf"]

    assert calculate_citation_precision(cited_src, rel_src) == 0.5
    assert calculate_citation_recall(cited_src, rel_src) == 1.0
    assert calculate_citation_coverage(cited_src, claim_count=2) == 1.0
    assert calculate_cited_page_accuracy(cited_pages=[1, 4], expected_pages=[1, 2]) == 0.5

    cit_res = evaluate_citations(cited_src, rel_src, cited_pages=[1], expected_pages=[1])
    assert cit_res.citation_precision == 0.5
    assert cit_res.citation_recall == 1.0


def test_graph_metrics() -> None:
    """Test graph metrics: Entity Recall, Relation Recall, Path Recall."""
    ret_ent = ["Aselsan", "ASELFLIR-500"]
    exp_ent = ["Aselsan", "ASELFLIR-500", "Defense"]

    assert calculate_entity_recall(ret_ent, exp_ent) == round(2 / 3, 4)
    assert calculate_relation_recall(["PRODUCES"], ["PRODUCES", "OPERATES_IN"]) == 0.5
    assert (
        calculate_graph_path_recall(
            ["(Aselsan) ➔ PRODUCES ➔ (ASELFLIR-500)"], ["(Aselsan) ➔ PRODUCES ➔ (ASELFLIR-500)"]
        )
        == 1.0
    )

    g_res = evaluate_graph_reasoning(ret_ent, exp_ent, ["PRODUCES"], ["PRODUCES"])
    assert g_res.relation_recall == 1.0


def test_evaluation_engine_end_to_end(tmp_path: Path) -> None:
    """Test EvaluationEngine loading samples, evaluating method, and exporting reports."""
    sample_file = tmp_path / "test_samples.jsonl"
    engine = EvaluationEngine(sample_path=sample_file)

    samples = engine.load_samples()
    assert len(samples) >= 3
    assert samples[0].question_type in list(QuestionType)

    sample = samples[0]
    sample_res = engine.evaluate_sample_method(
        sample=sample,
        method="hybrid",
        retrieved_chunk_ids=sample.source_chunk_ids,
        retrieved_sources=[sample.source_file] if isinstance(sample.source_file, str) else sample.source_file,
        retrieved_pages=sample.source_pages,
        predicted_answer=sample.expected_answer,
        cited_sources=[sample.source_file] if isinstance(sample.source_file, str) else sample.source_file,
        cited_pages=sample.source_pages,
        retrieved_entities=sample.expected_entities,
        retrieved_relations=sample.expected_relations,
        retrieved_paths=sample.expected_graph_path,
        latency_ms=30.0,
        is_abstained=False,
    )

    assert sample_res.overall_sample_score > 0.80
    assert sample_res.retrieval.mrr == 1.0

    run_report = engine.aggregate_run_report(samples, [sample_res])
    json_path, md_path = engine.export_reports(run_report, output_dir=tmp_path)

    assert json_path.exists()
    assert md_path.exists()
