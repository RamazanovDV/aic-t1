import json
import re

import mistune

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QDoubleSpinBox, QTextEdit,
    QGroupBox, QPushButton,
)
from typing import Optional
from PyQt6.QtCore import pyqtSignal


class EvalArea(QWidget):
    evaluate_clicked = pyqtSignal()

    DEFAULT_EVAL_MODELS = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.eval_request_json = None
        self.eval_response_json = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        group = QGroupBox("Expert Evaluation")
        group_layout = QVBoxLayout()

        settings_layout = QHBoxLayout()

        eval_model_label = QLabel("Eval Model:")
        self.eval_model_combo = QComboBox()
        self.eval_model_combo.addItems(self.DEFAULT_EVAL_MODELS)
        self.eval_model_combo.setEditable(True)
        settings_layout.addWidget(eval_model_label)
        settings_layout.addWidget(self.eval_model_combo)

        temp_label = QLabel("Temperature:")
        self.eval_temp_spin = QDoubleSpinBox()
        self.eval_temp_spin.setRange(0.0, 2.0)
        self.eval_temp_spin.setSingleStep(0.1)
        self.eval_temp_spin.setValue(0.3)
        settings_layout.addWidget(temp_label)
        settings_layout.addWidget(self.eval_temp_spin)

        self.evaluate_btn = QPushButton("Run Evaluation")
        self.evaluate_btn.clicked.connect(self.evaluate_clicked.emit)
        settings_layout.addWidget(self.evaluate_btn)

        self.show_json_btn = QPushButton("Show JSON")
        self.show_json_btn.setEnabled(False)
        self.show_json_btn.clicked.connect(self._show_json_dialog)
        settings_layout.addWidget(self.show_json_btn)

        settings_layout.addStretch()

        group_layout.addLayout(settings_layout)

        self.eval_result_edit = QTextEdit()
        self.eval_result_edit.setPlaceholderText("Evaluation results will appear here...")
        self.eval_result_edit.setReadOnly(True)
        self.eval_result_edit.setMinimumHeight(120)
        group_layout.addWidget(self.eval_result_edit)

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

    def get_eval_config(self):
        return {
            "model": self.eval_model_combo.currentText(),
            "temperature": self.eval_temp_spin.value(),
        }

    def set_eval_model(self, model_name: str):
        idx = self.eval_model_combo.findText(model_name)
        if idx >= 0:
            self.eval_model_combo.setCurrentIndex(idx)
        else:
            self.eval_model_combo.setCurrentText(model_name)

    def set_eval_result(self, text: str, reasoning: Optional[str] = None):
        self.eval_result_edit.setHtml(self._render_markdown(text))
        if reasoning:
            self.reasoning_edit.setPlainText(reasoning)
            self.reasoning_toggle.setVisible(True)
        else:
            self.reasoning_toggle.setVisible(False)
            self.reasoning_edit.setVisible(False)
            self.reasoning_toggle.setChecked(False)
            self.reasoning_edit.setMaximumHeight(0)

    def clear_eval_result(self):
        self.eval_result_edit.clear()
        self.reasoning_edit.clear()
        self.reasoning_toggle.setVisible(False)
        self.reasoning_edit.setVisible(False)
        self.reasoning_toggle.setChecked(False)
        self.reasoning_edit.setMaximumHeight(0)
        self.show_json_btn.setEnabled(False)
        self.eval_request_json = None
        self.eval_response_json = None

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

    def _render_markdown(self, text: str) -> str:
        if not text:
            return ""
        
        md = mistune.create_markdown(plugins=['table', 'strikethrough', 'url'])
        
        html = md(text)
        
        style = """
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
        
        return f"<html><head>{style}</head><body>{html}</body></html>"

    def set_evaluate_enabled(self, enabled: bool):
        self.evaluate_btn.setEnabled(enabled)

    def set_eval_json(self, request_json: dict, response_json: dict):
        self.eval_request_json = request_json
        self.eval_response_json = response_json
        self.show_json_btn.setEnabled(True)

    def _show_json_dialog(self):
        if not self.eval_request_json or not self.eval_response_json:
            return
        
        import json
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Eval Model - JSON")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        
        request_edit = QTextEdit()
        request_edit.setPlainText(json.dumps(self.eval_request_json, indent=2, ensure_ascii=False))
        request_edit.setReadOnly(True)
        layout.addWidget(request_edit)
        
        response_edit = QTextEdit()
        response_edit.setPlainText(json.dumps(self.eval_response_json, indent=2, ensure_ascii=False))
        response_edit.setReadOnly(True)
        layout.addWidget(response_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.exec()
