import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional


CONFIG_DIR = Path.home() / ".config" / "llmexplab"
CONFIG_FILE = CONFIG_DIR / "config.json"
EXPERIMENTS_DIR = CONFIG_DIR / "experiments"


def _ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def _migrate_old_config() -> bool:
    old_config = Path("config.json")
    if old_config.exists() and not CONFIG_FILE.exists():
        shutil.move(str(old_config), str(CONFIG_FILE))
        return True
    return False


def get_default_config() -> dict:
    return {
        "api": {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "verify_ssl": True,
        },
        "execution": {
            "mode": "parallel",
            "delay_seconds": 1,
        },
        "eval_model": {
            "name": "gpt-4",
            "custom_endpoint": "",
            "temperature": 0.3,
        },
        "models": [
            {"name": "gpt-4", "custom_endpoint": "", "temperature": 0.7, "top_p": 1.0, "top_k": -1},
            {"name": "gpt-3.5-turbo", "custom_endpoint": "", "temperature": 0.7, "top_p": 1.0, "top_k": -1},
            {"name": "gpt-4o-mini", "custom_endpoint": "", "temperature": 0.7, "top_p": 1.0, "top_k": -1},
        ],
    }


def load_config() -> dict:
    _ensure_config_dir()
    _migrate_old_config()
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return get_default_config()
    return get_default_config()


def save_config(settings: dict) -> None:
    _ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=2)
