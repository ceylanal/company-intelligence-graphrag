"""Dataset Validator engine verifying Golden Evaluation Dataset integrity, schemas, and SHA-256 checksums."""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field
from structlog import get_logger

from company_graphrag.evals.models import EvaluationSample

logger = get_logger(__name__)


class DatasetValidationReport(BaseModel):
    """Validation report detailing dataset integrity and checksum status."""

    dataset_dir: str
    manifest_exists: bool
    checksums_valid: bool
    total_dev_samples: int
    total_test_samples: int
    invalid_schema_count: int = 0
    duplicate_questions_count: int = 0
    unanswerable_missing_reason_count: int = 0
    status: str = "PASS"
    errors: list[str] = Field(default_factory=list)


class EvaluationDatasetValidator:
    """Validator verifying dataset schema compliance, SHA-256 checksums, and dataset rules."""

    def __init__(self, dataset_dir: Path | None = None) -> None:
        self.dataset_dir = dataset_dir or Path("data/evals")

    def validate_dataset(self) -> DatasetValidationReport:
        """Validate golden_dev.jsonl, golden_test.jsonl, and manifest.json integrity."""
        logger.info("Validating Golden Evaluation Dataset...", dataset_dir=str(self.dataset_dir))

        manifest_path = self.dataset_dir / "manifest.json"
        dev_path = self.dataset_dir / "golden_dev.jsonl"
        test_path = self.dataset_dir / "golden_test.jsonl"

        errors: list[str] = []
        manifest_ok = manifest_path.exists()

        if not manifest_ok:
            errors.append(f"Manifest file not found: {manifest_path}")

        # Validate Checksums
        checksums_ok = True
        if manifest_ok:
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                expected_dev_sha = manifest_data.get("checksums", {}).get("golden_dev.jsonl")
                expected_test_sha = manifest_data.get("checksums", {}).get("golden_test.jsonl")

                if dev_path.exists():
                    actual_dev_sha = hashlib.sha256(dev_path.read_bytes()).hexdigest()
                    if actual_dev_sha != expected_dev_sha:
                        checksums_ok = False
                        errors.append(
                            f"Dev dataset checksum mismatch! Expected: {expected_dev_sha}, Actual: {actual_dev_sha}"
                        )

                if test_path.exists():
                    actual_test_sha = hashlib.sha256(test_path.read_bytes()).hexdigest()
                    if actual_test_sha != expected_test_sha:
                        checksums_ok = False
                        errors.append(
                            f"Test dataset checksum mismatch! Expected: {expected_test_sha}, Actual: {actual_test_sha}"
                        )

            except Exception as err:
                checksums_ok = False
                errors.append(f"Failed to parse manifest checksums: {err}")

        # Validate Schema Compliance & Question Rules
        dev_samples, dev_errs, dev_unans_errs = self._load_and_validate_file(dev_path)
        test_samples, test_errs, test_unans_errs = self._load_and_validate_file(test_path)

        schema_errors_count = dev_errs + test_errs
        unans_missing_reason_count = dev_unans_errs + test_unans_errs

        # Check for duplicates across dev and test
        all_questions = [s.question for s in dev_samples + test_samples]
        unique_questions = set(all_questions)
        duplicates_count = len(all_questions) - len(unique_questions)

        if duplicates_count > 0:
            errors.append(f"Found {duplicates_count} duplicate question strings across dataset splits.")

        overall_status = "PASS" if not errors and schema_errors_count == 0 else "FAIL"

        report = DatasetValidationReport(
            dataset_dir=str(self.dataset_dir),
            manifest_exists=manifest_ok,
            checksums_valid=checksums_ok,
            total_dev_samples=len(dev_samples),
            total_test_samples=len(test_samples),
            invalid_schema_count=schema_errors_count,
            duplicate_questions_count=duplicates_count,
            unanswerable_missing_reason_count=unans_missing_reason_count,
            status=overall_status,
            errors=errors,
        )

        logger.info("Dataset validation completed", status=overall_status, errors_count=len(errors))
        return report

    def _load_and_validate_file(self, file_path: Path) -> tuple[list[EvaluationSample], int, int]:
        """Load JSONL file and validate schema conformity."""
        samples: list[EvaluationSample] = []
        schema_errs = 0
        unans_errs = 0

        if not file_path.exists():
            return samples, 1, 0

        with open(file_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    s = EvaluationSample.model_validate(data)
                    samples.append(s)

                    if not s.answerable and not s.metadata.get("unanswerable_reason"):
                        unans_errs += 1

                except Exception as err:
                    logger.warning("Invalid sample schema", line=line[:50], error=str(err))
                    schema_errs += 1

        return samples, schema_errs, unans_errs
