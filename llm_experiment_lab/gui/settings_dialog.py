from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QCheckBox,
    QComboBox, QSpinBox, QFormLayout,
    QDialogButtonBox, QTextEdit,
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        api_group = QGroupBox("API Settings")
        api_layout = QFormLayout()

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Enter API key...")
        api_layout.addRow("API Key:", self.api_key_edit)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setText("https://api.openai.com/v1")
        api_layout.addRow("Base URL:", self.base_url_edit)

        self.verify_ssl_check = QCheckBox()
        self.verify_ssl_check.setChecked(True)
        api_layout.addRow("Verify SSL:", self.verify_ssl_check)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        exec_group = QGroupBox("Execution Settings")
        exec_layout = QFormLayout()

        self.exec_mode_combo = QComboBox()
        self.exec_mode_combo.addItems(["Parallel", "Sequential"])
        exec_layout.addRow("Mode:", self.exec_mode_combo)

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 60)
        self.delay_spin.setValue(1)
        self.delay_spin.setSuffix(" seconds")
        exec_layout.addRow("Delay (sequential):", self.delay_spin)

        exec_group.setLayout(exec_layout)
        layout.addWidget(exec_group)

        eval_default_group = QGroupBox("Default Eval Model")
        eval_default_layout = QFormLayout()

        self.default_eval_model = QLineEdit()
        self.default_eval_model.setText("gpt-4")
        eval_default_layout.addRow("Model:", self.default_eval_model)

        self.default_eval_system_prompt = QTextEdit()
        self.default_eval_system_prompt.setPlaceholderText("System prompt for evaluator...")
        self.default_eval_system_prompt.setMaximumHeight(80)
        eval_default_layout.addRow("System Prompt:", self.default_eval_system_prompt)

        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset_eval_defaults)
        eval_default_layout.addRow("", reset_btn)

        eval_template_label = QLabel("Eval Prompt Template (read-only):")
        eval_default_layout.addRow(eval_template_label, None)

        self.eval_template = QTextEdit()
        self.eval_template.setReadOnly(True)
        self.eval_template.setMaximumHeight(150)
        self.eval_template.setPlaceholderText("Template for evaluator prompt...")
        eval_default_layout.addRow("", self.eval_template)

        eval_default_group.setLayout(eval_default_layout)
        layout.addWidget(eval_default_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    DEFAULT_EVAL_SYSTEM_PROMPT = "You are an expert evaluator. Compare LLM responses and provide fair, objective analysis."

    DEFAULT_EVAL_TEMPLATE = """Сравните следующие ответы на один и тот же запрос и предоставьте рейтинг от лучшего к худшему с краткими пояснениями.

Системный промпт: {system_prompt}

Пользовательский промпт: {user_prompt}

---
Ответы моделей:
{responses}

---
Предоставьте:
1. Рейтинг от лучшего (1-е место) к худшему
2. Краткое пояснение для каждого места
3. Ключевые сильные и слабые стороны каждого ответа
4. Учтите при оценке скорость ответа и количество затраченных токенов"""

    def _reset_eval_defaults(self):
        self.default_eval_system_prompt.setPlainText(self.DEFAULT_EVAL_SYSTEM_PROMPT)
        self.default_eval_model.setText("gpt-4")

    def get_settings(self):
        return {
            "api": {
                "api_key": self.api_key_edit.text(),
                "base_url": self.base_url_edit.text(),
                "verify_ssl": self.verify_ssl_check.isChecked(),
            },
            "execution": {
                "mode": self.exec_mode_combo.currentText().lower(),
                "delay_seconds": self.delay_spin.value(),
            },
            "eval_model": {
                "name": self.default_eval_model.text(),
                "system_prompt": self.default_eval_system_prompt.toPlainText(),
            },
        }

    def set_settings(self, settings: dict):
        if "api" in settings:
            self.api_key_edit.setText(settings["api"].get("api_key", ""))
            self.base_url_edit.setText(settings["api"].get("base_url", "https://api.openai.com/v1"))
            self.verify_ssl_check.setChecked(settings["api"].get("verify_ssl", True))

        if "execution" in settings:
            mode = settings["execution"].get("mode", "parallel")
            idx = 0 if mode == "parallel" else 1
            self.exec_mode_combo.setCurrentIndex(idx)
            self.delay_spin.setValue(settings["execution"].get("delay_seconds", 1))

        if "eval_model" in settings:
            self.default_eval_model.setText(settings["eval_model"].get("name", "gpt-4"))
            system_prompt = settings["eval_model"].get("system_prompt", self.DEFAULT_EVAL_SYSTEM_PROMPT)
            self.default_eval_system_prompt.setPlainText(system_prompt)
        
        self.eval_template.setPlainText(self.DEFAULT_EVAL_TEMPLATE)
