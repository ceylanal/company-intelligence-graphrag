"""CLI entry point for company-graphrag."""

from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from company_graphrag.config import settings

app = typer.Typer(
    name="company-graphrag",
    help="Company Intelligence GraphRAG CLI tool",
    add_completion=False,
)
console = Console()


@app.callback()
def main_callback() -> None:
    """Company Intelligence GraphRAG CLI tool."""
    pass


def check_qdrant() -> tuple[bool, str]:
    """Check Qdrant HTTP service health."""
    url = f"{settings.effective_qdrant_url}/healthz"
    try:
        response = httpx.get(url, timeout=3.0)
        if response.status_code == 200:
            return True, f"Online ({settings.effective_qdrant_url})"
        return False, f"HTTP {response.status_code} from {url}"
    except Exception as e:
        return False, f"Connection failed: {e}"


def check_neo4j() -> tuple[bool, str]:
    """Check Neo4j HTTP service health."""
    url = settings.effective_neo4j_http_url
    try:
        auth: Any = (
            (settings.neo4j_username, settings.neo4j_password) if settings.neo4j_password else None
        )
        response = httpx.get(url, auth=auth, timeout=3.0, follow_redirects=True)
        if response.status_code in (200, 301, 302):
            return True, f"Online ({url})"
        return False, f"HTTP {response.status_code} from {url}"
    except Exception as e:
        return False, f"Connection failed: {e}"


@app.command()
def doctor(
    strict: bool = typer.Option(
        False, "--strict", "-s", help="Exit with non-zero code if any check fails"
    ),
) -> None:
    """Diagnose local Qdrant and Neo4j database connections."""
    console.print("\n[bold blue]🏥 Running System Doctor Checks...[/bold blue]\n")

    table = Table(title="Service Health Diagnostics")
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Endpoint", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    qdrant_ok, qdrant_msg = check_qdrant()
    qdrant_status = "[green]✓ HEALTHY[/green]" if qdrant_ok else "[red]✗ OFFLINE[/red]"
    table.add_row("Qdrant Vector DB", settings.effective_qdrant_url, qdrant_status, qdrant_msg)

    neo4j_ok, neo4j_msg = check_neo4j()
    neo4j_status = "[green]✓ HEALTHY[/green]" if neo4j_ok else "[red]✗ OFFLINE[/red]"
    table.add_row(
        "Neo4j Knowledge Graph", settings.effective_neo4j_http_url, neo4j_status, neo4j_msg
    )

    console.print(table)
    console.print()

    if not (qdrant_ok and neo4j_ok):
        console.print(
            "[yellow]⚠️  Note: Some local services are unreachable. Ensure Qdrant & Neo4j containers are running.[/yellow]\n"
        )
        if strict:
            raise typer.Exit(code=1)
    else:
        console.print("[bold green]✨ All system health checks passed successfully![/bold green]\n")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
