#!/usr/bin/env python3
"""CLI script for batch chunking page JSONL documents into text chunks."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.table import Table

from company_graphrag.chunking.chunker import (
    DEFAULT_CHUNKS_DIR,
    DEFAULT_PAGES_DIR,
    chunk_document_directory,
    chunk_document_file,
)

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Chunk page JSONL documents into text chunk records for GraphRAG.")
    parser.add_argument(
        "input_path",
        type=Path,
        nargs="?",
        default=DEFAULT_PAGES_DIR,
        help="Input page JSONL file or directory (default: data/processed/pages)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=DEFAULT_CHUNKS_DIR,
        help="Output root directory for chunks (default: data/processed/chunks)",
    )
    parser.add_argument(
        "--target-tokens",
        "-t",
        type=int,
        default=500,
        help="Target token count per chunk (default: 500)",
    )
    parser.add_argument(
        "--overlap-tokens",
        "-v",
        type=int,
        default=50,
        help="Overlap token count between chunks (default: 50)",
    )
    parser.add_argument(
        "--overwrite",
        "-f",
        action="store_true",
        help="Overwrite existing chunk JSONL files",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Disable recursive directory scanning",
    )

    args = parser.parse_args()
    input_path = args.input_path.resolve()

    if not input_path.exists():
        console.print(f"[bold red]Error:[/bold red] Input path does not exist: {input_path}")
        sys.exit(1)

    if input_path.is_file():
        console.print(f"\n[bold blue]📄 Chunking single JSONL file:[/bold blue] {input_path.name}\n")
        try:
            chunks = chunk_document_file(
                input_path,
                output_dir=args.output_dir,
                target_tokens=args.target_tokens,
                overlap_tokens=args.overlap_tokens,
                overwrite=args.overwrite,
            )
            tokens = [c.token_count for c in chunks]

            table = Table(title="Single Document Chunking Result")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="bold green")

            table.add_row("Document ID", chunks[0].document_id if chunks else input_path.stem)
            table.add_row("Total Chunks Created", str(len(chunks)))
            table.add_row("Target Tokens / Overlap", f"{args.target_tokens} / {args.overlap_tokens}")
            table.add_row(
                "Min / Max / Avg Tokens",
                f"{min(tokens) if tokens else 0} / {max(tokens) if tokens else 0} / {round(sum(tokens) / len(tokens), 1) if tokens else 0}",
            )
            table.add_row(
                "Output File",
                str(args.output_dir / (chunks[0].ticker if chunks else "") / f"{input_path.stem}_chunks.jsonl"),
            )

            console.print(table)
            console.print("\n[bold green]✨ File chunking completed successfully![/bold green]\n")
        except Exception as err:
            console.print(f"[bold red]Chunking failed:[/bold red] {err}")
            sys.exit(1)

    elif input_path.is_dir():
        console.print(f"\n[bold blue]📁 Chunking directory:[/bold blue] {input_path}\n")
        summary = chunk_document_directory(
            input_path,
            output_dir=args.output_dir,
            target_tokens=args.target_tokens,
            overlap_tokens=args.overlap_tokens,
            overwrite=args.overwrite,
            recursive=not args.no_recursive,
        )

        table = Table(title="Directory Chunking Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold")

        table.add_row("Total Page JSONL Files", str(summary.total_documents))
        table.add_row(
            "Processed / Succeeded",
            f"[green]{summary.total_documents - summary.failed_documents - summary.skipped_documents}[/green]",
        )
        table.add_row("Skipped Files", f"[yellow]{summary.skipped_documents}[/yellow]")
        table.add_row("Failed Files", f"[red]{summary.failed_documents}[/red]")
        table.add_row("Total Chunks Created", f"[bold green]{summary.total_chunks_created:,}[/bold green]")
        table.add_row("Target Size / Overlap", f"{args.target_tokens} / {args.overlap_tokens} tokens")
        table.add_row(
            "Token Stats (Min / Max / Avg)",
            f"{summary.min_tokens} / {summary.max_tokens} / {summary.avg_tokens_per_chunk}",
        )

        console.print(table)
        console.print()

        if summary.errors:
            console.print("[bold red]Errors encountered during batch chunking:[/bold red]")
            for err_info in summary.errors:
                console.print(f"  - [red]{err_info['file']}:[/red] {err_info['error']}")
            console.print()

        console.print("[bold green]✨ Batch chunking completed![/bold green]\n")


if __name__ == "__main__":
    main()
