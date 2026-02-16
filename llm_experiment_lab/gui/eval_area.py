from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QDoubleSpinBox, QTextEdit,
    QGroupBox, QPushButton, QLineEdit,
)
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

        model_layout = QVBoxLayout()
        model_layout.addWidget(QLabel("Eval Model:"))
        self.eval_model_combo = QComboBox()
        self.eval_model_combo.addItems(self.DEFAULT_EVAL_MODELS)
        self.eval_model_combo.setEditable(True)
        model_layout.addWidget(self.eval_model_combo)
        settings_layout.addLayout(model_layout)

        endpoint_layout = QVBoxLayout()
        endpoint_layout.addWidget(QLabel("Custom Endpoint:"))
        self.eval_endpoint = QLineEdit()
        self.eval_endpoint.setPlaceholderText("Optional...")
        endpoint_layout.addWidget(self.eval_endpoint)
        settings_layout.addLayout(endpoint_layout)

        temp_layout = QVBoxLayout()
        temp_layout.addWidget(QLabel("Temperature:"))
        self.eval_temp_spin = QDoubleSpinBox()
        self.eval_temp_spin.setRange(0.0, 2.0)
        self.eval_temp_spin.setSingleStep(0.1)
        self.eval_temp_spin.setValue(0.3)
        temp_layout.addWidget(self.eval_temp_spin)
        settings_layout.addLayout(temp_layout)

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

        group.setLayout(group_layout)
        layout.addWidget(group)

    def get_eval_config(self):
        return {
            "model": self.eval_model_combo.currentText(),
            "custom_endpoint": self.eval_endpoint.text(),
            "temperature": self.eval_temp_spin.value(),
        }

    def set_eval_model(self, model_name: str):
        idx = self.eval_model_combo.findText(model_name)
        if idx >= 0:
            self.eval_model_combo.setCurrentIndex(idx)
        else:
            self.eval_model_combo.setCurrentText(model_name)

    def set_eval_result(self, text: str):
        self.eval_result_edit.setPlainText(text)

    def clear_eval_result(self):
        self.eval_result_edit.clear()
        self.show_json_btn.setEnabled(False)
        self.eval_request_json = None
        self.eval_response_json = None

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
