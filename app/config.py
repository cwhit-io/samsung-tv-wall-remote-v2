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


def save_tvs(tvs_dict: Dict[str, Any]) -> None:
    """Save TVs dictionary back to `config/tvs.json`.
    
    Args:
        tvs_dict: A mapping of ip -> tv-metadata dict.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    data["tvs"] = tvs_dict
    
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.write("\n")  # Add trailing newline
