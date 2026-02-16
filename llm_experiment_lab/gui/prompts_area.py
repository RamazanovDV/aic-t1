from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QGroupBox,
)
from PyQt6.QtCore import pyqtSignal


class PromptsArea(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        group = QGroupBox("Prompts")
        group_layout = QVBoxLayout()

        sys_layout = QHBoxLayout()
        sys_layout.addWidget(QLabel("System:"))
        self.system_edit = QTextEdit()
        self.system_edit.setPlaceholderText("Enter system prompt...")
        self.system_edit.setMaximumHeight(80)
        self.system_edit.textChanged.connect(self.changed.emit)
        sys_layout.addWidget(self.system_edit)
        group_layout.addLayout(sys_layout)

        user_layout = QHBoxLayout()
        user_layout.addWidget(QLabel("User:"))
        self.user_edit = QTextEdit()
        self.user_edit.setPlaceholderText("Enter user prompt...")
        self.user_edit.setMaximumHeight(120)
        self.user_edit.textChanged.connect(self.changed.emit)
        user_layout.addWidget(self.user_edit)
        group_layout.addLayout(user_layout)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def get_system_prompt(self) -> str:
        return self.system_edit.toPlainText().strip()

    def get_user_prompt(self) -> str:
        return self.user_edit.toPlainText().strip()

    def set_system_prompt(self, text: str):
        self.system_edit.setPlainText(text)

    def set_user_prompt(self, text: str):
        self.user_edit.setPlainText(text)

    def clear(self):
        self.system_edit.clear()
        self.user_edit.clear()
