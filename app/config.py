from pathlib import Path
import json
from typing import Dict, Any

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "tvs.json"


def load_tvs() -> Dict[str, Any]:
    """Load TVs dictionary from `config/tvs.json`.

    Returns a mapping of ip -> tv-metadata dict.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tvs", {})
