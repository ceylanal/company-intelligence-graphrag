#!/usr/bin/env python3
"""CLI script for batch embedding text chunks and loading into Qdrant vector DB."""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.table import Table

from company_graphrag.embeddings import EmbeddingConfig, embed_and_ingest_chunks
from company_graphrag.embeddings.pipeline import DEFAULT_CHUNKS_DIR

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Generate dense vector embeddings for chunks and load into Qdrant.")
    parser.add_argument(
        "input_path",
        type=Path,
        nargs="?",
        default=DEFAULT_CHUNKS_DIR,
        help="Input chunk JSONL file or directory (default: data/processed/chunks)",
    )
    parser.add_argument(
        "--collection-name",
        "-c",
        type=str,
        default="company_documents",
        help="Target Qdrant collection name (default: company_documents)",
    )
    parser.add_argument(
        "--model-name",
        "-m",
        type=str,
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="FastEmbed / HuggingFace model name (default: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=64,
        help="Batch size for vector embedding generation and upsert (default: 64)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate embedding pipeline without connecting or writing to Qdrant",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate Qdrant collection before uploading points",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock vectors for testing",
    )

    parser.add_argument(
        "--qdrant-url",
        type=str,
        default="",
        help="Target Qdrant server/cloud URL (default: read from QDRANT_URL environment variable)",
    )
    parser.add_argument(
        "--qdrant-api-key-env",
        type=str,
        default="QDRANT_API_KEY",
        help="Environment variable name for Qdrant API key (default: QDRANT_API_KEY)",
    )

    args = parser.parse_args()
    input_path = args.input_path.resolve()

    if not input_path.exists():
        console.print(f"[bold red]Error:[/bold red] Input path does not exist: {input_path}")
        sys.exit(1)

    config = EmbeddingConfig(
        model_name=args.model_name,
        batch_size=args.batch_size,
        collection_name=args.collection_name,
    )
    qdrant_url = args.qdrant_url or os.environ.get("QDRANT_URL", "")
    qdrant_api_key = os.environ.get(args.qdrant_api_key_env, "")

    console.print("\n[bold blue]🚀 Starting Vector Embedding & Qdrant Pipeline...[/bold blue]\n")
    console.print(f"  • Model: [cyan]{config.model_name}[/cyan]")
    console.print(f"  • Collection: [cyan]{config.collection_name}[/cyan]")
    console.print(f"  • Batch Size: [cyan]{config.batch_size}[/cyan]")
    console.print(f"  • Qdrant Target URL: [cyan]{qdrant_url or 'default/embedded'}[/cyan]")
    console.print(f"  • Dry-Run: [yellow]{args.dry_run}[/yellow]")
    console.print(f"  • Reset Collection: [yellow]{args.reset}[/yellow]\n")

    try:
        summary = embed_and_ingest_chunks(
            input_path=input_path,
            config=config,
            qdrant_url=qdrant_url or None,
            qdrant_api_key=qdrant_api_key or None,
            dry_run=args.dry_run,
            reset_collection=args.reset,
            mock_encoder=args.mock,
        )

        table = Table(title="Embedding & Qdrant Ingestion Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold green")

        table.add_row("Collection Name", summary.collection_name)
        table.add_row("Vector Size (Dimension)", str(summary.vector_size))
        table.add_row("Total Chunks Read", f"{summary.total_chunks:,}")
        table.add_row("Points Upserted to Qdrant", f"[bold green]{summary.total_points_upserted:,}[/bold green]")
        table.add_row("Failed Chunks", f"[red]{summary.failed_chunks}[/red]" if summary.failed_chunks else "0")
        table.add_row("Execution Duration", f"{summary.duration_seconds} sec")

        console.print(table)
        console.print("\n[bold green]✨ Vector embedding and Qdrant ingestion completed![/bold green]\n")

    except Exception as err:
        console.print(f"[bold red]Ingestion failed:[/bold red] {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
