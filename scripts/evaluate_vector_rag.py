#!/usr/bin/env python3
"""Standalone script to execute Vector RAG Final Evaluation & Benchmark Suite."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from company_graphrag.evaluation.vector_rag_evaluator import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_QUESTIONS_PATH,
    VectorRAGEvaluator,
)


def main() -> None:
    """Run vector RAG evaluation and print summary metrics."""
    print("🚀 Starting Vector RAG Benchmark Evaluation Suite...")
    evaluator = VectorRAGEvaluator()
    summary, results = evaluator.evaluate_all(
        questions_path=DEFAULT_QUESTIONS_PATH,
        output_dir=DEFAULT_OUTPUT_DIR,
    )
    evaluator.close()

    print("\n" + "=" * 70)
    print("📊 VECTOR RAG PHASE 2 EVALUATION SUMMARY METRICS")
    print("=" * 70)
    print(f"Total Benchmark Questions     : {summary.total_questions}")
    print(f"Hit Rate @ 1                  : {summary.hit_rate_at_1:.2%}")
    print(f"Hit Rate @ 3                  : {summary.hit_rate_at_3:.2%}")
    print(f"Hit Rate @ 5                  : {summary.hit_rate_at_5:.2%}")
    print(f"Mean Reciprocal Rank (MRR)   : {summary.mrr:.4f}")
    print(f"Top-3 Company Match Accuracy  : {summary.top3_company_accuracy:.2%}")
    print(f"Top-3 Year Match Accuracy     : {summary.top3_year_accuracy:.2%}")
    print(f"Citation Validity Rate        : {summary.citation_validity_rate:.2%}")
    print(f"Unanswerable Context Acc.     : {summary.insufficient_context_accuracy:.2%}")
    print(f"Average Total Duration        : {summary.avg_total_ms:.2f} ms")
    print(f"Overall Sign-off Status       : {summary.overall_status}")
    print("=" * 70)

    if summary.overall_status != "PASS":
        print("❌ Evaluation FAILED acceptance criteria:")
        for r in summary.status_reasons:
            print(f"  • {r}")
        sys.exit(1)

    print("✨ Vector RAG Phase 2 Sign-off PASSED cleanly!")
    sys.exit(0)


if __name__ == "__main__":
    main()
