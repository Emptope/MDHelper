"""Analysis backend discovery and energy-input actions."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QMainWindow

from mdhelper.app import ApplicationService
from mdhelper.gui.controllers.integration_detection import IntegrationDetectionController
from mdhelper.gui.controllers.session import ProjectSession
from mdhelper.gui.pages.analysis import AnalysisPanel


class BackendActions:
    """Coordinate backend capabilities with the active analysis parameters."""

    def __init__(
        self,
        parent: QMainWindow,
        application: ApplicationService,
        session: ProjectSession,
        analysis: AnalysisPanel,
        show_error: Callable[[BaseException], None],
    ):
        self.parent = parent
        self.application = application
        self.session = session
        self.analysis = analysis
        self.show_error = show_error
        self.gromacs_detected = False
        self.gromacs_capabilities: frozenset[str] = frozenset()
        self.detection = IntegrationDetectionController(application, parent)

        parameters = analysis.parameters
        parameters.energy_terms_requested.connect(self.load_energy_terms)
        parameters.analysis_backend_changed.connect(self.backend_changed)
        parameters.backend_requirements_changed.connect(
            self.sync_gromacs_availability
        )
        self.detection.completed.connect(self.integration_detected)
        self.detection.failed.connect(self.integration_detection_failed)

    def load_energy_terms(self, path: str) -> None:
        backend = self.analysis.parameters.analysis_backend_value()
        self.parent.statusBar().showMessage("Reading energy terms...")
        try:
            terms = self.application.analyses.energy_terms(
                path,
                backend,
                cache_dir=(
                    None
                    if self.session.project is None
                    else self.session.project.cache_dir
                ),
            )
            self.analysis.parameters.set_energy_terms(path, terms)
        except Exception as exc:
            self.show_error(exc)
            return
        self.parent.statusBar().showMessage(f"Loaded {len(terms)} energy terms", 10000)

    def backend_changed(self) -> None:
        parameters = self.analysis.parameters
        path = parameters.energy_path()
        parameters.set_energy_terms("", ())
        if Path(path).expanduser().is_file():
            self.load_energy_terms(path)

    def detect_gromacs(self) -> None:
        configured = self.application.integrations.is_configured("gromacs")
        self.analysis.parameters.set_gromacs_configured(configured)
        if not configured:
            self.gromacs_detected = False
            self.gromacs_capabilities = frozenset()
            self.analysis.parameters.set_gromacs_available(False)
            return
        self.analysis.parameters.set_gromacs_pending()
        self.detection.submit("gromacs")

    def integration_detected(self, name: str, status: object) -> None:
        if name != "gromacs":
            return
        capabilities = getattr(status, "capabilities", ())
        self.gromacs_detected = bool(getattr(status, "available", False))
        self.gromacs_capabilities = frozenset(
            str(capability) for capability in capabilities
        )
        self.sync_gromacs_availability()

    def integration_detection_failed(self, name: str, _error: object) -> None:
        if name != "gromacs":
            return
        self.gromacs_detected = False
        self.gromacs_capabilities = frozenset()
        self.sync_gromacs_availability()

    def sync_gromacs_availability(self) -> None:
        parameters = self.analysis.parameters
        analysis_type = parameters.analysis_type_value()
        try:
            frames = None if analysis_type == "energy" else parameters.frame_range()
        except ValueError:
            parameters.set_gromacs_available(False)
            return
        required = self.application.analyses.backend_capabilities(
            "gromacs",
            analysis_type,
            frames,
        )
        parameters.set_gromacs_available(
            self.gromacs_detected
            and set(required).issubset(self.gromacs_capabilities)
        )

    def shutdown(self) -> None:
        self.detection.shutdown()
