from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

from test_synthetic_system import _write_trajectory

import mdhelper.bootstrap.portable as portable
import mdhelper.bootstrap.windows_console as windows_console
from mdhelper.app import ApplicationService
from mdhelper.app.reports import result_summary
from mdhelper.core.system import FrameRange
from mdhelper.gui.main import tui_command
from mdhelper.integrations.models import IntegrationStatus
from mdhelper.services.config import UserConfig
from mdhelper.tui.controller import Tui
from mdhelper.tui.formatting import draft_issues
from mdhelper.tui.main import main
from mdhelper.tui.model import AnalysisDraft, Workspace
from mdhelper.tui.terminal import Terminal


def test_native_backend_requires_an_index_in_tui_setup() -> None:
    workspace = Workspace(topology="topology.gro", trajectory="trajectory.gro")
    draft = AnalysisDraft("rdf", analysis_backend="native")
    draft.reference = "reference"
    draft.selection = "selection"
    draft.output = "results"

    assert "select an index file for the Native backend" in draft_issues(
        draft,
        workspace,
    )


def test_tui_unloaded_home_shows_only_load_actions_and_developer() -> None:
    output = StringIO()

    assert main([], StringIO("q\n"), output, ApplicationService(UserConfig())) == 0

    text = output.getvalue()
    assert "Developer: Tuo Yao (Shanghai Jiao Tong University)" in text
    assert " Load " in text
    assert "Load topology and trajectory" in text
    assert "Open an existing project" in text
    assert "Main menu" not in text
    assert "Current project: none" in text
    assert "Current workspace: not loaded" in text
    assert "Analysis" not in text


def test_loaded_main_menu_contains_only_primary_actions() -> None:
    output = StringIO()
    tui = Tui(ApplicationService(UserConfig()), Terminal(StringIO("q\n"), output))
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"

    assert tui.run() == 0

    text = output.getvalue()
    assert "Current project: none" in text
    assert "Current workspace: trajectory.xtc" in text
    assert "Main menu" in text
    assert "  1  Analysis" in text
    assert "  2  Results and export" in text
    assert "  3  Workspace" in text
    assert "  4  Tools" in text
    assert "Confirm species roles" not in text
    assert "Configuration summary" not in text


def test_nested_menus_have_visible_spacing() -> None:
    output = StringIO()
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("3\n0\nq\n"), output),
    )
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"

    assert tui.run() == 0

    text = output.getvalue()
    assert "Current workspace: trajectory.xtc\n\n" in text
    assert "Workspace" in text
    assert "Select:" not in text
    assert "  q  Quit\n\n> " in text


def test_tools_separates_integrations_templates_and_configuration(monkeypatch) -> None:
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("1\n2\n3\n0\n"), StringIO()),
    )
    calls: list[str] = []
    monkeypatch.setattr(tui, "_integrations", lambda: calls.append("integrations"))
    monkeypatch.setattr(tui, "_templates", lambda: calls.append("templates"))
    monkeypatch.setattr(tui, "_config", lambda: calls.append("configuration"))

    try:
        tui._tools()
    finally:
        tui.tasks.shutdown()

    assert calls == ["integrations", "templates", "configuration"]


def test_opening_project_returns_to_main_menu(monkeypatch) -> None:
    application = ApplicationService(UserConfig())
    tui = Tui(application, Terminal(StringIO("1\n"), StringIO()))
    calls: list[str] = []
    monkeypatch.setattr(tui, "_open_project", lambda: calls.append("open"))

    try:
        tui._projects()
    finally:
        tui.tasks.shutdown()

    assert calls == ["open"]


def test_unified_entry_prefers_gui_and_routes_explicit_modes(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    console_calls: list[None] = []
    detach_calls: list[None] = []
    monkeypatch.setattr(portable, "gui_available", lambda: True)
    monkeypatch.setattr(portable, "show_console", lambda: console_calls.append(None))
    monkeypatch.setattr(
        portable, "detach_console", lambda *_args: detach_calls.append(None)
    )
    monkeypatch.setattr(
        portable, "gui_main", lambda values: calls.append(("gui", values)) or 0
    )
    monkeypatch.setattr(
        portable, "tui_main", lambda values: calls.append(("tui", values)) or 0
    )
    monkeypatch.setattr(
        portable, "cli_main", lambda values: calls.append(("cli", values)) or 0
    )

    assert portable.main([]) == 0
    assert portable.main(["gui", "--smoke-test"]) == 0
    assert portable.main(["tui", "--smoke-test"]) == 0
    assert portable.main(["cli", "inspect", "--help"]) == 0
    assert portable.main(["inspect", "--help"]) == 0
    assert calls == [
        ("gui", []),
        ("gui", ["--smoke-test"]),
        ("tui", ["--smoke-test"]),
        ("cli", ["inspect", "--help"]),
        ("cli", ["inspect", "--help"]),
    ]
    assert len(console_calls) == 3
    assert len(detach_calls) == 2


def test_unified_entry_falls_back_when_default_gui_is_unavailable(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    console_calls: list[None] = []
    detach_calls: list[None] = []
    monkeypatch.setattr(portable, "gui_available", lambda: False)
    monkeypatch.setattr(portable, "show_console", lambda: console_calls.append(None))
    monkeypatch.setattr(
        portable, "detach_console", lambda *_args: detach_calls.append(None)
    )
    monkeypatch.setattr(
        portable, "tui_main", lambda values: calls.append(("tui", values)) or 0
    )

    assert portable.main([]) == 0
    assert calls == [("tui", [])]
    assert console_calls == [None]
    assert detach_calls == []


def test_unified_entry_restores_console_after_gui_startup_failure(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    console_calls: list[None] = []
    detach_calls: list[None] = []
    monkeypatch.setattr(portable, "gui_available", lambda: True)
    monkeypatch.setattr(portable, "show_console", lambda: console_calls.append(None))
    monkeypatch.setattr(
        portable, "detach_console", lambda *_args: detach_calls.append(None)
    )
    monkeypatch.setattr(portable, "gui_main", lambda _values: portable.GUI_UNAVAILABLE)
    monkeypatch.setattr(
        portable, "tui_main", lambda values: calls.append(("tui", values)) or 0
    )

    assert portable.main([]) == 0
    assert calls == [("tui", [])]
    assert console_calls == [None]
    assert detach_calls == [None]


def test_console_visibility_is_limited_to_frozen_windows(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []

    class Kernel:
        @staticmethod
        def GetConsoleWindow() -> int:
            return 1

    class User:
        @staticmethod
        def ShowWindow(window: int, state: int) -> None:
            calls.append((window, state))

    class Windll:
        kernel32 = Kernel()
        user32 = User()

    monkeypatch.setattr("ctypes.windll", Windll(), raising=False)

    portable.show_console("linux", frozen=True)
    portable.show_console("win32", frozen=False)
    portable.show_console("win32", frozen=True)

    assert calls == [(1, 5)]


def test_console_detachment_is_limited_to_frozen_windows(monkeypatch) -> None:
    calls: list[None] = []

    class Kernel:
        @staticmethod
        def FreeConsole() -> None:
            calls.append(None)

    class Windll:
        kernel32 = Kernel()

    monkeypatch.setattr("ctypes.windll", Windll(), raising=False)

    portable.detach_console("linux", frozen=True)
    portable.detach_console("win32", frozen=False)
    portable.detach_console("win32", frozen=True)

    assert calls == [None]


def test_frozen_windows_gui_starts_as_a_detached_process(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    gui_calls: list[list[str]] = []
    detach_calls: list[None] = []
    environment = {"PATH": "runtime"}

    def popen(command: list[str], **options: object) -> object:
        calls.append((command, options))
        return object()

    monkeypatch.setattr(portable.subprocess, "Popen", popen)
    monkeypatch.setattr(
        portable, "gui_main", lambda values: gui_calls.append(values) or 0
    )
    monkeypatch.setattr(portable, "detach_console", lambda *_args: detach_calls.append(None))

    assert (
        portable.start_gui(
            ["--smoke-test"], environment, "win32", True, "mdhelper.exe"
        )
        == 0
    )

    assert gui_calls == []
    assert detach_calls == []
    assert environment == {"PATH": "runtime"}
    assert len(calls) == 1
    command, options = calls[0]
    assert command == ["mdhelper.exe", "gui", "--smoke-test"]
    assert options["creationflags"] == portable.DETACHED_PROCESS
    assert options["stdin"] is portable.subprocess.DEVNULL
    assert options["stdout"] is portable.subprocess.DEVNULL
    assert options["stderr"] is portable.subprocess.DEVNULL
    child_env = options["env"]
    assert isinstance(child_env, dict)
    assert child_env[portable.GUI_PROCESS] == "1"
    assert child_env[portable.RESET_FROZEN_ENV] == "1"


def test_detached_gui_process_clears_launcher_environment(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    environment = {
        "PATH": "runtime",
        portable.GUI_PROCESS: "1",
        portable.RESET_FROZEN_ENV: "1",
    }
    monkeypatch.setattr(
        portable,
        "detach_console",
        lambda platform, frozen: calls.append((platform, [str(frozen)])),
    )
    monkeypatch.setattr(
        portable, "gui_main", lambda values: calls.append(("gui", values)) or 4
    )

    assert portable.start_gui([], environment, "win32", True, "mdhelper.exe") == 4
    assert environment == {"PATH": "runtime"}
    assert calls == [("win32", ["True"]), ("gui", [])]


def test_frozen_windows_gui_reports_detached_start_failure(monkeypatch) -> None:
    def fail(*_args: object, **_options: object) -> None:
        raise OSError("could not start")

    monkeypatch.setattr(portable.subprocess, "Popen", fail)

    assert (
        portable.start_gui([], {}, "win32", True, "mdhelper.exe")
        == portable.GUI_UNAVAILABLE
    )


def test_windowed_launcher_attaches_to_parent_console(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    class Kernel:
        window = 0

        def GetConsoleWindow(self) -> int:
            return self.window

        def AttachConsole(self, process: int) -> int:
            calls.append(("attach", process))
            self.window = 2
            return 1

        def AllocConsole(self) -> int:
            calls.append(("allocate", 0))
            return 1

    class User:
        @staticmethod
        def ShowWindow(window: int, state: int) -> None:
            calls.append(("show", window * 10 + state))

    class Windll:
        kernel32 = Kernel()
        user32 = User()

    monkeypatch.setattr("ctypes.windll", Windll(), raising=False)

    windows_console.show()

    assert calls == [("attach", -1), ("show", 25)]


def test_windowed_launcher_allocates_console_without_parent(monkeypatch) -> None:
    calls: list[str] = []

    class Kernel:
        window = 0

        def GetConsoleWindow(self) -> int:
            return self.window

        @staticmethod
        def AttachConsole(_process: int) -> int:
            calls.append("attach")
            return 0

        def AllocConsole(self) -> int:
            calls.append("allocate")
            self.window = 3
            return 1

    class User:
        @staticmethod
        def ShowWindow(_window: int, _state: int) -> None:
            calls.append("show")

    class Windll:
        kernel32 = Kernel()
        user32 = User()

    monkeypatch.setattr("ctypes.windll", Windll(), raising=False)

    windows_console.show()

    assert calls == ["attach", "allocate", "show"]


def test_windowed_launcher_restores_standard_streams(monkeypatch) -> None:
    handles = {-10: 10, -11: 11, -12: 11}
    opened: list[tuple[int, str]] = []

    class Kernel:
        @staticmethod
        def GetStdHandle(identifier: int) -> int:
            return handles[identifier]

    def open_stream(handle: int, mode: str) -> StringIO:
        opened.append((handle, mode))
        return StringIO()

    values: tuple[object, object, object]
    with monkeypatch.context() as patch:
        patch.setattr(windows_console, "_open_stream", open_stream)
        for name in ("stdin", "stdout", "stderr"):
            patch.setattr(sys, name, None)
            patch.setattr(sys, f"__{name}__", None)

        windows_console._restore_streams(Kernel())
        values = (sys.stdin, sys.stdout, sys.stderr)

    assert all(value is not None for value in values)
    assert values[1] is values[2]
    assert opened == [(10, "r"), (11, "w")]


def test_gui_availability_requires_qt_and_a_linux_display() -> None:
    def present(_name: str) -> object:
        return object()

    def missing(_name: str) -> None:
        return None

    assert not portable.gui_available({}, "linux", present)
    assert portable.gui_available({"DISPLAY": ":0"}, "linux", present)
    assert portable.gui_available({}, "win32", present)
    assert not portable.gui_available({"DISPLAY": ":0"}, "linux", missing)


def test_gui_tui_command_reuses_the_unified_entry() -> None:
    executable = Path("runtime") / "python"

    assert tui_command(executable, frozen=True) == [str(executable), "tui"]
    assert tui_command(executable, frozen=False) == [
        str(executable),
        "-m",
        "mdhelper",
        "tui",
    ]


def test_rdf_selection_prompts_match_gromacs_labels(monkeypatch) -> None:
    tui = Tui(ApplicationService(UserConfig()), Terminal(StringIO(), StringIO()))
    prompts: list[str] = []

    def select(title: str, current: str = "") -> str:
        prompts.append(title)
        return current or title

    monkeypatch.setattr(tui, "_selection", select)
    draft = AnalysisDraft("rdf")
    try:
        tui._edit_selections(draft)
    finally:
        tui.tasks.shutdown()

    assert prompts == ["Reference", "Selection"]


def test_tui_default_export_directory_follows_selected_trajectory(tmp_path: Path) -> None:
    trajectory = tmp_path / "simulation" / "trajectory.gro"
    workspace = Workspace(trajectory=str(trajectory))

    assert workspace.draft("rdf").output == str(
        trajectory.parent / "results" / "rdf"
    )
    assert workspace.draft("cumulative_rdf").output == str(
        trajectory.parent / "results" / "cn"
    )


def test_tui_analysis_setup_opens_options_before_run_confirmation() -> None:
    output = StringIO()
    tui = Tui(ApplicationService(UserConfig()), Terminal(StringIO("0\n"), output))
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"
    draft = AnalysisDraft(
        "rdf",
        reference="Reference",
        selection="Selection",
        output="results/rdf",
    )

    try:
        tui._analysis_setup(draft)
    finally:
        tui.tasks.shutdown()

    text = output.getvalue()
    assert "Radial Distribution Function (RDF) setup" in text
    assert "Options" in text
    assert "Start RDF now?" not in text


def test_tui_analysis_menu_includes_rdf_cn_combined_plot(monkeypatch) -> None:
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("4\n0\n"), StringIO()),
    )
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"
    calls: list[None] = []
    monkeypatch.setattr(tui.application.integrations, "supports", lambda *_args: True)
    monkeypatch.setattr(tui, "_rdf_cn_setup", lambda: calls.append(None))

    try:
        tui._analyses()
    finally:
        tui.tasks.shutdown()

    assert calls == [None]


def test_tui_keeps_energy_available_through_auto_backend(monkeypatch) -> None:
    output = StringIO()
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("0\n"), output),
    )
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"
    monkeypatch.setattr(tui.application.integrations, "supports", lambda *_args: False)

    try:
        tui._analyses()
    finally:
        tui.tasks.shutdown()

    text = output.getvalue()
    assert "Energy Analysis" in text
    assert "RDF + CN Combined Plot" in text


def test_tui_hides_gromacs_backend_until_explicit_detection(monkeypatch) -> None:
    application = ApplicationService(UserConfig())
    tui = Tui(application, Terminal(StringIO(), StringIO()))
    choices: list[tuple[tuple[str, str], ...]] = []

    def choose(
        _title: str,
        options: tuple[tuple[str, str], ...],
        _default: str | None = None,
    ) -> str:
        choices.append(options)
        return "auto"

    monkeypatch.setattr(tui.terminal, "choose", choose)
    monkeypatch.setattr(tui.application.integrations, "supports", lambda *_args: True)
    monkeypatch.setattr(
        tui.application.context.integrations,
        "detect",
        lambda name, _override=None, _config=None: IntegrationStatus(name, True),
    )
    draft = AnalysisDraft("rdf")
    try:
        tui._edit_backend(draft)
        tui.application.integrations.detect("gromacs")
        tui._edit_backend(draft)
    finally:
        tui.tasks.shutdown()

    assert all(value != "gromacs" for _label, value in choices[0])
    assert any(value == "gromacs" for _label, value in choices[1])


def test_tui_load_does_not_mix_analysis_backend_with_input_inspection(
    monkeypatch,
) -> None:
    output = StringIO()
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("topology.gro\ntrajectory.xtc\n\n1\n"), output),
    )
    inspections: list[None] = []
    monkeypatch.setattr(tui.application.integrations, "supports", lambda *_args: False)
    monkeypatch.setattr(tui, "_inspect", lambda: inspections.append(None))

    try:
        tui._load_inputs()
    finally:
        tui.tasks.shutdown()

    assert inspections == [None]
    assert "Backend" not in output.getvalue()


def test_tui_discovers_and_selects_energy_terms_in_user_order(monkeypatch) -> None:
    output = StringIO()
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("energy.edr\n2 1\n0\n"), output),
    )
    calls: list[str] = []

    def terms(
        path: str, backend: str, *, cache_dir: object = None
    ) -> tuple[str, ...]:
        calls.append(path)
        assert backend == "auto"
        assert cache_dir is None
        return ("Potential", "Temperature", "Pressure")

    monkeypatch.setattr(tui.application.integrations, "supports", lambda *_args: True)
    monkeypatch.setattr(tui.application.analyses, "energy_terms", terms)
    draft = AnalysisDraft("energy")

    try:
        tui._edit_parameters(draft)
    finally:
        tui.tasks.shutdown()

    assert calls == ["energy.edr"]
    assert draft.energy_file == "energy.edr"
    assert draft.energy_terms == ["Temperature", "Potential"]
    text = output.getvalue()
    assert "Energy terms (comma-separated)" not in text
    assert "[ ] Potential" in text
    assert "[x] Potential" in text
    assert "[x] Temperature" in text


def test_tui_energy_rediscovery_preserves_valid_terms_and_removes_stale_terms(
    monkeypatch,
) -> None:
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("new.edr\n0\n"), StringIO()),
    )
    monkeypatch.setattr(tui.application.integrations, "supports", lambda *_args: True)
    monkeypatch.setattr(
        tui.application.analyses,
        "energy_terms",
        lambda _path, _backend, **_kwargs: ("Potential", "Temperature", "Pressure"),
    )
    draft = AnalysisDraft(
        "energy",
        energy_file="old.edr",
        energy_terms=["Pressure", "Stale", "Potential"],
    )

    try:
        tui._edit_parameters(draft)
    finally:
        tui.tasks.shutdown()

    assert draft.energy_file == "new.edr"
    assert draft.energy_terms == ["Pressure", "Potential"]


def test_tui_runs_rdf_cn_and_exports_one_combined_figure(tmp_path: Path) -> None:
    synthetic_path = tmp_path / "trajectory.gro"
    _write_trajectory(synthetic_path)
    application = ApplicationService(UserConfig())
    output = StringIO()
    tui = Tui(application, Terminal(StringIO("y\n"), output))
    summary = application.checks.inspect_system(
        str(synthetic_path), str(synthetic_path)
    )
    tui.workspace.topology = str(synthetic_path)
    tui.workspace.trajectory = str(synthetic_path)
    tui.workspace.summary = summary
    tui.workspace.roles = dict.fromkeys(summary.species, "other")
    tui.workspace.role_decisions = {
        species: {
            "decision": "confirmed_without_suggestion",
            "selected_role": "other",
            "suggestion": suggestion.to_dict(),
        }
        for species, suggestion in summary.role_suggestions.items()
    }
    tui.workspace.radial_output = str(tmp_path / "rdf-cn-output")
    draft = AnalysisDraft(
        "rdf",
        reference="resname REF",
        selection="resname LIGA",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        frames=FrameRange(stop=summary.n_frames),
    )

    try:
        assert tui._run_rdf_cn(draft)
    finally:
        tui.tasks.shutdown()

    export = tmp_path / "rdf-cn-output"
    assert {path.name for path in export.iterdir()} == {
        "rdf",
        "cn",
        "rdf-cn.png",
        "rdf-cn.svg",
        "rdf-cn.pdf",
    }
    assert {path.name for path in (export / "rdf").iterdir()} == {
        "result.json",
        "rdf.csv",
    }
    assert {path.name for path in (export / "cn").iterdir()} == {
        "result.json",
        "cn.csv",
    }
    assert tui.workspace.result is not None
    assert tui.workspace.result.analysis_type == "cumulative_rdf"
    text = output.getvalue()
    assert "Review RDF + CN setup" in text
    assert "RDF completed" in text
    assert "CN completed" in text
    assert "Results" in text
    assert "Configuration" in text
    assert "Technical details" in text


def test_tui_setup_runs_shared_analysis(tmp_path: Path) -> None:
    synthetic_path = tmp_path / "trajectory.gro"
    _write_trajectory(synthetic_path)
    application = ApplicationService(UserConfig())
    output = StringIO()
    tui = Tui(application, Terminal(StringIO("y\n"), output))
    summary = application.checks.inspect_system(
        str(synthetic_path), str(synthetic_path)
    )
    tui.workspace.topology = str(synthetic_path)
    tui.workspace.trajectory = str(synthetic_path)
    tui.workspace.summary = summary
    tui.workspace.roles = dict.fromkeys(summary.species, "other")
    tui.workspace.role_decisions = {
        species: {
            "decision": "confirmed_without_suggestion",
            "selected_role": "other",
            "suggestion": suggestion.to_dict(),
        }
        for species, suggestion in summary.role_suggestions.items()
    }
    draft = AnalysisDraft(
        "cumulative_rdf",
        reference="resname REF",
        selection="resname LIGA",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        frames=FrameRange(stop=summary.n_frames),
        output=str(tmp_path / "tui-output"),
        include_figures=False,
    )

    try:
        assert tui._run_analysis(draft)
    finally:
        tui.tasks.shutdown()

    assert tui.workspace.result is not None
    assert tui.workspace.result.data["cumulative_number"][-1] == 2.0
    assert (tmp_path / "tui-output" / "result.json").is_file()
    text = output.getvalue()
    assert "Review Cumulative Coordination Number (CN) setup" in text
    assert "[Groups]" in text
    assert "[Frames]" in text
    assert "every 1 frames" in text
    assert "[Parameters]" in text
    assert "Bin width:" in text
    assert "Analysis completed" in text
    assert result_summary(tui.workspace.result) in text
