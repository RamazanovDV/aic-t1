import json
import os
import threading
import queue
from functools import partial

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QMessageBox, QSplitter,
    QStatusBar, QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

from ..api.client import LLMAPIClient
from ..core.experiment import Experiment
from ..core.evaluator import Evaluator
from ..core.statistics import Statistics
from .model_panel import ModelPanel
from .prompts_area import PromptsArea
from .eval_area import EvalArea
from .settings_dialog import SettingsDialog


CONFIG_FILE = "config.json"


class Worker(QObject):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(int, dict, dict)
    complete_signal = pyqtSignal()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLM Experiment Lab")
        self.setMinimumSize(1200, 800)

        self.settings = {}
        self.client = None
        self.experiment = None
        self.evaluator = None
        self.statistics = Statistics()

        self.model_responses = {}
        self.model_stats = {}
        self.model_json = {}

        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        
        self._load_config()
        self._init_ui()
        self._create_client()
        self._start_log_timer()
        self._start_ui_timer()

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.settings = json.load(f)
            except Exception:
                self.settings = self._default_settings()
        else:
            self.settings = self._default_settings()

    def _default_settings(self):
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

    def _save_config(self):
        try:
            model_configs = []
            for panel in self.model_panels:
                config = panel.get_model_config()
                model_configs.append({
                    "name": config.name,
                    "custom_endpoint": config.custom_endpoint,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                })
            self.settings["models"] = model_configs
            
            model_lists = {}
            api_cfg = self.settings.get("api", {})
            base_url = api_cfg.get("base_url", "")
            
            for panel in self.model_panels:
                endpoint = panel.endpoint_edit.text() or base_url
                if endpoint not in model_lists:
                    model_lists[endpoint] = []
                current_items = [panel.model_combo.itemText(i) for i in range(panel.model_combo.count())]
                if current_items and current_items[0]:
                    model_lists[endpoint] = current_items
            
            eval_endpoint = self.eval_area.eval_endpoint.text() or base_url
            if eval_endpoint not in model_lists:
                model_lists[eval_endpoint] = []
            eval_items = [self.eval_area.eval_model_combo.itemText(i) for i in range(self.eval_area.eval_model_combo.count())]
            if eval_items and eval_items[0]:
                model_lists[eval_endpoint] = eval_items
            
            self.settings["model_lists"] = model_lists
            
            self.settings["prompts"] = {
                "system": self.prompts_area.get_system_prompt(),
                "user": self.prompts_area.get_user_prompt(),
            }
            
            self.settings["eval_model"] = {
                "name": self.eval_area.eval_model_combo.currentText(),
                "custom_endpoint": self.eval_area.eval_endpoint.text(),
                "temperature": self.eval_area.eval_temp_spin.value(),
            }
            
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not save config: {e}")

    def _create_client(self):
        api_cfg = self.settings.get("api", {})
        self.client = LLMAPIClient(
            api_key=api_cfg.get("api_key", ""),
            base_url=api_cfg.get("base_url", "https://api.openai.com/v1"),
            verify_ssl=api_cfg.get("verify_ssl", True),
        )
        self.experiment = Experiment(self.client)
        self.evaluator = Evaluator(self.client)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Vertical)

        models_layout = QHBoxLayout()
        models_widget = QWidget()
        self.model_panels = [
            ModelPanel("Model 1"),
            ModelPanel("Model 2"),
            ModelPanel("Model 3"),
        ]
        for i, panel in enumerate(self.model_panels):
            panel.dropdown_opened.connect(self._on_dropdown_opened)
            panel.run_clicked.connect(lambda idx=i: self._run_single(idx))
            panel.stop_clicked.connect(lambda idx=i: self._stop_model(idx))
            models_layout.addWidget(panel)
        models_widget.setLayout(models_layout)
        splitter.addWidget(models_widget)

        control_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run All")
        self.run_btn.clicked.connect(self._run_all)
        control_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        control_layout.addStretch()

        self.refresh_models_btn = QPushButton("Refresh Models")
        self.refresh_models_btn.clicked.connect(self._refresh_all_models)
        control_layout.addWidget(self.refresh_models_btn)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self._show_settings)
        control_layout.addWidget(self.settings_btn)

        control_widget = QWidget()
        control_widget.setLayout(control_layout)
        splitter.addWidget(control_widget)

        self.prompts_area = PromptsArea()
        splitter.addWidget(self.prompts_area)

        self.eval_area = EvalArea()
        self.eval_area.evaluate_clicked.connect(self._run_evaluation)
        self.eval_area.set_evaluate_enabled(False)
        splitter.addWidget(self.eval_area)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setStretchFactor(3, 1)

        layout.addWidget(splitter)

        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setMaximumHeight(100)
        self.log_widget.setPlaceholderText("Log output...")
        layout.addWidget(self.log_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self._load_saved_models()

    def _load_saved_models(self):
        saved_models = self.settings.get("models", [])
        for i, panel in enumerate(self.model_panels):
            if i < len(saved_models):
                model_data = saved_models[i]
                panel.set_model(model_data.get("name", ""))
                panel.endpoint_edit.setText(model_data.get("custom_endpoint", ""))
                panel.temp_spin.setValue(model_data.get("temperature", 0.7))
                panel.top_p_spin.setValue(model_data.get("top_p", 1.0))
                panel.top_k_spin.setValue(model_data.get("top_k", -1))

        api_cfg = self.settings.get("api", {})
        base_url = api_cfg.get("base_url", "")
        model_lists = self.settings.get("model_lists", {})
        
        for panel in self.model_panels:
            endpoint = panel.endpoint_edit.text() or base_url
            if endpoint in model_lists and model_lists[endpoint]:
                panel.set_model_list(model_lists[endpoint])
        
        eval_endpoint = self.eval_area.eval_endpoint.text() or base_url
        if eval_endpoint in model_lists and model_lists[eval_endpoint]:
            current = self.eval_area.eval_model_combo.currentText()
            self.eval_area.eval_model_combo.clear()
            self.eval_area.eval_model_combo.addItems(model_lists[eval_endpoint])
            if current in model_lists[eval_endpoint]:
                self.eval_area.eval_model_combo.setCurrentText(current)

        saved_prompts = self.settings.get("prompts", {})
        if saved_prompts:
            self.prompts_area.set_system_prompt(saved_prompts.get("system", ""))
            self.prompts_area.set_user_prompt(saved_prompts.get("user", ""))

        saved_eval = self.settings.get("eval_model", {})
        if saved_eval:
            self.eval_area.set_eval_model(saved_eval.get("name", "gpt-4"))
            self.eval_area.eval_temp_spin.setValue(saved_eval.get("temperature", 0.3))
            self.eval_area.eval_endpoint.setText(saved_eval.get("custom_endpoint", ""))

    def _log(self, message: str):
        self.log_queue.put(message)

    def _start_log_timer(self):
        self._log_timer = QTimer()
        self._log_timer.timeout.connect(self._process_log_queue)
        self._log_timer.start(100)

    def _process_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_widget.append(msg)
            except queue.Empty:
                break

    def _start_ui_timer(self):
        self._ui_timer = QTimer()
        self._ui_timer.timeout.connect(self._process_ui_queue)
        self._ui_timer.start(100)

    def _process_ui_queue(self):
        while not self.ui_queue.empty():
            try:
                op = self.ui_queue.get_nowait()
                op_type = op.get("type")
                if op_type == "set_status":
                    panel = op.get("panel")
                    status = op.get("status")
                    panel.set_status(status)
                elif op_type == "set_response":
                    panel = op.get("panel")
                    content = op.get("content")
                    stats = op.get("stats")
                    panel.set_response(content, stats)
                    if op.get("req_json") and op.get("res_json"):
                        panel.set_json(op.get("req_json"), op.get("res_json"))
                elif op_type == "enable_run":
                    self.run_btn.setEnabled(op.get("enabled", True))
                elif op_type == "enable_stop":
                    self.stop_btn.setEnabled(op.get("enabled", False))
                elif op_type == "enable_eval":
                    self.eval_area.set_evaluate_enabled(op.get("enabled", True))
                elif op_type == "set_statusbar":
                    self.status_bar.showMessage(op.get("message"))
                elif op_type == "eval_result":
                    self.eval_area.set_eval_result(op.get("result", ""))
                elif op_type == "model_complete":
                    idx = op.get("index")
                    stat = op.get("stat")
                    panel = op.get("panel")
                    config = op.get("config")
                    
                    panel.set_running(False)
                    
                    if stat.error:
                        self._update_panel_error(panel, stat, stat.error)
                    else:
                        content = stat.content
                        req_json = stat.raw_request
                        res_json = stat.raw_response
                        self._update_panel_success(panel, content, stat, req_json, res_json)
                        
                        self.model_responses[idx] = {
                            "model": config.name,
                            "content": content,
                        }
                        self.model_json[idx] = {
                            "request": req_json,
                            "response": res_json,
                        }
                    
                    self.model_stats[idx] = stat
                    
                elif op_type == "eval_json":
                    self.eval_area.set_eval_json(
                        op.get("request", {}),
                        op.get("response", {})
                    )
                elif op_type == "update_models":
                    models = op.get("models", [])
                    endpoint = op.get("endpoint", "")
                    self._update_model_lists(models, endpoint)
            except queue.Empty:
                break

    def _refresh_all_models(self):
        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            self._log("No API key configured")
            return

        endpoints = set()
        base_url = api_cfg.get("base_url", "")
        if base_url:
            endpoints.add(base_url)

        for panel in self.model_panels:
            endpoint = panel.endpoint_edit.text()
            if endpoint:
                endpoints.add(endpoint)

        eval_endpoint = self.eval_area.eval_endpoint.text()
        if eval_endpoint:
            endpoints.add(eval_endpoint)

        self._log(f"Refreshing models for {len(endpoints)} endpoints: {endpoints}")

        for endpoint in endpoints:
            self._refresh_models(endpoint)

    def _refresh_models(self, endpoint: str = ""):
        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            self._log("No API key configured")
            return

        base_url = endpoint if endpoint else api_cfg.get("base_url", "")
        self._log(f"Fetching models from {base_url}/models...")
        
        def fetch_models():
            try:
                import httpx
                headers = {"Authorization": f"Bearer {api_cfg.get('api_key', '')}"}
                with httpx.Client(verify=api_cfg.get("verify_ssl", True)) as client:
                    response = client.get(f"{base_url}/models", headers=headers, timeout=30.0)
                    self._log(f"Response status: {response.status_code}")
                    self._log(f"Response body: {response.text[:2000]}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        models = [m.get("id") for m in data.get("data", [])]
                        self._log(f"Parsed models: {models}")
                        self.ui_queue.put({"type": "update_models", "models": models, "endpoint": endpoint})
                    else:
                        self._log(f"Error: {response.status_code} - {response.text[:500]}")
            except Exception as e:
                import traceback
                self._log(f"Error: {str(e)}")
                self._log(traceback.format_exc())

        thread = threading.Thread(target=fetch_models)
        thread.start()

    def _update_model_lists(self, models: list, endpoint: str = ""):
        if not models:
            self._log("No models returned from API")
            return
        
        api_cfg = self.settings.get("api", {})
        base_url = api_cfg.get("base_url", "")
        
        is_default_endpoint = endpoint == base_url
        
        updated = False
        
        for i, panel in enumerate(self.model_panels):
            panel_endpoint = panel.endpoint_edit.text()
            should_update = (
                (endpoint and panel_endpoint == endpoint) or
                (is_default_endpoint and not panel_endpoint)
            )
            if should_update:
                panel.set_model_list(models)
                updated = True
        
        eval_endpoint = self.eval_area.eval_endpoint.text()
        should_update_eval = (
            (endpoint and eval_endpoint == endpoint) or
            (is_default_endpoint and not eval_endpoint)
        )
        if should_update_eval:
            current = self.eval_area.eval_model_combo.currentText()
            self.eval_area.eval_model_combo.clear()
            self.eval_area.eval_model_combo.addItems(models)
            if current in models:
                self.eval_area.eval_model_combo.setCurrentText(current)
            updated = True
        
        if updated:
            self._log(f"Loaded {len(models)} models from API")

    def _on_dropdown_opened(self):
        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            return
        self._refresh_models()

    def _run_single(self, index: int):
        if index >= len(self.model_panels):
            return

        system_prompt = self.prompts_area.get_system_prompt()
        user_prompt = self.prompts_area.get_user_prompt()

        if not system_prompt and not user_prompt:
            QMessageBox.warning(self, "Warning", "Please enter at least one prompt")
            return

        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            QMessageBox.warning(self, "Warning", "Please set API key in Settings")
            return

        self._create_client()

        panel = self.model_panels[index]
        config = panel.get_model_config()

        if index in self.model_responses:
            del self.model_responses[index]
        if index in self.model_stats:
            del self.model_stats[index]
        if index in self.model_json:
            del self.model_json[index]

        panel.clear_response()
        panel.set_running(True)
        self._log(f"Starting single model run: {config.name}...")

        self._set_all_run_buttons_enabled(False)
        self.eval_area.set_evaluate_enabled(False)
        self.stop_btn.setEnabled(True)
        self._log(f"Stop button enabled: {self.stop_btn.isEnabled()}")

        def on_complete(idx, stat, model_name):
            self.ui_queue.put({
                "type": "model_complete",
                "index": idx,
                "stat": stat,
                "model_name": model_name,
                "panel": panel,
                "config": config,
            })

        def run_single_model():
            import asyncio
            import json
            import traceback
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                req_json = {
                    "model": config.name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k if config.top_k > 0 else None,
                }
                self._log(f"--- Model REQUEST ---")
                self._log(json.dumps(req_json, indent=2, ensure_ascii=False)[:500])
                self._log("--- END REQUEST ---")

                stat = loop.run_until_complete(
                    self.experiment.run_single(
                        system_prompt,
                        user_prompt,
                        config,
                        index,
                        lambda idx, status, model_nm: self._progress_callback(idx, status, config.name),
                        on_complete
                    )
                )

                if stat.error:
                    self._update_panel_error(panel, stat, stat.error)
                else:
                    content = stat.content
                    req_json = stat.raw_request
                    res_json = stat.raw_response
                    self._update_panel_success(panel, content, stat, req_json, res_json)

                    self.model_responses[index] = {
                        "model": config.name,
                        "content": content,
                    }
                    self.model_json[index] = {
                        "request": req_json,
                        "response": res_json,
                    }

                self.model_stats[index] = stat

                self._on_single_complete()
                panel.set_running(False)
            except Exception as e:
                self._log(f"ERROR: {str(e)}")
                self._log(traceback.format_exc())
                self._on_single_complete()
                panel.set_running(False)
            finally:
                loop.close()

        thread = threading.Thread(target=run_single_model)
        thread.start()

    def _stop_model(self, index: int):
        if hasattr(self, 'experiment') and self.experiment:
            self._log(f"Stopping model {index + 1}...")
            self.experiment.cancel()
            self.model_panels[index].set_running(False)
            self._log(f"Model {index + 1} stopped")

    def _on_single_complete(self):
        self._set_all_run_buttons_enabled(True)
        self.ui_queue.put({"type": "enable_stop", "enabled": False})

        has_any_results = bool(self.model_responses)
        self.ui_queue.put({"type": "enable_eval", "enabled": has_any_results})
        self.ui_queue.put({"type": "set_statusbar", "message": "Single model completed"})
        self._log("Single model run completed")

    def _run_all(self):
        system_prompt = self.prompts_area.get_system_prompt()
        user_prompt = self.prompts_area.get_user_prompt()

        if not system_prompt and not user_prompt:
            QMessageBox.warning(self, "Warning", "Please enter at least one prompt")
            return

        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            QMessageBox.warning(self, "Warning", "Please set API key in Settings")
            return

        self._create_client()

        self.model_responses = {}
        self.model_stats = {}
        self.model_json = {}

        for panel in self.model_panels:
            panel.clear_response()
            panel.set_running(True)

        self.eval_area.clear_eval_result()
        self.log_widget.clear()
        self._log("Starting experiment...")

        self._set_all_run_buttons_enabled(False)
        self.stop_btn.setEnabled(True)
        self.eval_area.set_evaluate_enabled(False)

        exec_mode = self.settings.get("execution", {}).get("mode", "parallel")
        self._log(f"Execution mode: {exec_mode}")

        thread = threading.Thread(target=self._run_experiment_thread, args=(exec_mode,))
        thread.start()

    def _run_experiment_thread(self, mode: str):
        import asyncio
        import json
        import traceback
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self._log("Starting experiment...")
            system_prompt = self.prompts_area.get_system_prompt()
            user_prompt = self.prompts_area.get_user_prompt()
            model_configs = [panel.get_model_config() for panel in self.model_panels]

            self._log("=" * 60)
            self._log(f"Starting experiment with {len(model_configs)} models")
            self._log(f"System prompt ({len(system_prompt)} chars): {system_prompt[:100]}...")
            self._log(f"User prompt ({len(user_prompt)} chars): {user_prompt[:100]}...")
            self._log(f"Execution mode: {mode}")
            
            for i, config in enumerate(model_configs):
                req_json = {
                    "model": config.name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k if config.top_k > 0 else None,
                }
                self._log(f"--- Model {i+1}: {config.name} REQUEST ---")
                self._log(json.dumps(req_json, indent=2, ensure_ascii=False)[:500])
                self._log("--- END REQUEST ---")

            self._log("Sending requests...")

            def on_model_complete(idx, stat, model_name):
                self.ui_queue.put({
                    "type": "model_complete",
                    "index": idx,
                    "stat": stat,
                    "model_name": model_name,
                    "panel": self.model_panels[idx] if idx < len(self.model_panels) else None,
                    "config": model_configs[idx] if idx < len(model_configs) else None,
                })
            
            if mode == "parallel":
                stats = loop.run_until_complete(
                    self.experiment.run_parallel(
                        system_prompt,
                        user_prompt,
                        model_configs,
                        self._progress_callback,
                        on_model_complete
                    )
                )
            else:
                delay = self.settings.get("execution", {}).get("delay_seconds", 1)
                self._log(f"Delay between requests: {delay}s")
                stats = loop.run_until_complete(
                    self.experiment.run_sequential(
                        system_prompt,
                        user_prompt,
                        model_configs,
                        delay,
                        self._progress_callback,
                        on_model_complete
                    )
                )
            
            self._log(f"Got {len(stats)} results")
            self._log("=" * 60)
            
            for i, stat in enumerate(stats):
                content_len = len(stat.content) if stat.content else 0
                self._log(f"Result {i+1}: model={stat.model_name}, time={stat.response_time:.2f}s, tokens={stat.total_tokens}")
                
                if stat.error:
                    self._log(f"ERROR: {stat.error}")
                else:
                    self._log(f"--- Model {i+1}: {stat.model_name} RESPONSE ---")
                    self._log(f"Response ({content_len} chars): {stat.content[:200]}...")
                    self._log("--- END RESPONSE ---")
                
                if i < len(self.model_panels):
                    panel = self.model_panels[i]
                    config = model_configs[i]
                    
                    if stat.error:
                        error_msg = stat.error
                        self._update_panel_error(panel, stat, error_msg)
                    else:
                        content = stat.content
                        req_json = stat.raw_request
                        res_json = stat.raw_response
                        self._update_panel_success(panel, content, stat, req_json, res_json)

                        self.model_responses[i] = {
                            "model": config.name,
                            "content": content,
                        }
                        self.model_json[i] = {
                            "request": req_json,
                            "response": res_json,
                        }

                    self.model_stats[i] = stat

            self.statistics.add_result(system_prompt, user_prompt, stats)

            total_tokens = sum(s.total_tokens for s in stats if not s.error)
            total_time = sum(s.response_time for s in stats if not s.error)
            self._log(f"Total tokens: {total_tokens}, Total time: {total_time:.2f}s")
            
            self._on_experiment_complete()
        except Exception as e:
            self._log(f"ERROR: {str(e)}")
            import traceback
            self._log(traceback.format_exc())
            self._on_experiment_complete()
        finally:
            loop.close()

    def _update_panel_error(self, panel, stat, error_msg):
        self.ui_queue.put({
            "type": "set_status",
            "panel": panel,
            "status": "error"
        })
        self.ui_queue.put({
            "type": "set_response",
            "panel": panel,
            "content": f"Error: {error_msg}",
            "stats": stat
        })
        self._log(f"[{panel.title}] ERROR: {error_msg}")

    def _update_panel_success(self, panel, content, stat, request_json=None, response_json=None):
        self.ui_queue.put({
            "type": "set_status",
            "panel": panel,
            "status": "success"
        })
        self.ui_queue.put({
            "type": "set_response",
            "panel": panel,
            "content": content,
            "stats": stat,
            "req_json": request_json,
            "res_json": response_json
        })
        self._log(f"[{panel.title}] Response: {len(content)} chars, {stat.total_tokens} tokens in {stat.response_time:.2f}s")

    def _on_experiment_complete(self):
        self._set_all_run_buttons_enabled(True)
        for panel in self.model_panels:
            panel.set_running(False)
        self.ui_queue.put({"type": "enable_stop", "enabled": False})

        has_successful = any(
            self.model_stats.get(i) and not self.model_stats[i].error
            for i in self.model_stats
        )
        self.ui_queue.put({"type": "enable_eval", "enabled": has_successful})
        self.ui_queue.put({"type": "set_statusbar", "message": "Completed"})
        self._log("Experiment completed")

    def _set_all_run_buttons_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        for panel in self.model_panels:
            if not panel._is_running:
                panel.run_btn.setEnabled(enabled)

    def _progress_callback(self, index: int, status: str, model_name: str):
        if index < len(self.model_panels):
            panel = self.model_panels[index]
            self.ui_queue.put({
                "type": "set_status",
                "panel": panel,
                "status": status
            })
        self._log(f"[Model {index+1}] {status}...")

    def _stop(self):
        self._log("Stopping all models...")
        if hasattr(self, 'experiment') and self.experiment:
            self.experiment.cancel()
        for panel in self.model_panels:
            panel.set_running(False)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_bar.showMessage("Stopped")

    def _show_settings(self):
        dialog = SettingsDialog(self)
        dialog.set_settings(self.settings)

        if dialog.exec():
            self.settings = dialog.get_settings()
            self._save_config()
            self._create_client()

            eval_cfg = self.settings.get("eval_model", {})
            self.eval_area.set_eval_model(eval_cfg.get("name", "gpt-4"))
            self.eval_area.eval_temp_spin.setValue(eval_cfg.get("temperature", 0.3))
            self.eval_area.eval_endpoint.setText(eval_cfg.get("custom_endpoint", ""))

    def _run_evaluation(self):
        if not self.model_responses:
            QMessageBox.warning(self, "Warning", "No model responses to evaluate")
            return

        eval_config = self.eval_area.get_eval_config()
        if not eval_config.get("model"):
            QMessageBox.warning(self, "Warning", "Please select an evaluation model")
            return

        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            QMessageBox.warning(self, "Warning", "Please set API key in Settings")
            return

        system_prompt = self.prompts_area.get_system_prompt()
        user_prompt = self.prompts_area.get_user_prompt()

        responses = []
        for i, (idx, resp) in enumerate(self.model_responses.items()):
            stat = self.model_stats.get(idx)
            if stat and stat.error:
                self._log(f"Skipping model {resp['model']} due to error: {stat.error}")
                continue
            resp_with_stats = {
                "model": resp["model"],
                "content": resp["content"],
                "stats": {
                    "response_time": stat.response_time if stat else 0,
                    "prompt_tokens": stat.prompt_tokens if stat else 0,
                    "completion_tokens": stat.completion_tokens if stat else 0,
                    "total_tokens": stat.total_tokens if stat else 0,
                }
            }
            responses.append(resp_with_stats)

        if len(responses) < 1:
            QMessageBox.warning(self, "Warning", "No successful model responses to evaluate")
            return

        self._log(f"Evaluating {len(responses)} model responses...")

        self.eval_area.set_evaluate_enabled(False)
        self._set_all_run_buttons_enabled(False)
        self.status_bar.showMessage("Running evaluation...")
        self._log("Starting evaluation...")

        def run_eval():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                self._log("Sending evaluation request...")
                eval_system_prompt = self.settings.get("eval_model", {}).get("system_prompt", "")
                result, raw = loop.run_until_complete(
                    self.evaluator.evaluate(
                        eval_model=eval_config["model"],
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        responses=responses,
                        temperature=eval_config.get("temperature", 0.3),
                        custom_endpoint=eval_config.get("custom_endpoint", ""),
                        eval_system_prompt=eval_system_prompt,
                    )
                )

                self.statistics.set_eval_result(result, eval_config["model"])

                if raw:
                    self.ui_queue.put({
                        "type": "eval_json",
                        "request": raw.raw_request,
                        "response": raw.raw_response,
                    })

                self.ui_queue.put({"type": "eval_result", "result": result})
                self.ui_queue.put({"type": "set_statusbar", "message": "Evaluation completed"})
                self._log("Evaluation completed")
            except Exception as e:
                import traceback
                self.ui_queue.put({"type": "eval_result", "result": f"Error: {str(e)}"})
                self.ui_queue.put({"type": "set_statusbar", "message": "Evaluation failed"})
                self._log(f"Evaluation error: {str(e)}")
                self._log(traceback.format_exc())
            finally:
                self.ui_queue.put({"type": "enable_eval", "enabled": True})
                self._set_all_run_buttons_enabled(True)
                loop.close()

        thread = threading.Thread(target=run_eval)
        thread.start()

    def closeEvent(self, event):
        self._save_config()
        event.accept()
