import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
