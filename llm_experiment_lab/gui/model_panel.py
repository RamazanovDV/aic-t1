from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit,
    QGroupBox, QLineEdit, QFrame, QPushButton,
    QDialog, QDialogButtonBox,
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

    DEFAULT_MODELS = [
        "gpt-4",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-16k",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-3-haiku-20240307",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]

    def __init__(self, title: str = "Model", parent=None):
        super().__init__(parent)
        self.title = title
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

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedWidth(30)
        self.refresh_btn.setToolTip("Обновить список моделей")
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        top_row.addWidget(self.refresh_btn)

        self.status_indicator = StatusIndicator()
        top_row.addWidget(self.status_indicator)

        self.run_btn = QPushButton("Run")
        self.run_btn.setFixedWidth(60)
        self.run_btn.setToolTip("Запустить эту модель")
        self.run_btn.clicked.connect(self.run_clicked.emit)
        top_row.addWidget(self.run_btn)

        top_row.addStretch()
        group_layout.addLayout(top_row)

        endpoint_row = QHBoxLayout()
        endpoint_label = QLabel("Endpoint:")
        endpoint_label.setToolTip("Кастомный endpoint API (оставьте пустым для использования Base URL из настроек)")
        endpoint_row.addWidget(endpoint_label)
        self.endpoint_edit = QLineEdit()
        self.endpoint_edit.setPlaceholderText("Optional custom endpoint...")
        self.endpoint_edit.setToolTip("Кастомный endpoint API (оставьте пустым для использования Base URL из настроек)")
        self.endpoint_edit.textChanged.connect(self.config_changed.emit)
        endpoint_row.addWidget(self.endpoint_edit)
        group_layout.addLayout(endpoint_row)

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

        group.setLayout(group_layout)
        layout.addWidget(group)

    def _on_refresh_clicked(self):
        self.dropdown_opened.emit()

    def get_model_config(self):
        from ..core.experiment import ModelConfig
        return ModelConfig(
            name=self.model_combo.currentText(),
            custom_endpoint=self.endpoint_edit.text(),
            temperature=self.temp_spin.value(),
            top_p=self.top_p_spin.value(),
            top_k=self.top_k_spin.value(),
        )

    def set_response(self, content: str, stats=None):
        self.response_edit.setPlainText(content)
        if stats:
            self.time_label.setText(f"Time: {stats.response_time:.2f}s")
            self.tokens_label.setText(
                f"Tokens: {stats.prompt_tokens} + {stats.completion_tokens} = {stats.total_tokens}"
            )

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
        response_edit.setPlainText(json.dumps(self.response_json, indent=2, ensure_ascii=False))
        response_edit.setReadOnly(True)
        layout.addWidget(response_edit)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.exec()

    def set_status(self, status: str):
        self.status_indicator.set_status(status)

    def clear_response(self):
        self.response_edit.clear()
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
        self.model_combo.addItems(models)
        if current in models:
            self.model_combo.setCurrentText(current)

    def get_raw_json(self) -> dict:
        return {
            "request": {},
            "response": {},
        }

    def set_run_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
