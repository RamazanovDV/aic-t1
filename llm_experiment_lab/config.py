import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


CONFIG_DIR = Path.home() / ".config" / "llmexplab"
CONFIG_FILE = CONFIG_DIR / "config.json"
EXPERIMENTS_DIR = CONFIG_DIR / "experiments"


@dataclass
class EndpointConfig:
    id: str
    name: str
    url: str
    api_key: str


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


def _migrate_to_endpoints(config: dict) -> dict:
    if "endpoints" in config:
        return config
    
    api = config.get("api", {})
    api_key = api.get("api_key", "")
    base_url = api.get("base_url", "https://api.openai.com/v1")
    
    endpoint_id = "default"
    config["endpoints"] = [
        {
            "id": endpoint_id,
            "name": "Default",
            "url": base_url,
            "api_key": api_key,
        }
    ]
    config["default_endpoint_id"] = endpoint_id
    
    for model in config.get("models", []):
        if model.get("custom_endpoint"):
            model["endpoint_id"] = endpoint_id
        else:
            model["endpoint_id"] = endpoint_id
        if "custom_endpoint" in model:
            del model["custom_endpoint"]
        if "custom_api_token" in model:
            del model["custom_api_token"]
    
    eval_model = config.get("eval_model", {})
    if eval_model.get("custom_endpoint"):
        eval_model["endpoint_id"] = endpoint_id
    else:
        eval_model["endpoint_id"] = endpoint_id
    if "custom_endpoint" in eval_model:
        del eval_model["custom_endpoint"]
    
    if "api" in config:
        del config["api"]
    
    return config


def get_default_config() -> dict:
    return {
        "endpoints": [
            {
                "id": "default",
                "name": "OpenAI",
                "url": "https://api.openai.com/v1",
                "api_key": "",
            }
        ],
        "default_endpoint_id": "default",
        "execution": {
            "mode": "parallel",
            "delay_seconds": 1,
        },
        "eval_model": {
            "name": "gpt-4",
            "endpoint_id": "default",
            "temperature": 0.3,
            "system_prompt": "",
            "user_prompt_template": "",
        },
        "models": [
            {"name": "gpt-4", "endpoint_id": "default", "temperature": 0.7, "top_p": 1.0, "top_k": -1},
            {"name": "gpt-3.5-turbo", "endpoint_id": "default", "temperature": 0.7, "top_p": 1.0, "top_k": -1},
            {"name": "gpt-4o-mini", "endpoint_id": "default", "temperature": 0.7, "top_p": 1.0, "top_k": -1},
        ],
    }


def load_config() -> dict:
    _ensure_config_dir()
    _migrate_old_config()
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                return _migrate_to_endpoints(config)
        except Exception:
            return get_default_config()
    return get_default_config()


def save_config(settings: dict) -> None:
    _ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=2)
