# AGENTS.md - Developer Guide for LLM Experiment Lab

## Project Overview

A PyQt6 GUI application for experimenting with LLM models. The application allows running multiple LLM models in parallel or sequential mode, comparing their responses, and evaluating results.

## Project Structure

```
/home/eof/dev/aic/t1/
├── main.py                    # Application entry point
├── config.json                # User configuration (gitignored)
├── config.json.example        # Configuration template
├── requirements.txt           # Python dependencies
├── llm_experiment_lab/
│   ├── api/
│   │   └── client.py         # LLM API client (httpx)
│   ├── core/
│   │   ├── experiment.py     # Experiment runner
│   │   ├── evaluator.py      # Response evaluation
│   │   └── statistics.py      # Stats dataclasses
│   └── gui/
│       ├── main_window.py     # Main application window
│       ├── model_panel.py     # Model input/output panel
│       ├── prompts_area.py    # Prompt input area
│       ├── eval_area.py       # Evaluation panel
│       ├── settings_dialog.py # Settings dialog
│       └── json_viewer.py     # JSON viewer widget
```

## Commands

### Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Testing

This project currently has no test suite. When adding tests:

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_client.py

# Run a single test function
pytest tests/test_client.py::test_chat_completion

# Run tests matching a pattern
pytest -k "test_api"
```

### Linting and Type Checking

Recommended tooling (not currently configured):

```bash
# Install linting tools
pip install ruff mypy

# Run ruff linter
ruff check .

# Run ruff with auto-fix
ruff check --fix .

# Run mypy type checker
mypy llm_experiment_lab/
```

## Code Style Guidelines

### Imports

Order imports in the following groups with blank lines between groups:

1. Standard library imports
2. Third-party imports
3. Local application imports

```python
# Standard library
import asyncio
import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

# Third-party
import httpx
from PyQt6.QtWidgets import QMainWindow, QWidget
from PyQt6.QtCore import Qt, pyqtSignal

# Local application
from ..api.client import LLMAPIClient
from ..core.experiment import Experiment
from ..core.statistics import ModelStats
```

### Naming Conventions

- **Classes**: PascalCase (e.g., `LLMAPIClient`, `ModelStats`, `MainWindow`)
- **Functions/variables**: snake_case (e.g., `chat_completion`, `model_responses`)
- **Constants**: SCREAMING_SNAKE_CASE (e.g., `CONFIG_FILE`, `DEFAULT_TIMEOUT`)
- **Private methods**: prefix with underscore (e.g., `_load_config`, `_create_client`)

### Type Hints

Always use type hints for function signatures. Prefer explicit types over `Any`:

```python
# Good
def chat_completion(
    self,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
) -> ModelResponse:
    ...

# Good - using Optional for nullable returns
def get_model_config(self) -> Optional[ModelConfig]:
    ...

# Avoid
def get_model_config(self):  # No type hint
    ...
```

### Dataclasses

Use `@dataclass` for simple data containers:

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ModelStats:
    model_name: str
    response_time: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    content: str = ""
    raw_request: Dict[str, Any] = field(default_factory=dict)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
```

### Error Handling

Catch specific exceptions, not broad `Exception`:

```python
# Good
try:
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
    try:
        error_data = e.response.json()
        error_msg = error_data.get("error", {}).get("message", error_msg)
    except Exception:
        pass
    return ModelResponse(..., error=error_msg)

# Avoid
try:
    response.raise_for_status()
except Exception as e:  # Too broad
    return ModelResponse(..., error=str(e))
```

Return error information in the response object rather than raising for expected error cases (API failures, cancellation).

### Async/Await Patterns

Use `asyncio` for concurrent operations. Always handle `CancelledError`:

```python
async def run_parallel(self, models: List[ModelConfig]) -> List[ModelStats]:
    tasks = []
    for i, model in enumerate(models):
        task = self._run_model(...)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            stats = ModelStats(..., error=str(result))
            final_results.append(stats)
        else:
            final_results.append(result)
    
    return final_results
```

### Qt/PyQt6 Conventions

- Use `pyqtSignal` for thread-safe communication:
```python
class Worker(QObject):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(int, dict, dict)
```

- Use queue for thread-to-GUI communication:
```python
self.log_queue = queue.Queue()
self.ui_queue = queue.Queue()
```

- Always call `super().__init__()` in subclass `__init__`

### Code Formatting

- Use 4 spaces for indentation (no tabs)
- Maximum line length: 120 characters
- Use blank lines sparingly to group related code (2 blank lines between top-level definitions)
- No trailing whitespace

### Docstrings

Add docstrings for public classes and functions:

```python
class LLMAPIClient:
    """Client for interacting with LLM API endpoints."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        """Initialize the API client.
        
        Args:
            api_key: API key for authentication.
            base_url: Base URL for the API endpoint.
        """
        ...
```

### Configuration

- Configuration is stored in `config.json` (gitignored)
- Use `config.json.example` as a template
- Default settings are defined in code (see `MainWindow._default_settings`)

### Threading

GUI operations must run on the main thread. Use threading for:
- API calls
- Long-running computations

Pass data back to GUI via queues or Qt signals:

```python
def run_in_thread(self):
    def do_work():
        result = self._fetch_data()
        self.ui_queue.put({"type": "data", "result": result})
    
    thread = threading.Thread(target=do_work)
    thread.start()
```

## Common Development Tasks

### Adding a New GUI Panel

1. Create a new file in `llm_experiment_lab/gui/`
2. Import PyQt6 widgets
3. Create a QWidget subclass
4. Define signals using `pyqtSignal`
5. Add the panel to `MainWindow._init_ui()`

### Adding a New API Endpoint

1. Add method to `LLMAPIClient` in `api/client.py`
2. Return a dataclass with response data and any errors
3. Handle all exception types with appropriate error messages

### Adding Configuration Options

1. Add default value in `MainWindow._default_settings()`
2. Add UI control in `SettingsDialog`
3. Load in `_load_config()` or `_load_saved_models()`
4. Save in `_save_config()`

## Dependencies

- **PyQt6>=6.7.0**: GUI framework
- **httpx>=0.27.0**: Async HTTP client
- **pydantic>=2.0.0**: Data validation (available but not heavily used)
- **pyyaml>=6.0.0**: YAML parsing (available but not heavily used)
