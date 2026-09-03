from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

from test_synthetic_system import _write_trajectory

import mdhelper.bootstrap.portable as portable
import mdhelper.bootstrap.windows_console as windows_console
from mdhelper.app import ApplicationService
from mdhelper.core.integrations import IntegrationStatus
from mdhelper.core.species import SpeciesRoleSuggestion
from mdhelper.core.system import FrameRange, SystemSummary
from mdhelper.gui.main import tui_command
from mdhelper.services.config import UserConfig
from mdhelper.tui.controller import Tui
from mdhelper.tui.model import AnalysisDraft, RadialTask, Workspace
from mdhelper.tui.terminal import Terminal


def test_tui_open_project_creates_a_project_from_discovered_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    topology = tmp_path / "system.tpr"
    trajectory = tmp_path / "run.xtc"
    index = tmp_path / "groups.ndx"
    topology.write_text("topology\n", encoding="ascii")
    trajectory.write_text("trajectory\n", encoding="ascii")
    index.write_text("[ System ]\n1\n", encoding="ascii")
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO(f"{tmp_path}\n1\n1\n\n"), StringIO()),
    )
    inspections: list[None] = []
    monkeypatch.setattr(tui, "_inspect", lambda: inspections.append(None))

    try:
        tui._open_project()
    finally:
        tui.job_runner.shutdown()

    assert tui.workspace.project is not None
    assert tui.workspace.project.root == tmp_path.resolve()
    assert tui.workspace.topology == str(topology.resolve())
    assert tui.workspace.trajectory == str(trajectory.resolve())
    assert tui.workspace.index_file == str(index.resolve())
    assert inspections == [None]


def test_tui_open_project_loads_an_existing_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.gro"
    source.write_text("source\n", encoding="ascii")
    application = ApplicationService(UserConfig())
    project = application.projects.create(tmp_path / "project", source, source)
    tui = Tui(
        application,
        Terminal(StringIO(f"{project.root}\n"), StringIO()),
    )
    inspections: list[None] = []
    monkeypatch.setattr(tui, "_inspect", lambda: inspections.append(None))

    try:
        tui._open_project()
    finally:
        tui.job_runner.shutdown()

    assert tui.workspace.project is not None
    assert tui.workspace.project.root == project.root
    assert tui.workspace.topology == str(source.resolve())
    assert tui.workspace.trajectory == str(source.resolve())
    assert inspections == [None]


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


def test_tui_load_menu_uses_quit_command() -> None:
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("q\n"), StringIO()),
    )

    try:
        choice = tui._load_choice()
    finally:
        tui.job_runner.shutdown()

    assert choice == "q"


def test_tui_default_export_directory_follows_selected_trajectory(tmp_path: Path) -> None:
    trajectory = tmp_path / "simulation" / "trajectory.gro"
    workspace = Workspace(trajectory=str(trajectory))

    assert workspace.draft("rdf").output == str(trajectory.parent / "results")
    assert workspace.draft("cumulative_rdf").output == str(trajectory.parent / "results")
    assert workspace.rdf_cn().output == str(trajectory.parent / "results")
    assert workspace.rdf_cn() is not workspace.draft("rdf")


def test_tui_role_suggestion_batch_hides_internal_method() -> None:
    method = "internal evidence source"
    suggestion = SpeciesRoleSuggestion(
        "solvent",
        method,
        {"charge_e": 0.0},
        reason="The molecular charge is neutral.",
    )
    summary = SystemSummary(
        topology="topology.gro",
        trajectory="trajectory.xtc",
        n_atoms=1,
        n_frames=1,
        species={"SOL": 1},
        atom_names={"OW": 1},
        backend="mdanalysis",
        role_suggestions={"SOL": suggestion},
    )
    output = StringIO()
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("n\n"), output),
    )
    tui.workspace.summary = summary

    try:
        tui._apply_role_suggestions()
    finally:
        tui.job_runner.shutdown()

    rendered = output.getvalue()
    assert suggestion.suggested_role in rendered
    assert suggestion.method not in rendered
    assert tui.workspace.roles == {}


def test_tui_analysis_setup_queues_initial_radial_selection(monkeypatch) -> None:
    output = StringIO()
    tui = Tui(ApplicationService(UserConfig()), Terminal(StringIO("0\n"), output))
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"
    draft = AnalysisDraft(
        "rdf",
        output="results/rdf",
    )
    selections: list[None] = []

    def edit_selections(current: AnalysisDraft) -> None:
        selections.append(None)
        current.reference = "Reference"
        current.selection = "Selection"

    monkeypatch.setattr(tui, "_edit_selections", edit_selections)
    monkeypatch.setattr(
        "mdhelper.tui.controllers.analysis.queue.draft_issues", lambda *_args: []
    )

    try:
        tui._analysis_setup(draft)
    finally:
        tui.job_runner.shutdown()

    assert selections == [None]
    assert draft.queue == [
        RadialTask("rdf", "Reference", "Selection", 1.0, 0.002)
    ]


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
        tui.job_runner.shutdown()

    assert all(value != "gromacs" for _label, value in choices[0])
    assert any(value == "gromacs" for _label, value in choices[1])


def test_tui_requires_check_for_sampled_gromacs_rdf(monkeypatch) -> None:
    application = ApplicationService(UserConfig())
    tui = Tui(application, Terminal(StringIO(), StringIO()))
    choices: list[tuple[tuple[str, str], ...]] = []
    supported = {"rdf", "trjconv"}

    def choose(
        _title: str,
        options: tuple[tuple[str, str], ...],
        _default: str | None = None,
    ) -> str:
        choices.append(options)
        return "auto"

    monkeypatch.setattr(tui.terminal, "choose", choose)
    monkeypatch.setattr(
        tui.application.integrations,
        "is_configured",
        lambda _name: True,
    )
    monkeypatch.setattr(
        tui.application.integrations,
        "supports",
        lambda _name, *required: set(required).issubset(supported),
    )
    try:
        tui._edit_backend(AnalysisDraft("rdf"))
        tui._edit_backend(AnalysisDraft("rdf", frames=FrameRange(stride=2)))
    finally:
        tui.job_runner.shutdown()

    assert any(value == "gromacs" for _label, value in choices[0])
    assert all(value != "gromacs" for _label, value in choices[1])


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
        tui.job_runner.shutdown()

    assert inspections == [None]


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
        tui.job_runner.shutdown()

    assert calls == ["energy.edr"]
    assert draft.energy_file == "energy.edr"
    assert draft.energy_terms == ["Temperature", "Potential"]


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
        tui.job_runner.shutdown()

    assert draft.energy_file == "new.edr"
    assert draft.energy_terms == ["Pressure", "Potential"]


def test_tui_radial_task_queue_adds_updates_and_loads(monkeypatch) -> None:
    output = StringIO()
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO("1\n1\n"), output),
    )
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"
    monkeypatch.setattr(
        "mdhelper.tui.controllers.analysis.queue.draft_issues", lambda *_args: []
    )
    draft = AnalysisDraft(
        "rdf",
        reference="Reference",
        selection="First",
        output="results",
        parameter_provenance={
            "r_max_nm": {"decision": "manual", "selected_value": 1.0}
        },
    )

    try:
        tui._add_task(draft)
        draft.r_max_nm = 1.5
        tui._add_task(draft)
        draft.selection = "Second"
        tui._add_task(draft)
        tui._manage_tasks(draft)
    finally:
        tui.job_runner.shutdown()

    assert draft.queue == [
        RadialTask("rdf", "Reference", "First", 1.5, 0.002),
        RadialTask("rdf", "Reference", "Second", 1.5, 0.002),
    ]
    assert draft.queue_index == 0
    assert draft.selection == "First"
    assert draft.parameter_provenance["r_max_nm"]["selected_value"] == 1.5


def test_tui_mixed_queue_keeps_rdf_and_cn_for_same_pair(monkeypatch) -> None:
    tui = Tui(ApplicationService(UserConfig()), Terminal(StringIO(), StringIO()))
    tui.workspace.topology = "topology.gro"
    tui.workspace.trajectory = "trajectory.xtc"
    draft = AnalysisDraft(
        "rdf",
        reference="Reference",
        selection="Selection",
        output="results",
    )
    monkeypatch.setattr(
        "mdhelper.tui.controllers.analysis.queue.draft_issues", lambda *_args: []
    )

    try:
        tui._add_task(draft)
        draft.analysis_type = "cumulative_rdf"
        tui._add_task(draft)
    finally:
        tui.job_runner.shutdown()

    assert [task.analysis_type for task in draft.queue] == [
        "rdf",
        "cumulative_rdf",
    ]


def test_tui_mixed_queue_builds_each_request_once() -> None:
    tui = Tui(
        ApplicationService(UserConfig()),
        Terminal(StringIO(), StringIO()),
    )
    draft = AnalysisDraft(
        "rdf",
        reference="Reference",
        selection="Selection",
        output="results",
        queue=[
            RadialTask("rdf", "Reference", "First", 1.0, 0.002),
            RadialTask("cumulative_rdf", "Reference", "Second", 0.8, 0.004),
        ],
    )
    try:
        runs = tui._radial_runs(draft)
    finally:
        tui.job_runner.shutdown()

    assert [(run.analysis_type, run.selection) for run in runs] == [
        ("rdf", "First"),
        ("cumulative_rdf", "Second"),
    ]


def test_tui_runs_rdf_cn_queue_and_exports_combined_plot(
    tmp_path: Path,
    stub_figure_exports,
) -> None:
    stub_figure_exports()
    synthetic_path = tmp_path / "trajectory.gro"
    index_path = tmp_path / "groups.ndx"
    _write_trajectory(synthetic_path)
    index_path.write_text(
        "[ resname REF ]\n1\n[ resname LIGA ]\n2 3\n[ resname LIGB ]\n4\n",
        encoding="ascii",
    )
    application = ApplicationService(UserConfig())
    output = StringIO()
    tui = Tui(application, Terminal(StringIO(), output))
    summary = application.checks.inspect_system(
        str(synthetic_path), str(synthetic_path)
    )
    tui.workspace.topology = str(synthetic_path)
    tui.workspace.trajectory = str(synthetic_path)
    tui.workspace.index_file = str(index_path)
    tui.workspace.summary = summary
    tui.workspace.roles = dict.fromkeys(summary.species, "solvent")
    draft = AnalysisDraft(
        "rdf",
        analysis_backend="mdanalysis",
        reference="resname REF",
        selection="resname LIGA",
        r_max_nm=0.5,
        bin_width_nm=0.05,
        frames=FrameRange(stop=1),
        output=str(tmp_path / "rdf-cn-output"),
        queue=[
            RadialTask("rdf", "resname REF", "resname LIGA", 0.5, 0.05),
            RadialTask(
                "cumulative_rdf", "resname REF", "resname LIGA", 0.5, 0.05
            ),
            RadialTask("rdf", "resname REF", "resname LIGB", 0.5, 0.05),
            RadialTask(
                "cumulative_rdf", "resname REF", "resname LIGB", 0.5, 0.05
            ),
        ],
    )

    try:
        assert tui._run_rdf_cn(draft)
        tui.workspace.project = application.projects.create(
            tmp_path / "project",
            synthetic_path,
            synthetic_path,
        )
        tui._save_project_figures()
        tui._save_project_figures()
    finally:
        tui.job_runner.shutdown()

    export = tmp_path / "rdf-cn-output"
    assert {path.name for path in export.iterdir()} == {
        "rdf-resname-REF-resname-LIGA",
        "cn-resname-REF-resname-LIGA",
        "rdf-resname-REF-resname-LIGB",
        "cn-resname-REF-resname-LIGB",
        "rdf-cn.png",
        "rdf-cn.svg",
        "rdf-cn.pdf",
    }
    rdf = export / "rdf-resname-REF-resname-LIGA"
    cn = export / "cn-resname-REF-resname-LIGA"
    assert {path.name for path in rdf.iterdir()} == {
        "result.json",
        "rdf.csv",
        "rdf-resname-REF-resname-LIGA.png",
        "rdf-resname-REF-resname-LIGA.svg",
        "rdf-resname-REF-resname-LIGA.pdf",
    }
    assert {path.name for path in cn.iterdir()} == {
        "result.json",
        "rdf_cn.csv",
        "cn-resname-REF-resname-LIGA.png",
        "cn-resname-REF-resname-LIGA.svg",
        "cn-resname-REF-resname-LIGA.pdf",
    }
    for pair in ("rdf-resname-REF-resname-LIGB", "cn-resname-REF-resname-LIGB"):
        directory = export / pair
        assert {path.suffix for path in directory.iterdir()} == {
            ".json",
            ".csv",
            ".png",
            ".svg",
            ".pdf",
        }
    figures = tui.workspace.project.root / "figures"
    assert {path.name for path in figures.iterdir()} == {
        f"{stem}.{suffix}"
        for stem in ("rdf-cn", "rdf-cn-2")
        for suffix in ("png", "svg", "pdf")
    }
    assert tui.workspace.result is not None
    assert tui.workspace.result.analysis_type == "cumulative_rdf"
    assert len(tui.workspace.plot_results) == 4


def test_tui_energy_runs_without_review(monkeypatch) -> None:
    output = StringIO()
    tui = Tui(ApplicationService(UserConfig()), Terminal(StringIO(), output))
    draft = AnalysisDraft(
        "energy",
        energy_file="energy.edr",
        energy_terms=["Potential"],
        output="results",
    )
    calls: list[str] = []
    monkeypatch.setattr(tui, "_requests", lambda _drafts: ("request",))
    monkeypatch.setattr(
        tui,
        "_run_requests",
        lambda _requests: calls.append("run") or (),
    )
    monkeypatch.setattr(
        tui,
        "_complete_batch",
        lambda _results, _output: calls.append("complete"),
    )

    try:
        assert tui._run_analysis(draft)
    finally:
        tui.job_runner.shutdown()

    assert calls == ["run", "complete"]
