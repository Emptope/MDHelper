"""External integration settings for the desktop GUI."""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mdhelper.app import ApplicationService
from mdhelper.core.integrations import IntegrationConfig, IntegrationStatus
from mdhelper.gui.components.paths import PathRow
from mdhelper.gui.formatting import error_text
from mdhelper.services.config import save_config


class IntegrationsDialog(QDialog):
    """Configure and detect supported external software."""

    def __init__(self, application: ApplicationService, parent: QWidget | None = None):
        super().__init__(parent)
        self.application = application
        self.setWindowTitle("Integrations")
        self.resize(760, 560)
        self.setMinimumSize(680, 500)
        self.selected_status: IntegrationStatus | None = None
        self._drafts = {
            name: application.config.integration(name)
            for name in application.integrations.names()
        }
        self._active_name = ""
        self.tool = QComboBox()
        for name in application.integrations.names():
            self.tool.addItem(application.integrations.display_name(name), name)
        self.enabled = QCheckBox("Enable detection")
        self.environment = QCheckBox("Use environment and PATH")
        self.executable = PathRow("Select executable", "Executables (*)")
        self.config_file = PathRow(
            "Select configuration file",
            "TOML files (*.toml);;All files (*)",
        )
        self.config_file.set_path(str(application.config_file))
        self.detect = QPushButton("Detect")
        self.detect.clicked.connect(self._detect)
        self.status = QLabel("Not detected")
        self.status.setWordWrap(True)
        self.version = QLabel("Not detected")
        self.source = QLabel("Not detected")
        self.capabilities = QListWidget()
        self.capabilities.setMinimumHeight(180)
        form = QFormLayout()
        form.addRow("Software", self.tool)
        form.addRow("Executable", self.executable)
        form.addRow("", self.enabled)
        form.addRow("", self.environment)
        form.addRow("", self.detect)
        form.addRow("Configuration file", self.config_file)
        configuration = QGroupBox("Configuration")
        configuration.setLayout(form)
        status_form = QFormLayout()
        status_form.addRow("Status", self.status)
        status_form.addRow("Version", self.version)
        status_form.addRow("Detected from", self.source)
        status_form.addRow("Capabilities", self.capabilities)
        detection = QGroupBox("Detection Result")
        detection.setLayout(status_form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons = buttons
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(configuration)
        layout.addWidget(detection, 1)
        layout.addWidget(buttons)
        self.tool.currentIndexChanged.connect(self._switch)
        self._active_name = self._name()
        self._load(self._active_name)

    def _name(self) -> str:
        return str(self.tool.currentData())

    def _load(self, name: str) -> None:
        config = self._drafts[name]
        self.enabled.setChecked(config.enabled)
        self.environment.setChecked(config.use_environment)
        self.executable.set_path(config.path)
        self.selected_status = None
        self.status.setText("Not detected")
        self.version.setText("Not detected")
        self.source.setText("Not detected")
        self.capabilities.clear()

    def _current_config(self, name: str | None = None) -> IntegrationConfig:
        key = self._name() if name is None else name
        existing = self._drafts[key]
        return IntegrationConfig(
            enabled=self.enabled.isChecked(),
            path=self.executable.edit.text().strip(),
            search_paths=existing.search_paths,
            use_environment=self.environment.isChecked(),
            detect_timeout_seconds=existing.detect_timeout_seconds,
            run_timeout_seconds=existing.run_timeout_seconds,
        )

    def _detect(self) -> None:
        name = self._name()
        config = self._current_config()
        try:
            status = self.application.integrations.detect(name, config=config)
            self.selected_status = status if status.available else None
            if status.available and status.path:
                self.executable.set_path(status.path)
            self._show_status(status)
        except Exception as exc:
            self.selected_status = None
            self.status.setText(error_text(exc))
            self.version.setText("Unavailable")
            self.source.setText("Unavailable")
            self.capabilities.clear()
        self._drafts[name] = self._current_config()

    def _switch(self, _index: int) -> None:
        if self._active_name:
            self._drafts[self._active_name] = self._current_config(self._active_name)
        self._active_name = self._name()
        self._load(self._active_name)

    def _show_status(self, status: IntegrationStatus) -> None:
        self.status.setText(
            "Available" if status.available else status.error or "Unavailable"
        )
        self.version.setText(status.version or "Unavailable")
        self.source.setText(
            status.source.replace("_", " ") if status.source else "Unavailable"
        )
        self.capabilities.clear()
        self.capabilities.addItems(status.capabilities)

    def _save(self) -> None:
        self._drafts[self._name()] = self._current_config()
        config = deepcopy(self.application.config)
        config.integrations.update(self._drafts)
        try:
            save_config(config, self.application.config_file)
        except Exception as exc:
            QMessageBox.critical(self, "Configuration Error", error_text(exc))
            return
        self.application.integrations.configure(self._drafts)
        self.accept()
