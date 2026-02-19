from pathlib import Path

import mistune

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QLabel, QLineEdit, QTextEdit,
    QSplitter, QMessageBox, QWidget, QTabWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor

from ..core.experiment_storage import (
    list_experiments,
    get_experiment_by_id,
    delete_experiment,
    experiment_exists,
)


def _render_markdown(text: str) -> str:
    if not text:
        return ""
    
    md = mistune.create_markdown(plugins=['table', 'strikethrough', 'url'])
    
    html = md(text)
    
    style = """
    <style>
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 14px;
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


class SaveExperimentDialog(QDialog):
    def __init__(self, parent=None, default_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Save Experiment")
        self.setMinimumWidth(400)
        self.experiment_name = ""
        self._init_ui(default_name)

    def _init_ui(self, default_name: str):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Experiment name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(default_name)
        self.name_edit.setPlaceholderText("Enter experiment name...")
        layout.addWidget(self.name_edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("Please enter a name")
            return

        existing = experiment_exists(name)
        if existing:
            reply = QMessageBox.question(
                self,
                "Experiment Exists",
                f"Experiment '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.experiment_name = name
        self.accept()

    def get_name(self) -> str:
        return self.experiment_name


class LoadExperimentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Experiment")
        self.setMinimumSize(500, 400)
        self.selected_id = None
        self.selected_data = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self._load_experiments()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._on_load)
        btn_layout.addWidget(load_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _load_experiments(self):
        self.experiments = list_experiments()
        self.list_widget.clear()

        for exp in self.experiments:
            timestamp = exp.get("timestamp", "")
            name = exp.get("name", "Unnamed")
            self.list_widget.addItem(f"{timestamp} - {name}")

    def _on_load(self):
        current_row = self.list_widget.currentRow()
        if current_row < 0 or current_row >= len(self.experiments):
            QMessageBox.warning(self, "Warning", "Please select an experiment")
            return

        exp = self.experiments[current_row]
        self.selected_id = exp["id"]
        self.selected_data = get_experiment_by_id(self.selected_id)
        self.accept()

    def _on_delete(self):
        current_row = self.list_widget.currentRow()
        if current_row < 0 or current_row >= len(self.experiments):
            QMessageBox.warning(self, "Warning", "Please select an experiment")
            return

        exp = self.experiments[current_row]
        name = exp.get("name", "this experiment")

        reply = QMessageBox.question(
            self,
            "Delete Experiment",
            f"Delete experiment '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            delete_experiment(exp["id"])
            self._load_experiments()

    def get_selected_id(self):
        return self.selected_id

    def get_selected_data(self):
        return self.selected_data


class NotesEditorDialog(QDialog):
    def __init__(self, parent=None, initial_notes: str = "", experiment_id: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Edit Notes (Markdown)")
        self.setMinimumSize(800, 600)
        self.experiment_id = experiment_id
        self.current_notes = initial_notes
        self._init_ui(initial_notes)

    def _init_ui(self, initial_notes: str):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.setTabsClosable(False)
        tabs.currentChanged.connect(self._on_tab_changed)

        self.edit_widget = QWidget()
        edit_layout = QVBoxLayout(self.edit_widget)
        edit_layout.setContentsMargins(0, 0, 0, 0)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlainText(initial_notes)
        self.notes_edit.textChanged.connect(self._on_text_changed)
        edit_layout.addWidget(self.notes_edit)

        self.preview_edit = QTextEdit()
        self.preview_edit.setReadOnly(True)
        self._update_preview(initial_notes)

        tabs.addTab(self.edit_widget, "Edit")
        tabs.addTab(self.preview_edit, "Preview")

        layout.addWidget(tabs)
        self.tabs = tabs

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _on_tab_changed(self, index: int):
        if index == 1:
            self._update_preview(self.notes_edit.toPlainText())

    def _on_text_changed(self):
        text = self.notes_edit.toPlainText()
        self._update_preview(text)

    def _update_preview(self, text: str):
        html = _render_markdown(text)
        self.preview_edit.setHtml(html)

    def get_notes(self) -> str:
        return self.notes_edit.toPlainText()
