import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..config import EXPERIMENTS_DIR


def _ensure_experiments_dir() -> Path:
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    return EXPERIMENTS_DIR


@dataclass
class ExperimentData:
    id: str = ""
    name: str = ""
    timestamp: str = ""
    prompts: Dict[str, str] = field(default_factory=dict)
    models: List[Dict[str, Any]] = field(default_factory=list)
    execution: Dict[str, Any] = field(default_factory=dict)
    eval_model: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    model_responses: Dict[Any, Any] = field(default_factory=dict)
    model_stats: Dict[Any, Any] = field(default_factory=dict)
    eval_result: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("notes", None)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ExperimentData":
        data_copy = data.copy()
        data_copy.pop("notes", None)
        return cls(**data_copy)


def _serialize_stats(stats_dict: Dict[Any, Any]) -> Dict[str, Any]:
    serialized = {}
    for key, value in stats_dict.items():
        str_key = str(key)
        if hasattr(value, "__dict__"):
            serialized[str_key] = {
                "model_name": value.model_name,
                "response_time": value.response_time,
                "prompt_tokens": value.prompt_tokens,
                "completion_tokens": value.completion_tokens,
                "total_tokens": value.total_tokens,
                "content": value.content,
                "reasoning": value.reasoning,
                "timestamp": value.timestamp.isoformat() if value.timestamp else "",
                "error": value.error,
                "raw_request": value.raw_request,
                "raw_response": value.raw_response,
            }
        else:
            serialized[str_key] = value
    return serialized


def _serialize_responses(responses_dict: Dict[Any, Any]) -> Dict[str, Any]:
    return {str(k): v for k, v in responses_dict.items()}


def _deserialize_stats(serialized: Dict[str, Any]) -> Dict[int, Any]:
    from datetime import datetime
    deserialized = {}
    for key, value in serialized.items():
        int_key = int(key)
        if isinstance(value, dict) and "model_name" in value:
            ts = value.get("timestamp")
            if ts:
                ts = datetime.fromisoformat(ts)
            deserialized[int_key] = type(
                "ModelStats",
                (),
                {
                    "model_name": value.get("model_name", ""),
                    "response_time": value.get("response_time", 0),
                    "prompt_tokens": value.get("prompt_tokens", 0),
                    "completion_tokens": value.get("completion_tokens", 0),
                    "total_tokens": value.get("total_tokens", 0),
                    "content": value.get("content", ""),
                    "reasoning": value.get("reasoning"),
                    "timestamp": ts,
                    "error": value.get("error"),
                    "raw_request": value.get("raw_request", {}),
                    "raw_response": value.get("raw_response", {}),
                },
            )()
        else:
            deserialized[int_key] = value
    return deserialized


def _get_experiment_dir_by_id(exp_id: str) -> Optional[Path]:
    for exp_dir in EXPERIMENTS_DIR.iterdir():
        if not exp_dir.is_dir():
            continue
        exp_file = exp_dir / "experiment.json"
        if not exp_file.exists():
            continue
        with open(exp_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("id") == exp_id:
            return exp_dir
    return None


def _get_experiment_dir(name: str, timestamp: Optional[str] = None) -> Path:
    safe_name = "".join(c for c in name if c.isalnum() or c in "_- ")[:50].strip()
    return EXPERIMENTS_DIR / safe_name


def save_experiment(
    name: str,
    prompts: Dict[str, str],
    models: List[Dict[str, Any]],
    execution: Dict[str, Any],
    eval_model: Dict[str, Any],
    results: Dict[str, Any],
    model_responses: Dict[str, Any],
    model_stats: Dict[str, Any],
    eval_result: str = "",
    notes: str = "",
    existing_id: str = "",
    existing_timestamp: str = "",
) -> str:
    _ensure_experiments_dir()

    exp_id = existing_id or str(uuid.uuid4())
    timestamp = existing_timestamp or datetime.now().isoformat()

    if existing_id:
        exp_dir = _get_experiment_dir_by_id(existing_id)
        if exp_dir:
            exp_dir.mkdir(parents=True, exist_ok=True)
        else:
            exp_dir = _get_experiment_dir(name)
    else:
        exp_dir = _get_experiment_dir(name)
    
    exp_dir.mkdir(parents=True, exist_ok=True)

    data = ExperimentData(
        id=exp_id,
        name=name,
        timestamp=timestamp,
        prompts=prompts,
        models=models,
        execution=execution,
        eval_model=eval_model,
        results=results,
        model_responses=_serialize_responses(model_responses),
        model_stats=_serialize_stats(model_stats),
        eval_result=eval_result,
    )

    with open(exp_dir / "experiment.json", "w", encoding="utf-8") as f:
        json.dump(data.to_dict(), f, indent=2, ensure_ascii=False)

    with open(exp_dir / "notes.md", "w", encoding="utf-8") as f:
        f.write(notes)

    return exp_id


def load_experiment(exp_dir: Path) -> Optional[ExperimentData]:
    exp_file = exp_dir / "experiment.json"
    if not exp_file.exists():
        return None

    with open(exp_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    exp_data = ExperimentData.from_dict(data)
    exp_data.model_stats = _deserialize_stats(exp_data.model_stats)
    exp_data.model_responses = {int(k): v for k, v in exp_data.model_responses.items()}

    notes_file = exp_dir / "notes.md"
    if notes_file.exists():
        with open(notes_file, "r", encoding="utf-8") as f:
            exp_data.notes = f.read()

    return exp_data


def list_experiments() -> List[Dict[str, Any]]:
    _ensure_experiments_dir()
    experiments = []

    for exp_dir in sorted(EXPERIMENTS_DIR.iterdir(), reverse=True):
        if not exp_dir.is_dir():
            continue
        exp_file = exp_dir / "experiment.json"
        if not exp_file.exists():
            continue

        with open(exp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        experiments.append({
            "id": data.get("id", ""),
            "name": data.get("name", ""),
            "timestamp": data.get("timestamp", ""),
            "dir": str(exp_dir),
        })

    return experiments


def update_notes(exp_id: str, notes: str) -> bool:
    for exp_dir in EXPERIMENTS_DIR.iterdir():
        if not exp_dir.is_dir():
            continue
        exp_file = exp_dir / "experiment.json"
        if not exp_file.exists():
            continue

        with open(exp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("id") == exp_id:
            data["notes"] = notes
            with open(exp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            with open(exp_dir / "notes.md", "w", encoding="utf-8") as f:
                f.write(notes)
            return True

    return False


def get_experiment_by_id(exp_id: str) -> Optional[ExperimentData]:
    for exp_dir in EXPERIMENTS_DIR.iterdir():
        if not exp_dir.is_dir():
            continue
        exp_file = exp_dir / "experiment.json"
        if not exp_file.exists():
            continue

        with open(exp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("id") == exp_id:
            return load_experiment(exp_dir)

    return None


def experiment_exists(name: str) -> Optional[Dict[str, str]]:
    for exp_dir in EXPERIMENTS_DIR.iterdir():
        if not exp_dir.is_dir():
            continue
        exp_file = exp_dir / "experiment.json"
        if not exp_file.exists():
            continue

        with open(exp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("name") == name:
            return {
                "id": data.get("id", ""),
                "timestamp": data.get("timestamp", ""),
                "dir": str(exp_dir),
            }

    return None


def delete_experiment(exp_id: str) -> bool:
    for exp_dir in EXPERIMENTS_DIR.iterdir():
        if not exp_dir.is_dir():
            continue
        exp_file = exp_dir / "experiment.json"
        if not exp_file.exists():
            continue

        with open(exp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("id") == exp_id:
            import shutil
            shutil.rmtree(exp_dir)
            return True

    return False
