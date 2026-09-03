"""Human-readable terminal views for analysis setup and results."""

from __future__ import annotations

from mdhelper.app.reports import report_for
from mdhelper.core.analysis import AnalysisResult, analysis_label
from mdhelper.core.errors import MDHelperError
from mdhelper.core.system import SystemSummary
from mdhelper.tui.model import AnalysisDraft, RadialTask, Workspace


def _name(path: str | None, fallback: str) -> str:
    return fallback if not path else path.replace("\\", "/").rsplit("/", 1)[-1]


def error_text(error: BaseException) -> str:
    if not isinstance(error, MDHelperError):
        return f"{type(error).__name__}: {error}"
    lines = [error.message]
    if error.hint:
        lines.append(f"Next step: {error.hint}")
    return "\n".join(lines)


def summary_text(summary: SystemSummary) -> str:
    frames = "unknown" if summary.n_frames is None else str(summary.n_frames)
    lines = [
        f"Topology:   {summary.topology}",
        f"Trajectory: {summary.trajectory}",
        f"Backend:    {summary.backend}",
        f"Size:       {summary.n_atoms} atoms, {frames} frames",
        "",
        "Species:",
    ]
    lines.extend(f"  {name}: {count} molecule(s)" for name, count in summary.species.items())
    lines.append("")
    if summary.system_charge_e is not None:
        lines.append(f"System charge: {summary.system_charge_e:.12g} e")
        if summary.has_net_charge:
            lines.append("Warning: the inferred system net charge is outside tolerance.")
    if summary.index_groups:
        lines.append(f"Index groups: {len(summary.index_groups)} loaded")
    return "\n".join(lines)


def roles_text(workspace: Workspace) -> str:
    if workspace.summary is None:
        return "The system has not been inspected."
    headers = ("Species", "Numbers", "Role", "Suggestion")
    rows: list[tuple[str, str, str, str]] = []
    for species, count in workspace.summary.species.items():
        suggestion = workspace.summary.role_suggestions[species]
        suggested = suggestion.suggested_role or "unavailable"
        rows.append(
            (
                species,
                str(count),
                workspace.roles.get(species, "not set"),
                suggested,
            )
        )
    widths = tuple(
        max((len(header), *(len(row[index]) for row in rows)))
        for index, header in enumerate(headers)
    )
    lines = [
        f"{headers[0]:<{widths[0]}}  {headers[1]:>{widths[1]}}  "
        f"{headers[2]:<{widths[2]}}  {headers[3]}"
    ]
    lines.extend(
        f"{species:<{widths[0]}}  {count:>{widths[1]}}  "
        f"{role:<{widths[2]}}  {suggestion}"
        for species, count, role, suggestion in rows
    )
    return "\n".join(lines)


def draft_issues(draft: AnalysisDraft, workspace: Workspace) -> list[str]:
    issues: list[str] = []
    if not workspace.loaded:
        issues.append("load topology and trajectory files")
    if workspace.summary is None:
        issues.append("inspect the loaded system")
    elif set(workspace.roles) != set(workspace.summary.species):
        issues.append("choose a role for every species")
    if draft.analysis_type != "energy" and not draft.reference.strip():
        issues.append("choose the reference group")
    if draft.analysis_type in {"rdf", "cumulative_rdf"} and not draft.selection.strip():
        issues.append("choose the selection group")
    if draft.analysis_type == "energy":
        if not draft.energy_file.strip():
            issues.append("choose a GROMACS energy file")
        if not draft.energy_terms:
            issues.append("choose at least one energy term")
    if not draft.output.strip():
        issues.append("choose an export folder")
    return issues


def task_label(task: RadialTask) -> str:
    analysis = "RDF" if task.analysis_type == "rdf" else analysis_label(task.analysis_type)
    return (
        f"{analysis}: {task.reference} -> {task.selection} | "
        f"r max {task.r_max_nm:g} nm | bin {task.bin_width_nm:g} nm"
    )


def setup_panel(draft: AnalysisDraft, workspace: Workspace) -> str:
    issues = draft_issues(draft, workspace)
    status = "Ready to run" if not issues else "Incomplete: " + "; ".join(issues)
    summary = workspace.summary
    frames = draft.frames
    stop = "end" if frames.stop is None else str(frames.stop)
    selection_source = "index groups" if workspace.index_file else "selection expressions"
    role_count = len(workspace.roles)
    species_count = 0 if summary is None else len(summary.species)
    project = "none" if workspace.project is None else str(workspace.project.root)
    topology = _name(workspace.topology, "not loaded")
    trajectory = _name(workspace.trajectory, "not loaded")
    index = _name(workspace.index_file, "none")
    backend: str = draft.analysis_backend
    if backend == "mdanalysis":
        backend = "MDAnalysis"
    lines = [
        status,
        "",
        "[Files]",
        f"  Project:       {project}",
        f"  Topology:      {topology}",
        f"  Trajectory:    {trajectory}",
        f"  Index:         {index}",
        f"  Species roles: {role_count}/{species_count}",
        "",
        "[Analysis]",
        f"  Backend:       {backend}",
    ]
    if draft.analysis_type == "energy":
        lines.extend(
            (
                "",
                "[Energy]",
                f"  File:          {_name(draft.energy_file, 'not set')}",
                f"  Terms:         {', '.join(draft.energy_terms) or 'not set'}",
            )
        )
    else:
        lines.extend(
            (
                "",
                "[Groups]",
                f"  Source:        {selection_source}",
                f"  Reference:     {draft.reference or 'not set'}",
            )
        )
        lines.append(f"  Selection:     {draft.selection or 'not set'}")
        lines.extend(
            (
                "",
                "[Frames]",
                f"  Range:         {frames.start} to {stop} (exclusive), "
                f"every {frames.stride} frames",
                "",
                "[Parameters]",
            )
        )
        lines.extend(
            (
                f"  Maximum radius: {draft.r_max_nm:g} nm",
                f"  Bin width:     {draft.bin_width_nm:g} nm",
                "",
                "[Task Queue]",
            )
        )
        if draft.queue:
            lines.extend(
                f"  {number}. {task_label(task)}"
                for number, task in enumerate(draft.queue, 1)
            )
        else:
            lines.append("  Empty.")
    lines.extend(
        (
            "",
            "[Export]",
            f"  Folder:        {draft.output or 'not set'}",
            "  Figures:       PNG/SVG/PDF",
        )
    )
    if issues:
        lines.extend(("", "[Missing]"))
        lines.extend(f"  - {issue}" for issue in issues)
    return "\n".join(lines)


def result_text(result: AnalysisResult) -> str:
    return report_for(result).text()
