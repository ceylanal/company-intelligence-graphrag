#!/usr/bin/env python3
"""CLI script for executing semantic vector search queries against Qdrant."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console

from company_graphrag.retrieval import SearchQuery, VectorSearchEngine

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="Search Qdrant vector database using natural language financial queries."
    )
    parser.add_argument("query", type=str, help="Search query string")
    parser.add_argument(
        "--top-k",
        "-k",
        type=int,
        default=5,
        help="Maximum number of results to return (default: 5)",
    )
    parser.add_argument(
        "--score-threshold",
        "-s",
        type=float,
        default=None,
        help="Minimum similarity score threshold (default: None)",
    )
    parser.add_argument(
        "--ticker",
        "-t",
        type=str,
        default=None,
        help="Filter by stock ticker symbol (e.g. ASELS, AKBNK)",
    )
    parser.add_argument(
        "--year",
        "-y",
        type=int,
        default=None,
        help="Filter by report year (e.g. 2024, 2025)",
    )
    parser.add_argument(
        "--language",
        "-l",
        type=str,
        default=None,
        help="Filter by language code (tr or en)",
    )
    parser.add_argument(
        "--collection-name",
        "-c",
        type=str,
        default="company_documents",
        help="Target Qdrant collection name (default: company_documents)",
    )

    args = parser.parse_args()

    search_req = SearchQuery(
        query=args.query,
        top_k=args.top_k,
        score_threshold=args.score_threshold,
        ticker=args.ticker,
        year=args.year,
        language=args.language,
    )

    console.print(f"\n[bold blue]🔍 Executing Semantic Search Query:[/bold blue] [cyan]'{args.query}'[/cyan]\n")

    try:
        engine = VectorSearchEngine(collection_name=args.collection_name)
        response = engine.search(search_req)

        console.print(
            f"[dim]Execution Time: {response.execution_time_ms} ms | Total Hits: {response.total_hits}[/dim]\n"
        )

        if not response.hits:
            console.print("[yellow]No relevant document chunks found matching criteria.[/yellow]\n")
            return

        for idx, hit in enumerate(response.hits, 1):
            console.print(
                f"[bold gold1]Hit #{idx}[/bold gold1] (Score: [bold green]{hit.score}[/bold green]) | [cyan]{hit.company}[/cyan] ({hit.ticker}) | Year: [magenta]{hit.year}[/magenta] | Page: {hit.page_number}"
            )
            console.print(f"[dim]Source: {hit.source_file} (Chunk ID: {hit.chunk_id})[/dim]")

            # Print text snippet preview
            snippet = hit.text if len(hit.text) <= 300 else hit.text[:297] + "..."
            console.print(f"[white]{snippet}[/white]\n" + "─" * 70)

        console.print("\n[bold green]✨ Search completed successfully![/bold green]\n")

    except Exception as err:
        console.print(f"[bold red]Search query failed:[/bold red] {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
