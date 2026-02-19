from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox,
    QDialogButtonBox, QGroupBox, QComboBox,
    QTextEdit, QLabel,
)
from PyQt6.QtCore import Qt


class EvalSettingsDialog(QDialog):
    DEFAULT_SYSTEM_PROMPT = "You are an expert evaluator. Compare LLM responses and provide fair, objective analysis. Always respond in Russian."
    
    DEFAULT_USER_TEMPLATE = """Сравните следующие ответы на один и тот же запрос и предоставьте рейтинг от лучшего к худшему с краткими пояснениями. Отвечайте на русском языке.

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

    def __init__(self, parent=None, endpoints: list = None):
        super().__init__(parent)
        self.setWindowTitle("Evaluator Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.endpoints = endpoints or []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        api_group = QGroupBox("API Settings")
        api_layout = QFormLayout()

        self.endpoint_combo = QComboBox()
        self.endpoint_combo.addItem("(Default)", "")
        for ep in self.endpoints:
            self.endpoint_combo.addItem(ep.get("name", "Unnamed"), ep.get("id", ""))
        api_layout.addRow("Endpoint:", self.endpoint_combo)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        prompts_group = QGroupBox("Prompts")
        prompts_layout = QFormLayout()

        self.system_prompt_edit = QTextEdit()
        self.system_prompt_edit.setPlaceholderText("System prompt for evaluator...")
        self.system_prompt_edit.setMaximumHeight(80)
        self.system_prompt_edit.setPlainText(self.DEFAULT_SYSTEM_PROMPT)
        prompts_layout.addRow("System Prompt:", self.system_prompt_edit)

        self.user_template_edit = QTextEdit()
        self.user_template_edit.setPlaceholderText("User prompt template...")
        self.user_template_edit.setMaximumHeight(150)
        self.user_template_edit.setPlainText(self.DEFAULT_USER_TEMPLATE)
        prompts_layout.addRow("User Template:", self.user_template_edit)

        prompts_group.setLayout(prompts_layout)
        layout.addWidget(prompts_group)

        generation_group = QGroupBox("Generation Settings")
        generation_layout = QFormLayout()

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(0, 100000)
        self.max_tokens_spin.setValue(0)
        self.max_tokens_spin.setSpecialValueText("No limit")
        self.max_tokens_spin.setToolTip("Maximum number of tokens to generate (0 = no limit)")
        generation_layout.addRow("Max tokens:", self.max_tokens_spin)

        self.stop_sequences_edit = QLineEdit()
        self.stop_sequences_edit.setPlaceholderText("e.g., END, ---, ###")
        self.stop_sequences_edit.setToolTip("Stop sequences")
        generation_layout.addRow("Stop sequences:", self.stop_sequences_edit)

        self.frequency_penalty_spin = QDoubleSpinBox()
        self.frequency_penalty_spin.setRange(-2.0, 2.0)
        self.frequency_penalty_spin.setSingleStep(0.1)
        self.frequency_penalty_spin.setValue(0.0)
        generation_layout.addRow("Frequency penalty:", self.frequency_penalty_spin)

        self.presence_penalty_spin = QDoubleSpinBox()
        self.presence_penalty_spin.setRange(-2.0, 2.0)
        self.presence_penalty_spin.setSingleStep(0.1)
        self.presence_penalty_spin.setValue(0.0)
        generation_layout.addRow("Presence penalty:", self.presence_penalty_spin)

        generation_group.setLayout(generation_layout)
        layout.addWidget(generation_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self) -> dict:
        stop_text = self.stop_sequences_edit.text().strip()
        stop_sequences = [s.strip() for s in stop_text.split(",") if s.strip()]
        endpoint_id = self.endpoint_combo.currentData()
        return {
            "endpoint_id": endpoint_id if endpoint_id else "",
            "system_prompt": self.system_prompt_edit.toPlainText(),
            "user_prompt_template": self.user_template_edit.toPlainText(),
            "max_tokens": self.max_tokens_spin.value(),
            "stop_sequences": stop_sequences,
            "frequency_penalty": self.frequency_penalty_spin.value(),
            "presence_penalty": self.presence_penalty_spin.value(),
        }

    def set_settings(self, settings: dict):
        endpoint_id = settings.get("endpoint_id", "")
        found = False
        for i in range(self.endpoint_combo.count()):
            if self.endpoint_combo.itemData(i) == endpoint_id:
                self.endpoint_combo.setCurrentIndex(i)
                found = True
                break
        if not found:
            self.endpoint_combo.setCurrentIndex(0)

        self.system_prompt_edit.setPlainText(settings.get("system_prompt", self.DEFAULT_SYSTEM_PROMPT))
        self.user_template_edit.setPlainText(settings.get("user_prompt_template", self.DEFAULT_USER_TEMPLATE))
        self.max_tokens_spin.setValue(settings.get("max_tokens", 0))
        
        stop_sequences = settings.get("stop_sequences", [])
        if stop_sequences:
            self.stop_sequences_edit.setText(", ".join(stop_sequences))
        else:
            self.stop_sequences_edit.setText("")
        
        self.frequency_penalty_spin.setValue(settings.get("frequency_penalty", 0.0))
        self.presence_penalty_spin.setValue(settings.get("presence_penalty", 0.0))
