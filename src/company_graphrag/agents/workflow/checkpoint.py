"""Lightweight JSON file-based checkpoint persistence for ResearchState."""

from pathlib import Path

from company_graphrag.agents.schema import ResearchState


class CheckpointNotFoundError(Exception):
    """Raised when checkpoint file for a given run_id does not exist."""

    pass


class CheckpointCorruptError(Exception):
    """Raised when checkpoint file is corrupted or unparseable."""

    pass


class JSONCheckpointSaver:
    """Persists ResearchState objects to local JSON files."""

    def __init__(self, checkpoint_dir: str | Path = "data/checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_filepath(self, run_id: str) -> Path:
        clean_run_id = run_id.strip()
        if not clean_run_id.endswith(".json"):
            filename = f"{clean_run_id}.json"
        else:
            filename = clean_run_id
        return self.checkpoint_dir / filename

    def save_checkpoint(self, state: ResearchState) -> str:
        """Save ResearchState to local JSON file."""
        filepath = self._get_filepath(state.run_id)
        json_data = state.model_dump_json(indent=2)

        filepath.write_text(json_data, encoding="utf-8")
        return str(filepath)

    def load_checkpoint(self, run_id: str) -> ResearchState:
        """Load ResearchState from local JSON file."""
        filepath = self._get_filepath(run_id)

        if not filepath.exists():
            raise CheckpointNotFoundError(
                f"Checkpoint file for run_id '{run_id}' not found at path: {filepath.absolute()}"
            )

        try:
            content = filepath.read_text(encoding="utf-8")
            state = ResearchState.model_validate_json(content)
            return state
        except Exception as e:
            raise CheckpointCorruptError(
                f"Checkpoint file '{filepath}' is corrupted or invalid: {str(e)}"
            ) from e

    def list_checkpoints(self) -> list[str]:
        """List all available checkpoint run_ids."""
        if not self.checkpoint_dir.exists():
            return []
        files = self.checkpoint_dir.glob("*.json")
        return [f.stem for f in files]

    def delete_checkpoint(self, run_id: str) -> bool:
        """Delete checkpoint file if it exists."""
        filepath = self._get_filepath(run_id)
        if filepath.exists():
            filepath.unlink()
            return True
        return False
