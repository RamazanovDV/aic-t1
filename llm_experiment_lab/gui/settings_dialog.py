from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QCheckBox,
    QComboBox, QSpinBox, QFormLayout,
    QDialogButtonBox, QTextEdit, QTableWidget,
    QTableWidgetItem, QRadioButton, QWidget,
    QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt
import uuid


class EndpointDialog(QDialog):
    def __init__(self, parent=None, endpoint: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Endpoint" if not endpoint else "Edit Endpoint")
        self.setMinimumWidth(400)
        self.endpoint = endpoint or {}
        self._init_ui()

    def _init_ui(self):
        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setText(self.endpoint.get("name", ""))
        self.name_edit.setPlaceholderText("Display name...")
        layout.addRow("Name:", self.name_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setText(self.endpoint.get("url", "https://api.openai.com/v1"))
        self.url_edit.setPlaceholderText("https://api.openai.com/v1")
        layout.addRow("URL:", self.url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setText(self.endpoint.get("api_key", ""))
        self.api_key_edit.setPlaceholderText("API Key...")
        layout.addRow("API Key:", self.api_key_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow("", buttons)

    def get_endpoint(self) -> dict:
        return {
            "id": self.endpoint.get("id", str(uuid.uuid4())),
            "name": self.name_edit.text(),
            "url": self.url_edit.text(),
            "api_key": self.api_key_edit.text(),
        }


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        endpoints_group = QGroupBox("Endpoints")
        endpoints_layout = QVBoxLayout()

        self.endpoints_table = QTableWidget()
        self.endpoints_table.setColumnCount(4)
        self.endpoints_table.setHorizontalHeaderLabels(["Default", "Name", "URL", "API Key"])
        self.endpoints_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.endpoints_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.endpoints_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.endpoints_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.endpoints_table.setColumnHidden(3, True)
        endpoints_layout.addWidget(self.endpoints_table)

        endpoints_buttons = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_endpoint)
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_endpoint)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_endpoint)
        endpoints_buttons.addWidget(add_btn)
        endpoints_buttons.addWidget(edit_btn)
        endpoints_buttons.addWidget(remove_btn)
        endpoints_buttons.addStretch()
        endpoints_layout.addLayout(endpoints_buttons)

        endpoints_group.setLayout(endpoints_layout)
        layout.addWidget(endpoints_group)

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_endpoint(self):
        dialog = EndpointDialog(self)
        if dialog.exec():
            endpoint = dialog.get_endpoint()
            self._add_endpoint_to_table(endpoint)

    def _edit_endpoint(self):
        row = self.endpoints_table.currentRow()
        if row < 0:
            return
        endpoint_id = self.endpoints_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        endpoint = self._get_endpoint_by_id(endpoint_id)
        if endpoint:
            dialog = EndpointDialog(self, endpoint)
            if dialog.exec():
                updated = dialog.get_endpoint()
                self.endpoints_table.removeRow(row)
                self._add_endpoint_to_table(updated)

    def _remove_endpoint(self):
        row = self.endpoints_table.currentRow()
        if row >= 0:
            self.endpoints_table.removeRow(row)

    def _add_endpoint_to_table(self, endpoint: dict):
        row = self.endpoints_table.rowCount()
        self.endpoints_table.insertRow(row)

        radio = QRadioButton()
        radio.setChecked(endpoint.get("is_default", False))
        radio.toggled.connect(lambda checked, r=row: self._on_default_toggled(r, checked))
        self.endpoints_table.setCellWidget(row, 0, radio)

        name_item = QTableWidgetItem(endpoint.get("name", ""))
        name_item.setData(Qt.ItemDataRole.UserRole, endpoint.get("id", ""))
        self.endpoints_table.setItem(row, 1, name_item)

        url_item = QTableWidgetItem(endpoint.get("url", ""))
        self.endpoints_table.setItem(row, 2, url_item)

        api_key_item = QTableWidgetItem(endpoint.get("api_key", ""))
        api_key_item.setData(Qt.ItemDataRole.UserRole, endpoint.get("id", ""))
        self.endpoints_table.setItem(row, 3, api_key_item)

    def _on_default_toggled(self, row: int, checked: bool):
        if checked:
            for r in range(self.endpoints_table.rowCount()):
                if r != row:
                    widget = self.endpoints_table.cellWidget(r, 0)
                    if widget:
                        widget.setChecked(False)

    def _get_endpoint_by_id(self, endpoint_id: str) -> dict:
        for r in range(self.endpoints_table.rowCount()):
            item = self.endpoints_table.item(r, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == endpoint_id:
                return {
                    "id": endpoint_id,
                    "name": item.text(),
                    "url": self.endpoints_table.item(r, 2).text(),
                    "api_key": self.endpoints_table.item(r, 3).text(),
                }
        return {}

    def get_settings(self) -> dict:
        endpoints = []
        default_endpoint_id = ""
        for r in range(self.endpoints_table.rowCount()):
            radio = self.endpoints_table.cellWidget(r, 0)
            if radio and radio.isChecked():
                default_endpoint_id = self.endpoints_table.item(r, 1).data(Qt.ItemDataRole.UserRole)
            
            endpoints.append({
                "id": self.endpoints_table.item(r, 1).data(Qt.ItemDataRole.UserRole),
                "name": self.endpoints_table.item(r, 1).text(),
                "url": self.endpoints_table.item(r, 2).text(),
                "api_key": self.endpoints_table.item(r, 3).text(),
            })

        return {
            "endpoints": endpoints,
            "default_endpoint_id": default_endpoint_id,
            "execution": {
                "mode": self.exec_mode_combo.currentText().lower(),
                "delay_seconds": self.delay_spin.value(),
            },
        }

    def set_settings(self, settings: dict):
        self.endpoints_table.setRowCount(0)
        
        endpoints = settings.get("endpoints", [])
        default_id = settings.get("default_endpoint_id", "")
        
        for ep in endpoints:
            ep_copy = dict(ep)
            ep_copy["is_default"] = (ep.get("id") == default_id)
            self._add_endpoint_to_table(ep_copy)

        if "execution" in settings:
            mode = settings["execution"].get("mode", "parallel")
            idx = 0 if mode == "parallel" else 1
            self.exec_mode_combo.setCurrentIndex(idx)
            self.delay_spin.setValue(settings["execution"].get("delay_seconds", 1))

        if self.endpoints_table.rowCount() > 0:
            has_default = False
            for r in range(self.endpoints_table.rowCount()):
                widget = self.endpoints_table.cellWidget(r, 0)
                if widget and widget.isChecked():
                    has_default = True
                    break
            if not has_default:
                widget = self.endpoints_table.cellWidget(0, 0)
                if widget:
                    widget.setChecked(True)
