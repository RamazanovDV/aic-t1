import json
import os
import threading
import queue

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QProgressBar, QMessageBox, QSplitter,
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
        for panel in self.model_panels:
            panel.dropdown_opened.connect(self._on_dropdown_opened)
            models_layout.addWidget(panel)
        models_widget.setLayout(models_layout)
        splitter.addWidget(models_widget)

        self.prompts_area = PromptsArea()
        splitter.addWidget(self.prompts_area)

        self.eval_area = EvalArea()
        self.eval_area.evaluate_clicked.connect(self._run_evaluation)
        self.eval_area.set_evaluate_enabled(False)
        splitter.addWidget(self.eval_area)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)

        layout.addWidget(splitter)

        control_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run All")
        self.run_btn.clicked.connect(self._run_all)
        control_layout.addWidget(self.run_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        control_layout.addSpacing(20)

        self.refresh_models_btn = QPushButton("Refresh Models")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        control_layout.addWidget(self.refresh_models_btn)

        control_layout.addStretch()

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self._show_settings)
        control_layout.addWidget(self.settings_btn)

        layout.addLayout(control_layout)

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
                elif op_type == "eval_json":
                    self.eval_area.set_eval_json(
                        op.get("request", {}),
                        op.get("response", {})
                    )
            except queue.Empty:
                break

    def _refresh_models(self):
        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            return

        self._create_client()
        self._log("Fetching models from API...")
        
        def fetch_models():
            try:
                models, error = self.client.list_models()
                if error:
                    QTimer.singleShot(0, lambda: self._log(f"Error fetching models: {error}"))
                else:
                    QTimer.singleShot(0, lambda: self._update_model_lists(models))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._log(f"Error: {str(e)}"))

        thread = threading.Thread(target=fetch_models)
        thread.start()

    def _update_model_lists(self, models: list):
        if models:
            for panel in self.model_panels:
                panel.set_model_list(models)
            self._log(f"Loaded {len(models)} models from API")
        else:
            self._log("No models returned from API")

    def _on_dropdown_opened(self):
        api_cfg = self.settings.get("api", {})
        if not api_cfg.get("api_key"):
            return
        self._refresh_models()

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

        self.eval_area.clear_eval_result()
        self.log_widget.clear()
        self._log("Starting experiment...")

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
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
            
            if mode == "parallel":
                stats = loop.run_until_complete(
                    self.experiment.run_parallel(
                        system_prompt,
                        user_prompt,
                        model_configs,
                        self._progress_callback
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
                        self._progress_callback
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
        self.ui_queue.put({"type": "set_progress", "value": 100})
        self.ui_queue.put({"type": "enable_run", "enabled": True})
        self.ui_queue.put({"type": "enable_stop", "enabled": False})
        self.ui_queue.put({"type": "enable_eval", "enabled": True})
        self.ui_queue.put({"type": "set_statusbar", "message": "Completed"})
        self._log("Experiment completed")

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
        self._log("Stopping...")
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

        self.eval_area.set_evaluate_enabled(False)
        self.status_bar.showMessage("Running evaluation...")
        self._log("Starting evaluation...")

        def run_eval():
            try:
                self._log("Sending evaluation request...")
                eval_system_prompt = self.settings.get("eval_model", {}).get("system_prompt", "")
                result, raw = self.evaluator.evaluate(
                    eval_model=eval_config["model"],
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    responses=responses,
                    temperature=eval_config.get("temperature", 0.3),
                    custom_endpoint=eval_config.get("custom_endpoint", ""),
                    eval_system_prompt=eval_system_prompt,
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

        thread = threading.Thread(target=run_eval)
        thread.start()

    def closeEvent(self, event):
        self._save_config()
        event.accept()
