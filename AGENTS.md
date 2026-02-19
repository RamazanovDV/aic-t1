# AGENTS.md - Developer Guide for LLM Experiment Lab

## Project Overview

PyQt6 GUI for running multiple LLM models in parallel/sequential mode, comparing responses, evaluating results.

## Project Structure

```
/home/eof/dev/aic/t1/
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── llm_experiment_lab/
│   ├── api/client.py       # LLM API client
│   ├── config.py           # Configuration paths
│   ├── core/
│   │   ├── experiment.py      # Experiment runner
│   │   ├── experiment_storage.py  # Save/load
│   │   ├── evaluator.py       # Response evaluation
│   │   └── statistics.py     # Stats dataclasses
│   └── gui/
│       ├── main_window.py     # Main window
│       ├── model_panel.py     # Model I/O panel
│       ├── prompts_area.py    # Prompt input
│       ├── eval_area.py       # Evaluation panel
│       └── settings_dialog.py
```

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run application
python main.py

# Run all tests
pytest

# Run single test file
pytest tests/test_client.py

# Run single test function
pytest tests/test_client.py::test_chat_completion

# Run tests matching pattern
pytest -k "test_api"

# Lint with ruff
pip install ruff && ruff check .

# Auto-fix lint issues
ruff check --fix .

# Type checking
pip install mypy && mypy llm_experiment_lab/
```

## Code Style

### Imports

Order: Standard library → Third-party → Local application.

```python
import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import httpx
from PyQt6.QtWidgets import QMainWindow, QWidget
from PyQt6.QtCore import Qt, pyqtSignal

from ..api.client import LLMAPIClient
from ..core.statistics import ModelStats
```

### Naming

- **Classes**: PascalCase (`LLMAPIClient`, `ModelStats`)
- **Functions/variables**: snake_case (`chat_completion`)
- **Constants**: SCREAMING_SNAKE_CASE (`CONFIG_FILE`)
- **Private methods**: underscore prefix (`_load_config`)

### Type Hints

Always use explicit type hints. Prefer `Optional` over `None`:

```python
def chat_completion(self, model: str, prompt: str, temp: float = 0.7) -> ModelResponse: ...
def get_config(self) -> Optional[ModelConfig]: ...
```

### Dataclasses

Use `@dataclass` with `field(default_factory=dict)` for mutable defaults.

### Error Handling

Catch specific exceptions. Return errors in response objects, not raise:

```python
try:
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    return ModelResponse(..., error=f"HTTP {e.response.status_code}")
```

### Async/Await

Use `asyncio.gather` with `return_exceptions=True`:

```python
async def run_parallel(self, models: List[ModelConfig]) -> List[ModelStats]:
    tasks = [self._run_model(m) for m in models]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r if not isinstance(r, Exception) else ModelStats(error=str(r)) for r in results]
```

### Qt/PyQt6

Use `pyqtSignal` for thread-safe communication, queues for thread-to-GUI data passing, and `super().__init__()` in subclass `__init__`.

### Formatting

4 spaces indentation (no tabs), max 120 characters per line, 2 blank lines between top-level definitions.

### Docstrings

Add docstrings for public classes/functions:

```python
class LLMAPIClient:
    """Client for interacting with LLM API endpoints."""
    
    def chat_completion(self, model: str, prompt: str) -> ModelResponse:
        """Send a chat completion request.
        Args:
            model: Model identifier.
            prompt: User prompt.
        Returns:
            ModelResponse with content and metadata.
        """
```

## Configuration & Dependencies

- Config: `~/.config/llmexplab/config.json`
- Experiments: `~/.config/llmexplab/experiments/` (subdirectory with `experiment.json` + `notes.md`)
- **PyQt6>=6.7.0**: GUI framework
- **httpx>=0.27.0**: Async HTTP client
