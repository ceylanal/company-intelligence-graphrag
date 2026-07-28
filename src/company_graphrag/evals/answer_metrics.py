"""Answer quality metrics module: Exact Match, Token F1, Normalized Match, Numeric Accuracy, Completeness, Abstention."""

import re
from collections import Counter
from typing import Any

from company_graphrag.evals.models import AnswerMetricsResult


def normalize_text(text: str | list[str] | Any) -> str:
    """Lower-case, remove punctuation and extra whitespace for normalized matching."""
    if isinstance(text, list):
        text = " ".join(str(item) for item in text if item)
    elif not isinstance(text, str):
        text = str(text or "")
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_numbers(text: str | list[str] | Any) -> set[float]:
    """Extract all numerical values (integers, floats, percentages) from text."""
    if isinstance(text, list):
        text = " ".join(str(item) for item in text if item)
    elif not isinstance(text, str):
        text = str(text or "")
    clean_text = text.replace(",", ".")
    matches = re.findall(r"[-+]?\d*\.\d+|\d+", clean_text)
    numbers = set()
    for m in matches:
        try:
            numbers.add(float(m))
        except ValueError:
            pass
    return numbers


def calculate_exact_match(prediction: str, ground_truth: str, acceptable_answers: list[str] | None = None) -> float:
    """Calculate Exact Match (EM): 1.0 if normalized prediction matches ground truth or any acceptable answer."""
    norm_pred = normalize_text(prediction)
    norm_gt = normalize_text(ground_truth)

    if norm_pred == norm_gt:
        return 1.0

    acceptable = acceptable_answers or []
    for acc in acceptable:
        if norm_pred == normalize_text(acc):
            return 1.0

    return 0.0


def calculate_token_f1(prediction: str, ground_truth: str) -> float:
    """Calculate Token-level F1 score between prediction and ground truth."""
    pred_tokens = normalize_text(prediction).split()
    gt_tokens = normalize_text(ground_truth).split()

    if not pred_tokens or not gt_tokens:
        return 1.0 if pred_tokens == gt_tokens else 0.0

    pred_counter = Counter(pred_tokens)
    gt_counter = Counter(gt_tokens)

    intersection = sum((pred_counter & gt_counter).values())
    if intersection == 0:
        return 0.0

    precision = intersection / len(pred_tokens)
    recall = intersection / len(gt_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    return round(f1, 4)


def calculate_normalized_match(prediction: str, ground_truth: str) -> float:
    """Calculate Normalized String Similarity Match."""
    norm_pred = normalize_text(prediction)
    norm_gt = normalize_text(ground_truth)

    if not norm_pred or not norm_gt:
        return 1.0 if norm_pred == norm_gt else 0.0

    if norm_gt in norm_pred or norm_pred in norm_gt:
        return 1.0

    # Token overlap ratio
    pred_set = set(norm_pred.split())
    gt_set = set(norm_gt.split())
    jaccard = len(pred_set & gt_set) / max(1, len(pred_set | gt_set))
    return round(jaccard, 4)


def calculate_numeric_accuracy(prediction: str, ground_truth: str) -> float:
    """Calculate Numeric Accuracy: ratio of ground truth numerical values correctly present in prediction."""
    gt_nums = extract_numbers(ground_truth)
    if not gt_nums:
        return 1.0  # No numbers in ground truth to check

    pred_nums = extract_numbers(prediction)
    if not pred_nums:
        return 0.0

    matched = gt_nums & pred_nums
    return round(len(matched) / len(gt_nums), 4)


def calculate_answer_completeness(prediction: str, ground_truth: str | list[str]) -> float:
    """Calculate Answer Completeness: recall of ground truth tokens in prediction."""
    pred_set = set(normalize_text(prediction).split())
    gt_set = set(normalize_text(ground_truth).split())
    if not gt_set:
        return 1.0
    hits = pred_set & gt_set
    return round(len(hits) / len(gt_set), 4)


def calculate_abstention_accuracy(is_abstained: bool, answerable: bool) -> float:
    """Calculate Abstention Accuracy: 1.0 if system correctly refused unanswerable query or answered answerable query."""
    expected_abstention = not answerable
    return 1.0 if is_abstained == expected_abstention else 0.0


def evaluate_answer(
    prediction: str,
    ground_truth: str,
    acceptable_answers: list[str] | None = None,
    is_abstained: bool = False,
    answerable: bool = True,
) -> AnswerMetricsResult:
    """Aggregate answer quality metrics into AnswerMetricsResult."""
    return AnswerMetricsResult(
        exact_match=calculate_exact_match(prediction, ground_truth, acceptable_answers),
        token_f1=calculate_token_f1(prediction, ground_truth),
        normalized_match=calculate_normalized_match(prediction, ground_truth),
        numeric_accuracy=calculate_numeric_accuracy(prediction, ground_truth),
        answer_completeness=calculate_answer_completeness(prediction, ground_truth),
        abstention_accuracy=calculate_abstention_accuracy(is_abstained, answerable),
    )
