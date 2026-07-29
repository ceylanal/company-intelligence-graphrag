import csv
from pathlib import Path

from scripts.summarize_staging_load import summarize_stage


def test_summarize_stage_reads_locust_aggregate(tmp_path: Path) -> None:
    path = tmp_path / "users-1_stats.csv"
    columns = [
        "Type",
        "Name",
        "Request Count",
        "Failure Count",
        "50%",
        "95%",
        "99%",
        "Max Response Time",
        "Requests/s",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow(
            {
                "Type": "",
                "Name": "Aggregated",
                "Request Count": "20",
                "Failure Count": "0",
                "50%": "12",
                "95%": "25",
                "99%": "30",
                "Max Response Time": "32",
                "Requests/s": "2.5",
            }
        )

    summary = summarize_stage(path, users=1)

    assert summary["success_rate"] == 1.0
    assert summary["p95_latency_ms"] == 25.0
