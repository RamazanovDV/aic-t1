import json
import os
import threading
import queue
from functools import partial

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QMessageBox, QSplitter,
    QStatusBar, QTextEdit, QLabel, QToolBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QStyle

from ..api.client import LLMAPIClient
from ..core.experiment import Experiment
from ..core.evaluator import Evaluator
from ..core.statistics import Statistics
from ..config import load_config, save_config, CONFIG_FILE
from .model_panel import ModelPanel
from .prompts_area import PromptsArea
from .eval_area import EvalArea
from .settings_dialog import SettingsDialog
from .experiment_dialog import SaveExperimentDialog, LoadExperimentDialog, NotesEditorDialog


class Worker(QObject):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    result_signal = pyqtSignal(int, dict, dict)
    complete_signal = pyqtSignal()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._base_title = "LLM Experiment Lab"
        self.setWindowTitle(self._base_title)
        self.setMinimumSize(1200, 800)

        self.settings = {}
        self.client = None
        self.experiment = None
        self.evaluator = None
        self.statistics = Statistics()

        self.model_responses = {}
        self.model_stats = {}
        self.model_json = {}

        self.current_experiment_id = None
        self.current_experiment_name = ""
        self.current_notes = ""
        self._is_modified = False

        self.log_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        
        self._load_config()
        self._init_ui()
        self._create_client()
        self._start_log_timer()
        self._start_ui_timer()

    def _load_config(self):
        self.settings = load_config()

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
                    "custom_api_token": config.custom_api_token,
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                    "prompt_modifier": config.prompt_modifier,
                    "stop_sequences": config.stop_sequences,
                    "max_tokens": config.max_tokens,
                    "frequency_penalty": config.frequency_penalty,
                    "presence_penalty": config.presence_penalty,
                })
            self.settings["models"] = model_configs
            
            model_lists = {}
            api_cfg = self.settings.get("api", {})
            base_url = api_cfg.get("base_url", "")
            
            for panel in self.model_panels:
                settings = panel.get_custom_settings()
                endpoint = settings.get("custom_endpoint") or base_url
                if endpoint not in model_lists:
                    model_lists[endpoint] = []
                current_items = [panel.model_combo.itemText(i) for i in range(panel.model_combo.count())]
                if current_items and current_items[0]:
                    model_lists[endpoint] = current_items
            
            if base_url not in model_lists:
                model_lists[base_url] = []
            eval_items = [self.eval_area.eval_model_combo.itemText(i) for i in range(self.eval_area.eval_model_combo.count())]
            if eval_items and eval_items[0]:
                model_lists[base_url] = eval_items
            
            self.settings["model_lists"] = model_lists
            
            self.settings["prompts"] = {
                "system": self.prompts_area.get_system_prompt(),
                "user": self.prompts_area.get_user_prompt(),
            }
            
            self.settings["eval_model"] = {
                "name": self.eval_area.eval_model_combo.currentText(),
            }
            
            self.settings["window"] = {
                "geometry": {
                    "x": self.x(),
                    "y": self.y(),
                    "width": self.width(),
                    "height": self.height(),
                },
                "main_splitter_sizes": self.main_splitter.sizes() if hasattr(self, 'main_splitter') else [],
            }
            
            if self.current_experiment_id:
                self.settings["last_experiment_id"] = self.current_experiment_id
            else:
                self.settings.pop("last_experiment_id", None)
            
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.settings, f, indent=2)
            save_config(self.settings)
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

    def _update_window_title(self):
        if self.current_experiment_name:
            self.setWindowTitle(f"{self._base_title} - {self.current_experiment_name}")
        else:
            self.setWindowTitle(self._base_title)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        style = self.style()

        self.run_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_MediaPlay)),
            "", self
        )
        self.run_btn.setToolTip("Run All")
        self.run_btn.triggered.connect(self._run_all)
        toolbar.addAction(self.run_btn)

        self.stop_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_MediaStop)),
            "", self
        )
        self.stop_btn.setToolTip("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.triggered.connect(self._stop)
        toolbar.addAction(self.stop_btn)

        toolbar.addSeparator()

        self.refresh_models_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_BrowserReload)),
            "", self
        )
        self.refresh_models_btn.setToolTip("Refresh Models")
        self.refresh_models_btn.triggered.connect(self._refresh_all_models)
        toolbar.addAction(self.refresh_models_btn)

        self.settings_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_DesktopIcon)),
            "", self
        )
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.triggered.connect(self._show_settings)
        toolbar.addAction(self.settings_btn)

        toolbar.addSeparator()

        self.save_exp_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_DialogSaveButton)),
            "", self
        )
        self.save_exp_btn.setToolTip("Save Experiment")
        self.save_exp_btn.triggered.connect(self._save_experiment)
        toolbar.addAction(self.save_exp_btn)

        self.save_as_exp_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_DialogSaveButton)),
            "", self
        )
        self.save_as_exp_btn.setToolTip("Save As...")
        self.save_as_exp_btn.triggered.connect(self._save_experiment_as)
        toolbar.addAction(self.save_as_exp_btn)

        self.load_exp_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_DialogOpenButton)),
            "", self
        )
        self.load_exp_btn.setToolTip("Load Experiment")
        self.load_exp_btn.triggered.connect(self._load_experiment)
        toolbar.addAction(self.load_exp_btn)

        self.notes_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_FileIcon)),
            "", self
        )
        self.notes_btn.setToolTip("Edit Notes")
        self.notes_btn.triggered.connect(self._edit_notes)
        toolbar.addAction(self.notes_btn)

        self.clear_exp_btn = QAction(
            QIcon(style.standardIcon(QStyle.SP_DialogDiscardButton)),
            "", self
        )
        self.clear_exp_btn.setToolTip("Clear Experiment")
        self.clear_exp_btn.triggered.connect(self._clear_experiment)
        toolbar.addAction(self.clear_exp_btn)

        toolbar.addSeparator()

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.prompts_area = PromptsArea()
        splitter.addWidget(self.prompts_area)

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

        self.eval_area = EvalArea()
        self.eval_area.evaluate_clicked.connect(self._run_evaluation)
        self.eval_area.stop_evaluate_clicked.connect(self._stop_evaluation)
        self.eval_area.set_evaluate_enabled(False)
        splitter.addWidget(self.eval_area)

        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setPlaceholderText("Log output...")
        self.log_widget.setMinimumHeight(0)
        splitter.addWidget(self.log_widget)

        splitter.setSizes([150, 300, 50, 200, 0])

        layout.addWidget(splitter)
        
        self.main_splitter = splitter

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self._load_saved_models()
        self._restore_window_state()
        self._load_last_experiment()
        
        self.prompts_area.changed.connect(self._on_experiment_changed)

    def _on_experiment_changed(self):
        if self.current_experiment_id:
            self._is_modified = True

    def _load_last_experiment(self):
        last_exp_id = self.settings.get("last_experiment_id")
        if last_exp_id:
            from ..core.experiment_storage import get_experiment_by_id
            exp_data = get_experiment_by_id(last_exp_id)
            if exp_data:
                self.prompts_area.set_system_prompt(exp_data.prompts.get("system", ""))
                self.prompts_area.set_user_prompt(exp_data.prompts.get("user", ""))
                
                api_cfg = self.settings.get("api", {})
                base_url = api_cfg.get("base_url", "")
                model_lists = self.settings.get("model_lists", {})
                
                saved_models = exp_data.models
                for i, panel in enumerate(self.model_panels):
                    settings = panel.get_custom_settings()
                    endpoint = settings.get("custom_endpoint") or base_url
                    if endpoint in model_lists and model_lists[endpoint]:
                        panel.set_model_list(model_lists[endpoint])
                    
                    if i < len(saved_models):
                        model_data = saved_models[i]
                        panel.set_model(model_data.get("name", ""))
                        panel.temp_spin.setValue(model_data.get("temperature", 0.7))
                        panel.top_p_spin.setValue(model_data.get("top_p", 1.0))
                        panel.top_k_spin.setValue(model_data.get("top_k", -1))
                        panel.set_prompt_modifier(model_data.get("prompt_modifier", ""))
                        panel.set_custom_settings({
                            "custom_endpoint": model_data.get("custom_endpoint", ""),
                            "custom_api_token": model_data.get("custom_api_token", ""),
                            "max_tokens": model_data.get("max_tokens", 0),
                            "stop_sequences": model_data.get("stop_sequences", []),
                            "frequency_penalty": model_data.get("frequency_penalty", 0.0),
                            "presence_penalty": model_data.get("presence_penalty", 0.0),
                        })
                
                self.settings["execution"] = exp_data.execution
                self.settings["eval_model"] = exp_data.eval_model
                
                self.model_responses = exp_data.model_responses or {}
                self.model_stats = exp_data.model_stats or {}
                
                self.model_json = exp_data.results.get("model_json", {}) if exp_data.results else {}
                
                for i, panel in enumerate(self.model_panels):
                    panel.clear_response()
                    if i in self.model_responses:
                        response_data = self.model_responses[i]
                        if isinstance(response_data, dict):
                            content = response_data.get("content", "")
                        else:
                            content = response_data
                        stats = self.model_stats.get(i)
                        panel.set_response(content, stats)

                        if stats and hasattr(stats, 'raw_request') and hasattr(stats, 'raw_response'):
                            req_json = stats.raw_request
                            res_json = stats.raw_response
                            if req_json or res_json:
                                panel.set_json(req_json, res_json, content if isinstance(content, str) else "")
                        elif i in self.model_json:
                            req_json = self.model_json[i].get("request", {})
                            res_json = self.model_json[i].get("response", {})
                            panel.set_json(req_json, res_json, content if isinstance(content, str) else "")
                
                self.current_experiment_id = exp_data.id
                self.current_experiment_name = exp_data.name
                self.current_notes = exp_data.notes or ""
                self._is_modified = False
                self._update_window_title()
                
                if exp_data.eval_result:
                    self.eval_area.set_eval_result(exp_data.eval_result)
                
                if self.model_responses:
                    self.eval_area.set_evaluate_enabled(True)
                
                self._log(f"Last experiment loaded: {exp_data.name}")
                self.status_bar.showMessage(f"Last experiment loaded: {exp_data.name}")

    def _load_saved_models(self):
        saved_models = self.settings.get("models", [])
        for i, panel in enumerate(self.model_panels):
            if i < len(saved_models):
                model_data = saved_models[i]
                panel.set_model(model_data.get("name", ""))
                panel.temp_spin.setValue(model_data.get("temperature", 0.7))
                panel.top_p_spin.setValue(model_data.get("top_p", 1.0))
                panel.top_k_spin.setValue(model_data.get("top_k", -1))
                panel.set_prompt_modifier(model_data.get("prompt_modifier", ""))
                panel.set_custom_settings({
                    "custom_endpoint": model_data.get("custom_endpoint", ""),
                    "custom_api_token": model_data.get("custom_api_token", ""),
                    "max_tokens": model_data.get("max_tokens", 0),
                    "stop_sequences": model_data.get("stop_sequences", []),
                    "frequency_penalty": model_data.get("frequency_penalty", 0.0),
                    "presence_penalty": model_data.get("presence_penalty", 0.0),
                })

        api_cfg = self.settings.get("api", {})
        base_url = api_cfg.get("base_url", "")
        model_lists = self.settings.get("model_lists", {})
        
        for panel in self.model_panels:
            settings = panel.get_custom_settings()
            endpoint = settings.get("custom_endpoint") or base_url
            if endpoint in model_lists and model_lists[endpoint]:
                panel.set_model_list(model_lists[endpoint])
        
        if base_url in model_lists and model_lists[base_url]:
            current = self.eval_area.eval_model_combo.currentText()
            self.eval_area.eval_model_combo.clear()
            sorted_eval_models = sorted(model_lists[base_url])
            self.eval_area.eval_model_combo.addItems(sorted_eval_models)
            if current in sorted_eval_models:
                self.eval_area.eval_model_combo.setCurrentText(current)

        saved_prompts = self.settings.get("prompts", {})
        if saved_prompts:
            self.prompts_area.set_system_prompt(saved_prompts.get("system", ""))
            self.prompts_area.set_user_prompt(saved_prompts.get("user", ""))

        saved_eval = self.settings.get("eval_model", {})
        if saved_eval:
            self.eval_area.set_eval_model(saved_eval.get("name", "gpt-4"))
            self.eval_area.eval_temp_spin.setValue(saved_eval.get("temperature", 0.3))

    def _restore_window_state(self):
        window_settings = self.settings.get("window", {})
        geometry = window_settings.get("geometry", {})
        
        if geometry:
            x = geometry.get("x", 100)
            y = geometry.get("y", 100)
            width = geometry.get("width", 1200)
            height = geometry.get("height", 800)
            self.setGeometry(x, y, width, height)
        
        if hasattr(self, 'main_splitter'):
            main_sizes = window_settings.get("main_splitter_sizes", [])
            if main_sizes:
                self.main_splitter.setSizes(main_sizes)

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
                    panel.finalize_response()
                    if op.get("req_json") and op.get("res_json"):
                        panel.set_json(op.get("req_json"), op.get("res_json"), content if content else "")
                elif op_type == "stream_chunk":
                    panel = op.get("panel")
                    content = op.get("content")
                    reasoning = op.get("reasoning", "")
                    panel.append_response(content)
                    if reasoning:
                        panel.append_reasoning(reasoning)
                elif op_type == "init_response":
                    panel = op.get("panel")
                    panel.init_response()
                elif op_type == "enable_run":
                    self.run_btn.setEnabled(op.get("enabled", True))
                elif op_type == "enable_stop":
                    self.stop_btn.setEnabled(op.get("enabled", False))
                elif op_type == "enable_eval":
                    self.eval_area.set_evaluate_enabled(op.get("enabled", True))
                elif op_type == "set_statusbar":
                    self.status_bar.showMessage(op.get("message"))
                elif op_type == "eval_stream_chunk":
                    content = op.get("content", "")
                    reasoning = op.get("reasoning", "")
                    self.eval_area.append_eval_result(content)
                    if reasoning:
                        self.eval_area.append_eval_reasoning(reasoning)
                elif op_type == "eval_result":
                    self.eval_area.set_eval_result(
                        op.get("result", ""),
                        op.get("reasoning")
                    )
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
                    
                    if not stat.error:
                        self.eval_area.set_evaluate_enabled(True)
                    
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
            settings = panel.get_custom_settings()
            endpoint = settings.get("custom_endpoint")
            if endpoint:
                endpoints.add(endpoint)

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
                with httpx.Client(verify=api_cfg.get("verify_ssl", True), follow_redirects=True) as client:
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
            settings = panel.get_custom_settings()
            panel_endpoint = settings.get("custom_endpoint", "")
            should_update = (
                (endpoint and panel_endpoint == endpoint) or
                (is_default_endpoint and not panel_endpoint)
            )
            if should_update:
                panel.set_model_list(models)
                updated = True
        
        should_update_eval = is_default_endpoint
        if should_update_eval:
            current = self.eval_area.eval_model_combo.currentText()
            self.eval_area.eval_model_combo.clear()
            sorted_models = sorted(models)
            self.eval_area.eval_model_combo.addItems(sorted_models)
            if current in sorted_models:
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

        self._set_all_run_buttons_enabled(False, disable_panels=False)
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
                        self._progress_callback,
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

        exec_mode = self.settings.get("execution", {}).get("mode", "parallel")
        self._log(f"Execution mode: {exec_mode}")

        disable_panels = (exec_mode == "sequential")
        self._set_all_run_buttons_enabled(False, disable_panels=disable_panels)
        self.stop_btn.setEnabled(True)
        self.eval_area.set_evaluate_enabled(False)

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
                endpoint = config.custom_endpoint if config.custom_endpoint else "default"
                token_info = "default" if not config.custom_api_token else "custom (set)"
                self._log(f"--- Model {i+1}: {config.name} ---")
                self._log(f"    Endpoint: {endpoint}")
                self._log(f"    API Token: {token_info}")
                
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
                if config.stop_sequences:
                    req_json["stop"] = config.stop_sequences
                if config.max_tokens > 0:
                    req_json["max_tokens"] = config.max_tokens
                if config.frequency_penalty != 0.0:
                    req_json["frequency_penalty"] = config.frequency_penalty
                if config.presence_penalty != 0.0:
                    req_json["presence_penalty"] = config.presence_penalty
                
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

    def _set_all_run_buttons_enabled(self, enabled: bool, disable_panels: bool = True):
        self.run_btn.setEnabled(enabled)
        if disable_panels:
            for panel in self.model_panels:
                if not panel._is_running:
                    panel.run_btn.setEnabled(enabled)

    def _progress_callback(self, index: int, status: str, model_name: str, content: str = "", reasoning: str = ""):
        if index < len(self.model_panels):
            panel = self.model_panels[index]
            if status == "running":
                self.ui_queue.put({
                    "type": "init_response",
                    "panel": panel,
                })
                self.ui_queue.put({
                    "type": "set_status",
                    "panel": panel,
                    "status": status
                })
            elif status == "streaming" and (content or reasoning):
                self.ui_queue.put({
                    "type": "stream_chunk",
                    "panel": panel,
                    "content": content,
                    "reasoning": reasoning,
                })
            else:
                self.ui_queue.put({
                    "type": "set_status",
                    "panel": panel,
                    "status": status
                })
        if status != "streaming":
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

        self.eval_area.clear_eval_result()
        self.eval_area.set_running(True)
        self._set_all_run_buttons_enabled(False)
        self.status_bar.showMessage("Running evaluation...")
        self._log("Starting evaluation...")

        def run_eval():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                self.eval_area.set_running(True)
                self._log("Sending evaluation request...")
                eval_system_prompt = self.settings.get("eval_model", {}).get("system_prompt", "")

                accumulated_content = []

                def on_chunk(content: str, reasoning: str):
                    accumulated_content.append(content)
                    self.ui_queue.put({
                        "type": "eval_stream_chunk",
                        "content": content,
                        "reasoning": reasoning,
                    })

                result, raw = loop.run_until_complete(
                    self.evaluator.evaluate_stream(
                        eval_model=eval_config["model"],
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        responses=responses,
                        temperature=eval_config.get("temperature", 0.3),
                        eval_system_prompt=eval_system_prompt,
                        on_chunk=on_chunk,
                    )
                )

                self.statistics.set_eval_result(result, eval_config["model"])

                if raw:
                    self.ui_queue.put({
                        "type": "eval_json",
                        "request": raw.raw_request,
                        "response": raw.raw_response,
                    })
                    reasoning = getattr(raw, 'reasoning', None)
                else:
                    reasoning = None

                self.ui_queue.put({
                    "type": "eval_result",
                    "result": result,
                    "reasoning": reasoning
                })
                self.ui_queue.put({"type": "set_statusbar", "message": "Evaluation completed"})
                self._log("Evaluation completed")
            except Exception as e:
                import traceback
                self.ui_queue.put({
                    "type": "eval_result",
                    "result": f"Error: {str(e)}",
                    "reasoning": None
                })
                self.ui_queue.put({"type": "set_statusbar", "message": "Evaluation failed"})
                self._log(f"Evaluation error: {str(e)}")
                self._log(traceback.format_exc())
            finally:
                self.eval_area.set_running(False)
                if self.model_responses:
                    self.eval_area.set_evaluate_enabled(True)
                self._set_all_run_buttons_enabled(True)
                loop.close()

        thread = threading.Thread(target=run_eval)
        thread.start()

    def _stop_evaluation(self):
        self._log("Stopping evaluation...")
        self.evaluator.cancel()
        self.eval_area.set_running(False)

    def _save_experiment(self):
        if self.current_experiment_id and not self._is_modified:
            return
        
        if self.current_experiment_id:
            self._do_save_experiment(self.current_experiment_name)
        else:
            self._show_save_dialog()

    def _save_experiment_as(self):
        self._show_save_dialog()

    def _show_save_dialog(self):
        from ..core.experiment_storage import save_experiment
        
        dialog = SaveExperimentDialog(self, self.current_experiment_name)
        if dialog.exec():
            name = dialog.get_name()
            self._do_save_experiment(name, force_new=True)

    def _do_save_experiment(self, name: str, force_new: bool = False):
        from ..core.experiment_storage import save_experiment
        
        prompts = {
            "system": self.prompts_area.get_system_prompt(),
            "user": self.prompts_area.get_user_prompt(),
        }
        
        model_configs = []
        for panel in self.model_panels:
            config = panel.get_model_config()
            model_configs.append({
                "name": config.name,
                "custom_endpoint": config.custom_endpoint,
                "custom_api_token": config.custom_api_token,
                "temperature": config.temperature,
                "top_p": config.top_p,
                "top_k": config.top_k,
                "prompt_modifier": config.prompt_modifier,
                "stop_sequences": config.stop_sequences,
                "max_tokens": config.max_tokens,
                "frequency_penalty": config.frequency_penalty,
                "presence_penalty": config.presence_penalty,
            })
        
        execution = self.settings.get("execution", {})
        eval_model_cfg = self.settings.get("eval_model", {})
        
        results = {
            "model_responses": self.model_responses,
            "model_stats_keys": list(self.model_stats.keys()),
        }
        
        existing_id = "" if force_new else self.current_experiment_id
        existing_timestamp = ""
        
        exp_id = save_experiment(
            name=name,
            prompts=prompts,
            models=model_configs,
            execution=execution,
            eval_model=eval_model_cfg,
            results=results,
            model_responses=self.model_responses,
            model_stats=self.model_stats,
            eval_result=self.eval_area.get_eval_result(),
            notes=self.current_notes,
            existing_id=existing_id,
            existing_timestamp=existing_timestamp,
        )
        
        self.current_experiment_id = exp_id
        self.current_experiment_name = name
        self._is_modified = False
        self._update_window_title()
        self._log(f"Experiment saved: {name}")
        self.status_bar.showMessage(f"Experiment saved: {name}")

    def _load_experiment(self):
        if self.current_experiment_id and self._is_modified:
            reply = QMessageBox.question(
                self,
                "Save Changes",
                "You have unsaved changes. Save before loading another experiment?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_experiment()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        
        dialog = LoadExperimentDialog(self)
        if dialog.exec():
            exp_data = dialog.get_selected_data()
            if exp_data:
                self.prompts_area.set_system_prompt(exp_data.prompts.get("system", ""))
                self.prompts_area.set_user_prompt(exp_data.prompts.get("user", ""))
                
                api_cfg = self.settings.get("api", {})
                base_url = api_cfg.get("base_url", "")
                model_lists = self.settings.get("model_lists", {})
                
                saved_models = exp_data.models
                for i, panel in enumerate(self.model_panels):
                    settings = panel.get_custom_settings()
                    endpoint = settings.get("custom_endpoint") or base_url
                    if endpoint in model_lists and model_lists[endpoint]:
                        panel.set_model_list(model_lists[endpoint])
                    
                    if i < len(saved_models):
                        model_data = saved_models[i]
                        panel.set_model(model_data.get("name", ""))
                        panel.temp_spin.setValue(model_data.get("temperature", 0.7))
                        panel.top_p_spin.setValue(model_data.get("top_p", 1.0))
                        panel.top_k_spin.setValue(model_data.get("top_k", -1))
                        panel.set_prompt_modifier(model_data.get("prompt_modifier", ""))
                        panel.set_custom_settings({
                            "custom_endpoint": model_data.get("custom_endpoint", ""),
                            "custom_api_token": model_data.get("custom_api_token", ""),
                            "max_tokens": model_data.get("max_tokens", 0),
                            "stop_sequences": model_data.get("stop_sequences", []),
                            "frequency_penalty": model_data.get("frequency_penalty", 0.0),
                            "presence_penalty": model_data.get("presence_penalty", 0.0),
                        })
                
                self.settings["execution"] = exp_data.execution
                self.settings["eval_model"] = exp_data.eval_model
                
                self.model_responses = exp_data.model_responses or {}
                self.model_stats = exp_data.model_stats or {}
                
                self.current_experiment_id = exp_data.id
                self.current_experiment_name = exp_data.name
                self.current_notes = exp_data.notes or ""
                self._is_modified = False
                self._update_window_title()
                
                self.model_json = exp_data.results.get("model_json", {}) if exp_data.results else {}
                
                for i, panel in enumerate(self.model_panels):
                    panel.clear_response()
                    if i in self.model_responses:
                        response_data = self.model_responses[i]
                        if isinstance(response_data, dict):
                            content = response_data.get("content", "")
                        else:
                            content = response_data
                        stats = self.model_stats.get(i)
                        panel.set_response(content, stats)

                        if stats and hasattr(stats, 'raw_request') and hasattr(stats, 'raw_response'):
                            req_json = stats.raw_request
                            res_json = stats.raw_response
                            if req_json or res_json:
                                panel.set_json(req_json, res_json, content if isinstance(content, str) else "")
                        elif i in self.model_json:
                            req_json = self.model_json[i].get("request", {})
                            res_json = self.model_json[i].get("response", {})
                            panel.set_json(req_json, res_json, content if isinstance(content, str) else "")
                
                self.eval_area.clear_eval_result()
                
                if exp_data.eval_result:
                    self.eval_area.set_eval_result(exp_data.eval_result)
                
                if self.model_responses:
                    self.eval_area.set_evaluate_enabled(True)
                
                self._log(f"Experiment loaded: {exp_data.name}")
                self.status_bar.showMessage(f"Experiment loaded: {exp_data.name}")

    def _edit_notes(self):
        if not self.current_experiment_id:
            reply = QMessageBox.question(
                self,
                "No Experiment",
                "No experiment loaded. Create a new experiment first?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._save_experiment()
            if not self.current_experiment_id:
                return
        
        dialog = NotesEditorDialog(self, self.current_notes, self.current_experiment_id)
        if dialog.exec():
            self.current_notes = dialog.get_notes()
            if self.current_experiment_id:
                from ..core.experiment_storage import update_notes
                update_notes(self.current_experiment_id, self.current_notes)
                self._log("Notes updated")
                self.status_bar.showMessage("Notes updated")

    def _clear_experiment(self):
        if self.current_experiment_id:
            reply = QMessageBox.question(
                self,
                "Clear Experiment",
                "This will clear all current experiment data. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.prompts_area.clear()
        
        for panel in self.model_panels:
            panel.clear_response()
            panel.set_model("")
            panel.temp_spin.setValue(0.7)
            panel.top_p_spin.setValue(1.0)
            panel.top_k_spin.setValue(-1)
            panel.set_prompt_modifier("")
            panel.set_custom_settings({
                "custom_endpoint": "",
                "custom_api_token": "",
                "max_tokens": 0,
                "stop_sequences": [],
                "frequency_penalty": 0.0,
                "presence_penalty": 0.0,
            })
        
        self.eval_area.clear_eval_result()
        
        self.model_responses = {}
        self.model_stats = {}
        self.model_json = {}
        
        self.current_experiment_id = None
        self.current_experiment_name = ""
        self.current_notes = ""
        
        self._update_window_title()
        self._log("Experiment cleared - starting new experiment")
        self.status_bar.showMessage("New experiment started")

    def closeEvent(self, event):
        if self.current_experiment_id and self._is_modified:
            reply = QMessageBox.question(
                self,
                "Save Experiment",
                "There is an active experiment. Save it before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_experiment()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
                return
        
        self._save_config()
        event.accept()
