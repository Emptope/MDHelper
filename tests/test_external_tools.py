from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, Timer

import pytest

import mdhelper.integrations.manager as manager_module
from mdhelper.app import ApplicationService
from mdhelper.core.errors import BackendError, ConfigurationError, TaskCancelled
from mdhelper.integrations import DEFAULT_INTEGRATION_REGISTRY
from mdhelper.integrations.gromacs import GromacsAdapter
from mdhelper.integrations.gromacs import frame_progress as gromacs_frame_progress
from mdhelper.integrations.gromacs import output_message as gromacs_output_message
from mdhelper.integrations.manager import IntegrationManager
from mdhelper.integrations.models import (
    Detection,
    IntegrationAdapter,
    IntegrationConfig,
    IntegrationRegistry,
)
from mdhelper.integrations.vmd import VmdAdapter
from mdhelper.project import Project
from mdhelper.runtime.process import hidden_window_flags
from mdhelper.services.config import UserConfig


class FakeAdapter(IntegrationAdapter):
    name = "fake"

    def __init__(self, program: Path):
        self.program = str(program)

    def candidate_names(self) -> tuple[str, ...]:
        return ()

    def environment_paths(self, environment: dict[str, str]) -> tuple[tuple[str, str], ...]:
        value = environment.get("FAKE_TOOL")
        return (("FAKE_TOOL", value),) if value else ()

    def parse_version(self, stdout: str, stderr: str, exit_code: int) -> str | None:
        return "1.2.3" if exit_code == 0 and "FakeTool 1.2.3" in stdout else None

    def version_arguments(self, detect_path: str | None = None) -> tuple[str, ...]:
        del detect_path
        return ("--version",)

    def command_prefix(self) -> tuple[str, ...]:
        return (self.program,)

    def capability_arguments(self) -> tuple[str, ...]:
        return ("capabilities",)

    def parse_capabilities(self, stdout: str, stderr: str, exit_code: int) -> tuple[str, ...]:
        return ("echo",) if exit_code == 0 and "echo" in stdout else ()


def _fake_program(path: Path) -> Path:
    path.write_text(
        "import sys\n"
        "import time\n"
        "command = sys.argv[1] if len(sys.argv) > 1 else ''\n"
        "if command == '--version': print('FakeTool 1.2.3'); raise SystemExit(0)\n"
        "if command == 'capabilities': print('echo'); raise SystemExit(0)\n"
        "if command == 'fail': print('failed intentionally', file=sys.stderr); "
        "raise SystemExit(9)\n"
        "if command == 'wait': time.sleep(5); raise SystemExit(0)\n"
        "if command == 'progress':\n"
        "    for frame in range(3):\n"
        "        print(f'Reading frame {frame} time {frame * 2.0:.3f}', flush=True)\n"
        "        time.sleep(0.3)\n"
        "    raise SystemExit(0)\n"
        "if command == 'tree':\n"
        "    import subprocess\n"
        "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
        "    time.sleep(5)\n"
        "    raise SystemExit(0)\n"
        "print('\\n'.join(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    return path


def _gromacs_candidate(root: Path, version: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / GromacsAdapter().candidate_names()[0]
    path.write_text(version, encoding="utf-8")
    path.chmod(0o755)
    return path


def _stub_gromacs_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    def detect(
        adapter: IntegrationAdapter,
        candidate: str,
        source: str,
        rank: int,
        timeout: float,
        environment: dict[str, str],
        detection_factory: object,
    ) -> Detection:
        del timeout, environment, detection_factory
        path = Path(candidate).resolve()
        if not path.is_file():
            return Detection(
                adapter.name,
                source,
                candidate,
                False,
                error="Executable was not found.",
                rank=rank,
            )
        return Detection(
            adapter.name,
            source,
            candidate,
            True,
            path=str(path),
            version=path.read_text(encoding="utf-8"),
            capabilities=("rdf", "select", "check"),
            rank=rank,
        )

    monkeypatch.setattr(manager_module, "detect_candidate", detect)


def _fake_integration(
    tmp_path: Path,
) -> tuple[IntegrationManager, Path, IntegrationRegistry]:
    program = _fake_program(tmp_path / "fake tool.py")
    registry = IntegrationRegistry()
    registry.register(FakeAdapter(program))
    environment = dict(os.environ)
    environment["FAKE_TOOL"] = sys.executable
    manager = IntegrationManager(
        {"fake": IntegrationConfig()}, registry, environment
    )
    return manager, program, registry


def test_supported_registry_includes_gromacs_and_vmd() -> None:
    assert DEFAULT_INTEGRATION_REGISTRY.names() == ("gromacs", "vmd")
    registry = IntegrationRegistry()
    registry.register(GromacsAdapter())
    registry.register(VmdAdapter())
    assert registry.names() == ("gromacs", "vmd")


def test_background_processes_hide_windows_console(monkeypatch) -> None:
    monkeypatch.setitem(vars(subprocess), "CREATE_NO_WINDOW", 0x08000000)

    assert hidden_window_flags("nt") == 0x08000000
    assert hidden_window_flags("posix") == 0


def test_gromacs_output_parsing() -> None:
    adapter = GromacsAdapter()
    assert adapter.parse_version("GROMACS version: 2026.3", "", 0) == "2026.3"
    assert adapter.parse_version("not the requested tool", "", 0) is None
    assert adapter.parse_capabilities(
        "gmx rdf\ngmx select\ngmx check\ngmx custom-command", "", 0
    ) == ("rdf", "select", "check", "custom-command")
    assert gromacs_frame_progress(
        "", "Reading frame 20 time 40.000\rReading frame 30 time 60.000"
    ) == (30, 60.0)
    assert gromacs_frame_progress("unrelated", "output") is None
    assert gromacs_output_message(
        "Reading frame 1 time 2.000\rReading frame 2 time 4.000",
        "",
    ) == "GROMACS: Reading frame 2 time 4.000"
    assert gromacs_output_message("", "\nStep 10  Potential -1.0\n") == (
        "GROMACS: Step 10  Potential -1.0"
    )
    assert gromacs_output_message("", "") is None


def test_vmd_version_detect_and_output_parsing(tmp_path: Path) -> None:
    adapter = VmdAdapter()
    detect = tmp_path / "version detect.tcl"

    assert adapter.version_detect() == ("quit\n", ".tcl")
    assert adapter.version_arguments(str(detect)) == (
        "-dispdev",
        "text",
        "-e",
        str(detect),
    )
    assert adapter.parse_version(
        "Info) VMD for WIN64, version 2.0.0a7 (August 1, 2025)", "", 0
    ) == "2.0.0a7"


def test_detection_materializes_and_removes_version_detect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = VmdAdapter()
    candidate = tmp_path / "vmd"
    candidate.write_text("candidate", encoding="ascii")
    candidate.chmod(0o755)
    observed: list[Path] = []

    def run(
        path: str,
        prefix: tuple[str, ...],
        arguments: tuple[str, ...],
        timeout: float,
        environment: dict[str, str],
    ) -> object:
        del path, prefix, timeout, environment
        detect = Path(arguments[-1])
        observed.append(detect)
        assert detect.read_text(encoding="ascii") == "quit\n"
        return type(
            "Completed",
            (),
            {
                "stdout": "Info) VMD for WIN64, version 2.0.0a7",
                "stderr": "",
                "returncode": 0,
            },
        )()

    monkeypatch.setattr("mdhelper.runtime.detection._run", run)
    registry = IntegrationRegistry()
    registry.register(adapter)
    manager = IntegrationManager(
        {"vmd": IntegrationConfig(path=str(candidate), use_environment=False)},
        registry,
        {"PATH": ""},
    )

    status = manager.detect("vmd")

    assert status.available
    assert len(observed) == 1
    assert not observed[0].exists()


def test_generic_detection_status_and_safe_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, _program_path, _ = _fake_integration(tmp_path)
    logged: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        "mdhelper.runtime.execution.record_command",
        lambda command, cwd: logged.append((command, cwd)),
    )
    status = manager.detect("fake")
    assert status.available
    assert status.version == "1.2.3"
    assert status.capabilities == ("echo",)
    assert status.path == str(Path(sys.executable).resolve())
    assert manager.status("fake") == status

    injection = "hello;touch should-not-exist"
    record = manager.run("fake", [injection], tmp_path)
    assert record.command == manager.format_command("fake", [injection])
    assert logged == [(record.command, tmp_path.resolve())]
    assert injection in record.stdout
    assert not (tmp_path / "should-not-exist").exists()

    failed = manager.run("fake", ["fail"], tmp_path)
    assert failed.exit_code == 9
    assert failed.status == "failed"

    cancel = Event()
    cancel.set()
    with pytest.raises(TaskCancelled) as cancelled:
        manager.run("fake", ["wait"], tmp_path, cancel_event=cancel)
    assert cancelled.value.details is not None
    assert cancelled.value.details["integration_run"]["status"] == "cancelled"  # type: ignore[index]

    with pytest.raises(BackendError) as timed_out:
        manager.run(
            "fake", ["wait"], tmp_path, timeout_seconds=0.01
        )
    assert timed_out.value.details is not None
    assert timed_out.value.details["integration_run"]["status"] == "timed_out"  # type: ignore[index]

    with pytest.raises(BackendError, match="finite positive"):
        manager.run("fake", ["echo"], tmp_path, timeout_seconds=0)


def test_running_integration_reports_output_before_completion(tmp_path: Path) -> None:
    manager, _program_path, _ = _fake_integration(tmp_path)
    updates: list[tuple[float, str, str]] = []
    started = time.monotonic()

    record = manager.run(
        "fake",
        ["progress"],
        tmp_path,
        process_progress=lambda elapsed, stdout, stderr: updates.append(
            (elapsed, stdout, stderr)
        ),
    )

    assert record.status == "completed"
    assert len(updates) >= 2
    assert any("Reading frame 0" in stdout for _, stdout, _ in updates[:-1])
    assert updates[0][0] < record.elapsed_seconds
    assert time.monotonic() - started < 3


def test_running_integration_cancels_process_tree_promptly(tmp_path: Path) -> None:
    manager, _program_path, _ = _fake_integration(tmp_path)
    cancel = Event()
    timer = Timer(0.2, cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(TaskCancelled):
            manager.run("fake", ["tree"], tmp_path, cancel_event=cancel)
    finally:
        timer.cancel()

    assert time.monotonic() - started < 2


def test_configured_path_replaces_cached_detection(tmp_path: Path) -> None:
    program = _fake_program(tmp_path / "fake tool.py")
    registry = IntegrationRegistry()
    registry.register(FakeAdapter(program))
    application = ApplicationService(
        UserConfig(integrations={"fake": IntegrationConfig()}),
        integration_registry=registry,
    )
    application.context.integrations.environment = {}
    draft = IntegrationConfig(path=str(Path(sys.executable)))

    assert not application.integrations.status("fake").available
    detected = application.integrations.detect("fake", config=draft)
    assert detected.available
    assert application.integrations.is_configured("fake")
    assert detected.source == "user_config"
    assert not application.integrations.status("fake").available

    application.integrations.configure({"fake": draft})

    refreshed = application.integrations.status("fake")
    assert refreshed.available
    assert refreshed.path == str(Path(sys.executable).resolve())
    assert refreshed.source == "user_config"


def test_gromacs_detection_precedence_and_candidate_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = IntegrationRegistry()
    registry.register(GromacsAdapter())
    _stub_gromacs_detection(monkeypatch)
    explicit = _gromacs_candidate(tmp_path / "explicit path", "run")
    configured = _gromacs_candidate(tmp_path / "configured", "config")
    search = _gromacs_candidate(tmp_path / "search", "search")
    mdhelper_env = _gromacs_candidate(tmp_path / "environment", "env")
    gmxbin = _gromacs_candidate(tmp_path / "gmxbin", "gmxbin")
    path_candidate = _gromacs_candidate(tmp_path / "path", "path")
    environment = {
        "MDHELPER_GROMACS": str(mdhelper_env),
        "GMXBIN": str(gmxbin.parent),
        "PATH": str(path_candidate.parent),
    }
    manager = IntegrationManager(
        {
            "gromacs": IntegrationConfig(
                path=str(configured), search_paths=(str(search),)
            )
        },
        registry,
        environment,
    )

    status = manager.detect("gromacs", str(explicit))

    assert [(item.source, item.version) for item in status.detections if item.available] == [
        ("run_override", "run"),
        ("user_config", "config"),
        ("configured_path", "search"),
        ("MDHELPER_GROMACS", "env"),
        ("GMXBIN", "gmxbin"),
        ("PATH", "path"),
    ]
    assert status.path == str(explicit.resolve())


def test_disabled_detection_allows_only_explicit_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = IntegrationRegistry()
    registry.register(GromacsAdapter())
    _stub_gromacs_detection(monkeypatch)
    explicit = _gromacs_candidate(tmp_path / "explicit", "explicit")
    configured = _gromacs_candidate(tmp_path / "configured", "configured")
    manager = IntegrationManager(
        {"gromacs": IntegrationConfig(enabled=False, path=str(configured))},
        registry,
        {},
    )

    assert not manager.detect("gromacs").available
    status = manager.detect("gromacs", str(explicit))
    assert status.available
    assert [item.source for item in status.detections] == ["run_override"]


def test_project_archives_integration_run_outside_manifest(tmp_path: Path) -> None:
    manager, _program_path, registry = _fake_integration(tmp_path)
    topology = tmp_path / "topology"
    trajectory = tmp_path / "trajectory"
    topology.write_text("topology", encoding="utf-8")
    trajectory.write_text("trajectory", encoding="utf-8")
    project = Project.create(tmp_path / "project", topology, trajectory)
    application = ApplicationService(
        UserConfig(
            integrations={"fake": IntegrationConfig(path=str(Path(sys.executable)))}
        ),
        integration_registry=registry,
    )
    application.context.integrations.environment = manager.environment

    record = application.integrations.run(
        "fake", ["echo"], tmp_path, project=project, required_capabilities=("echo",)
    )

    assert record.status == "completed"
    reopened = Project.open(project.root)
    assert "integration_preferences" not in reopened.manifest
    assert "integration_runs" not in reopened.manifest
    run_paths = tuple((project.root / "results" / "runs").glob("*.json"))
    assert len(run_paths) == 1
    run_path = run_paths[0]
    stored = json.loads(run_path.read_text(encoding="utf-8"))
    assert "stdout" not in stored
    assert "stderr" not in stored
    assert "stdout_path" not in stored
    assert "stderr_path" not in stored
    for stream, extension in (("stdout", "out"), ("stderr", "err")):
        content = getattr(record, stream)
        path = run_path.with_suffix(f".{extension}")
        assert path.read_text(encoding="utf-8") == content
        assert stored[f"{stream}_sha256"] == hashlib.sha256(
            content.encode("utf-8")
        ).hexdigest()

    with pytest.raises(BackendError, match="lacks required capabilities"):
        application.integrations.run(
            "fake",
            ["echo"],
            tmp_path,
            project=reopened,
            required_capabilities=("missing",),
        )
    assert len(tuple((project.root / "results" / "runs").glob("*.json"))) == 1

    stdout_path = run_path.with_suffix(".out")
    stdout_path.write_text("changed output\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="stream fingerprint changed"):
        Project.open(project.root, verify_inputs=False)
