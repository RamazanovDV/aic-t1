import json
import re

import mistune

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit,
    QGroupBox, QLineEdit, QFrame, QPushButton,
    QDialog, QDialogButtonBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QColor, QPalette


COLORS = {
    "idle": "#6c757d",
    "running": "#ffc107",
    "success": "#28a745",
    "error": "#dc3545",
}


class StatusIndicator(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.set_status("idle")

    def set_status(self, status: str):
        color = COLORS.get(status, COLORS["idle"])
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 6px;
                border: 1px solid #444;
            }}
        """)


class ModelPanel(QWidget):
    config_changed = pyqtSignal()
    dropdown_opened = pyqtSignal()
    run_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()

    DEFAULT_MODELS = []

    def __init__(self, title: str = "Model", parent=None):
        super().__init__(parent)
        self.title = title
        self._md = mistune.create_markdown(plugins=['table', 'strikethrough', 'url'])
        self._html_style = """
        <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 13px;
            line-height: 1.0;
            color: #e0e0e0;
            background-color: #2b2b2b;
            padding: 10px;
        }
        pre {
            background-color: #1e1e1e;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 10px;
            overflow-x: auto;
        }
        code {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 12px;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #ffffff;
            border-bottom: 1px solid #444;
            padding-bottom: 5px;
        }
        blockquote {
            border-left: 4px solid #666;
            margin-left: 0;
            padding-left: 15px;
            color: #aaa;
        }
        a { color: #6cb6ff; }
        table { border-collapse: collapse; }
        th, td { border: 1px solid #444; padding: 8px; }
        </style>
        """
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        group = QGroupBox(self.title)
        group_layout = QVBoxLayout()

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.DEFAULT_MODELS)
        self.model_combo.setEditable(True)
        self.model_combo.setToolTip("Выберите модель для тестирования")
        self.model_combo.currentTextChanged.connect(self.config_changed.emit)
        top_row.addWidget(self.model_combo)

        self.status_indicator = StatusIndicator()
        top_row.addWidget(self.status_indicator)

        self.run_btn = QPushButton("Run")
        self.run_btn.setFixedWidth(60)
        self.run_btn.setToolTip("Запустить эту модель")
        self.run_btn.clicked.connect(self._on_run_btn_clicked)
        self._is_running = False
        top_row.addWidget(self.run_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedWidth(30)
        self.settings_btn.setToolTip("Model settings")
        self.settings_btn.clicked.connect(self._on_settings_btn_clicked)
        top_row.addWidget(self.settings_btn)

        top_row.addStretch()
        group_layout.addLayout(top_row)

        params_group = QGroupBox("Parameters")
        params_layout = QHBoxLayout()

        temp_layout = QVBoxLayout()
        temp_label = QLabel("Temperature")
        temp_label.setToolTip("Температура: выше = более случайные ответы, ниже = более детерминированные (0.0-2.0)")
        temp_layout.addWidget(temp_label)
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)
        self.temp_spin.setToolTip("Температура: выше = более случайные ответы, ниже = более детерминированные (0.0-2.0)")
        self.temp_spin.valueChanged.connect(self.config_changed.emit)
        temp_layout.addWidget(self.temp_spin)
        params_layout.addLayout(temp_layout)

        top_p_layout = QVBoxLayout()
        top_p_label = QLabel("Top P")
        top_p_label.setToolTip("Top P: учитывает только токены с суммарной вероятностью <= P (0.0-1.0)")
        top_p_layout.addWidget(top_p_label)
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setValue(1.0)
        self.top_p_spin.setToolTip("Top P: учитывает только токены с суммарной вероятностью <= P (0.0-1.0)")
        self.top_p_spin.valueChanged.connect(self.config_changed.emit)
        top_p_layout.addWidget(self.top_p_spin)
        params_layout.addLayout(top_p_layout)

        top_k_layout = QVBoxLayout()
        top_k_label = QLabel("Top K")
        top_k_label.setToolTip("Top K: учитывает только K наиболее вероятных токенов (-1 = отключено)")
        top_k_layout.addWidget(top_k_label)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(-1, 100)
        self.top_k_spin.setValue(-1)
        self.top_k_spin.setSpecialValueText("None")
        self.top_k_spin.setToolTip("Top K: учитывает только K наиболее вероятных токенов (-1 = отключено)")
        self.top_k_spin.valueChanged.connect(self.config_changed.emit)
        top_k_layout.addWidget(self.top_k_spin)
        params_layout.addLayout(top_k_layout)

        params_group.setLayout(params_layout)
        group_layout.addWidget(params_group)

        modifier_label = QLabel("Prompt modifier (appended to user prompt):")
        modifier_label.setToolTip("Additional context/instructions for this specific model only")
        group_layout.addWidget(modifier_label)

        self.prompt_modifier_edit = QTextEdit()
        self.prompt_modifier_edit.setPlaceholderText("Additional context/instructions for this specific model...")
        self.prompt_modifier_edit.setFixedHeight(60)
        self.prompt_modifier_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.prompt_modifier_edit.textChanged.connect(self.config_changed.emit)
        group_layout.addWidget(self.prompt_modifier_edit)

        stats_row = QHBoxLayout()
        self.time_label = QLabel("Time: --")
        self.tokens_label = QLabel("Tokens: --")
        self.json_btn = QPushButton("Show JSON")
        self.json_btn.setEnabled(False)
        self.json_btn.clicked.connect(self._show_json_dialog)
        stats_row.addWidget(self.time_label)
        stats_row.addWidget(self.tokens_label)
        stats_row.addWidget(self.json_btn)
        stats_row.addStretch()
        group_layout.addLayout(stats_row)

        self.response_edit = QTextEdit()
        self.response_edit.setPlaceholderText("Response will appear here...")
        self.response_edit.setReadOnly(True)
        self.response_edit.setMinimumHeight(150)
        group_layout.addWidget(self.response_edit)

        self.reasoning_toggle = QPushButton("▼ Reasoning")
        self.reasoning_toggle.setCheckable(True)
        self.reasoning_toggle.setChecked(False)
        self.reasoning_toggle.clicked.connect(self._toggle_reasoning)
        self.reasoning_toggle.setVisible(False)
        group_layout.addWidget(self.reasoning_toggle)

        self.reasoning_edit = QTextEdit()
        self.reasoning_edit.setPlaceholderText("Model reasoning/thinking will appear here...")
        self.reasoning_edit.setReadOnly(True)
        self.reasoning_edit.setMaximumHeight(0)
        self.reasoning_edit.setVisible(False)
        group_layout.addWidget(self.reasoning_edit)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def _on_run_btn_clicked(self):
        if self._is_running:
            self.stop_clicked.emit()
        else:
            self.run_clicked.emit()

    def set_running(self, running: bool):
        self._is_running = running
        if running:
            self.run_btn.setText("Stop")
            self.run_btn.setToolTip("Остановить выполнение")
        else:
            self.run_btn.setText("Run")
            self.run_btn.setToolTip("Запустить эту модель")

    def _on_settings_btn_clicked(self):
        from .model_settings_dialog import ModelSettingsDialog
        dialog = ModelSettingsDialog(self)
        dialog.set_settings({
            "custom_endpoint": getattr(self, "_custom_endpoint", ""),
            "custom_api_token": getattr(self, "_custom_api_token", ""),
            "max_tokens": getattr(self, "_max_tokens", 0),
            "stop_sequences": getattr(self, "_stop_sequences", []),
            "frequency_penalty": getattr(self, "_frequency_penalty", 0.0),
            "presence_penalty": getattr(self, "_presence_penalty", 0.0),
        })
        if dialog.exec():
            settings = dialog.get_settings()
            self._custom_endpoint = settings["custom_endpoint"]
            self._custom_api_token = settings["custom_api_token"]
            self._max_tokens = settings["max_tokens"]
            self._stop_sequences = settings["stop_sequences"]
            self._frequency_penalty = settings["frequency_penalty"]
            self._presence_penalty = settings["presence_penalty"]
            self.config_changed.emit()

    def get_model_config(self):
        from ..core.experiment import ModelConfig
        return ModelConfig(
            name=self.model_combo.currentText(),
            custom_endpoint=getattr(self, "_custom_endpoint", ""),
            custom_api_token=getattr(self, "_custom_api_token", ""),
            temperature=self.temp_spin.value(),
            top_p=self.top_p_spin.value(),
            top_k=self.top_k_spin.value(),
            prompt_modifier=self.prompt_modifier_edit.toPlainText(),
            stop_sequences=getattr(self, "_stop_sequences", []),
            max_tokens=getattr(self, "_max_tokens", 0),
            frequency_penalty=getattr(self, "_frequency_penalty", 0.0),
            presence_penalty=getattr(self, "_presence_penalty", 0.0),
        )

    def get_prompt_modifier(self) -> str:
        return self.prompt_modifier_edit.toPlainText().strip()

    def set_prompt_modifier(self, text: str):
        self.prompt_modifier_edit.setPlainText(text)

    def get_custom_settings(self) -> dict:
        return {
            "custom_endpoint": getattr(self, "_custom_endpoint", ""),
            "custom_api_token": getattr(self, "_custom_api_token", ""),
            "max_tokens": getattr(self, "_max_tokens", 0),
            "stop_sequences": getattr(self, "_stop_sequences", []),
            "frequency_penalty": getattr(self, "_frequency_penalty", 0.0),
            "presence_penalty": getattr(self, "_presence_penalty", 0.0),
        }

    def set_custom_settings(self, settings: dict):
        self._custom_endpoint = settings.get("custom_endpoint", "")
        self._custom_api_token = settings.get("custom_api_token", "")
        self._max_tokens = settings.get("max_tokens", 0)
        self._stop_sequences = settings.get("stop_sequences", [])
        self._frequency_penalty = settings.get("frequency_penalty", 0.0)
        self._presence_penalty = settings.get("presence_penalty", 0.0)

    def _toggle_reasoning(self):
        is_expanded = self.reasoning_toggle.isChecked()
        if is_expanded:
            self.reasoning_toggle.setText("▲ Reasoning")
            self.reasoning_edit.setMaximumHeight(200)
            self.reasoning_edit.setVisible(True)
        else:
            self.reasoning_toggle.setText("▼ Reasoning")
            self.reasoning_edit.setMaximumHeight(0)
            self.reasoning_edit.setVisible(False)

    def expand_reasoning(self):
        if self.reasoning_toggle.isVisible():
            self.reasoning_toggle.setChecked(True)
            self._toggle_reasoning()

    def _render_markdown(self, text: str) -> str:
        if not text:
            return ""
        
        html = self._md(text)
        
        return f"{html}"

    def set_response(self, content: str, stats=None):
        html = self._render_markdown(content)
        full_html = f"<html><head>{self._html_style}</head><body>{html}</body></html>"
        self.response_edit.setHtml(full_html)
        if stats:
            self.time_label.setText(f"Time: {stats.response_time:.2f}s")
            self.tokens_label.setText(
                f"Tokens: {stats.prompt_tokens} + {stats.completion_tokens} = {stats.total_tokens}"
            )
            if hasattr(stats, 'reasoning') and stats.reasoning:
                self.reasoning_edit.setPlainText(stats.reasoning)
                self.reasoning_toggle.setVisible(True)
            else:
                self.reasoning_toggle.setVisible(False)
                self.reasoning_edit.setVisible(False)
                self.reasoning_toggle.setChecked(False)
                self.reasoning_edit.setMaximumHeight(0)

    def init_response(self):
        self._accumulated_content = ""
        empty_html = f"<html><head>{self._html_style}</head><body></body></html>"
        self.response_edit.setHtml(empty_html)

    def append_response(self, new_content: str):
        self._accumulated_content += new_content
        cursor = self.response_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(new_content)
        self.response_edit.setTextCursor(cursor)

    def finalize_response(self):
        html = self._render_markdown(self._accumulated_content)
        full_html = f"<html><head>{self._html_style}</head><body>{html}</body></html>"
        self.response_edit.setHtml(full_html)

    def append_reasoning(self, new_reasoning: str):
        self.reasoning_toggle.setVisible(True)
        self.reasoning_edit.setVisible(True)
        cursor = self.reasoning_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(new_reasoning)
        self.reasoning_edit.setTextCursor(cursor)

    def set_json(self, request_json: dict, response_json: dict):
        self.request_json = request_json
        self.response_json = response_json
        self.json_btn.setEnabled(True)

    def _show_json_dialog(self):
        if not hasattr(self, 'request_json') or not hasattr(self, 'response_json'):
            return
        
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{self.title} - JSON")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        
        request_edit = QTextEdit()
        import json
        request_edit.setPlainText(json.dumps(self.request_json, indent=2, ensure_ascii=False))
        request_edit.setReadOnly(True)
        layout.addWidget(request_edit)
        
        response_edit = QTextEdit()
        response_text = json.dumps(self.response_json, indent=2, ensure_ascii=False)
        if self.response_json.get("streaming") == True:
            response_text = "(Streaming response - full response not available)"
        response_edit.setPlainText(response_text)
        response_edit.setReadOnly(True)
        layout.addWidget(response_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.exec()

    def set_status(self, status: str):
        self.status_indicator.set_status(status)

    def clear_response(self):
        self.response_edit.setHtml("")
        self.reasoning_edit.clear()
        self.reasoning_toggle.setVisible(False)
        self.reasoning_edit.setVisible(False)
        self.reasoning_toggle.setChecked(False)
        self.reasoning_edit.setMaximumHeight(0)
        self.time_label.setText("Time: --")
        self.tokens_label.setText("Tokens: --")
        self.status_indicator.set_status("idle")
        self.json_btn.setEnabled(False)
        if hasattr(self, 'request_json'):
            del self.request_json
        if hasattr(self, 'response_json'):
            del self.response_json

    def set_model(self, model_name: str):
        idx = self.model_combo.findText(model_name)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentText(model_name)

    def set_model_list(self, models: list):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        sorted_models = sorted(models)
        self.model_combo.addItems(sorted_models)
        if current in sorted_models:
            self.model_combo.setCurrentText(current)

    def get_raw_json(self) -> dict:
        return {
            "request": {},
            "response": {},
        }

    def set_run_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
