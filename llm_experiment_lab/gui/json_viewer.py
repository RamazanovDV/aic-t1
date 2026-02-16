import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QTextEdit, QPushButton, QDialogButtonBox,
)
from PyQt6.QtCore import Qt


class JsonViewerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JSON Viewer")
        self.setMinimumSize(700, 500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_model_json(self, model_name: str, request_json: dict, response_json: dict):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)

        request_group = QWidget()
        request_layout = QVBoxLayout(request_group)
        request_header = QHBoxLayout()
        request_header.addWidget(QPushButton("Request"))
        request_header.addStretch()
        copy_req_btn = QPushButton("Copy")
        copy_req_btn.clicked.connect(lambda: self._copy_json(request_json))
        request_header.addWidget(copy_req_btn)
        request_layout.addLayout(request_header)

        request_edit = QTextEdit()
        request_edit.setPlainText(json.dumps(request_json, indent=2, ensure_ascii=False))
        request_edit.setReadOnly(True)
        request_edit.setMaximumHeight(150)
        request_layout.addWidget(request_edit)

        response_group = QWidget()
        response_layout = QVBoxLayout(response_group)
        response_header = QHBoxLayout()
        response_header.addWidget(QPushButton("Response"))
        response_header.addStretch()
        copy_res_btn = QPushButton("Copy")
        copy_res_btn.clicked.connect(lambda: self._copy_json(response_json))
        response_header.addWidget(copy_res_btn)
        response_layout.addLayout(response_header)

        response_edit = QTextEdit()
        response_edit.setPlainText(json.dumps(response_json, indent=2, ensure_ascii=False))
        response_edit.setReadOnly(True)
        response_layout.addWidget(response_edit)

        scroll = QWidget()
        scroll_layout = QVBoxLayout(scroll)
        scroll_layout.addWidget(request_group)
        scroll_layout.addWidget(response_group)
        scroll_layout.addStretch()

        tab_layout.addWidget(scroll)
        self.tabs.addTab(tab, model_name)

    def _copy_json(self, data: dict):
        from PyQt6.QtWidgets import QApplication
        text = json.dumps(data, indent=2, ensure_ascii=False)
        QApplication.clipboard().setText(text)

    def clear(self):
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)
