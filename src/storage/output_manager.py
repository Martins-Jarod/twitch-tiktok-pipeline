from pathlib import Path
from loguru import logger

class OutputManager:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_output_path(self, filename: str) -> Path:
        return self.output_dir / filename

    def list_outputs(self):
        return list(self.output_dir.glob("*.mp4"))

    def cleanup_old_files(self, max_files: int = 50):
        files = sorted(self.output_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime)
        while len(files) > max_files:
            files.pop(0).unlink()
            logger.info(f"Fichier supprimé pour libérer de l'espace")
