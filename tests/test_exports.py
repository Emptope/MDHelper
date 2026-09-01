from __future__ import annotations

from pathlib import Path

import pytest

import mdhelper.app.exports as exports_module
from mdhelper.app.exports import export_bundle, plot_exports, save_plots
from mdhelper.core.analysis import (
    AnalysisResult,
    AnalysisType,
    EnergyRequest,
    RadialRequest,
)
from mdhelper.core.plotting import PlotLimits, PlotModel, PlotSize, results_plots


def _radial_result(
    analysis_type: AnalysisType,
    reference: str,
    selection: str,
    analysis_id: str,
) -> AnalysisResult:
    request = RadialRequest(
        analysis_type=analysis_type,
        topology="topology",
        trajectory="trajectory",
        reference=reference,
        selection=selection,
    )
    data = (
        {"radius_nm": [0.1, 0.2], "g_r": [0.0, 1.0]}
        if analysis_type == "rdf"
        else {"radius_nm": [0.1, 0.2], "cumulative_number": [0.0, 2.0]}
    )
    return AnalysisResult(
        analysis_type=analysis_type,
        data=data,
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
        analysis_id=analysis_id,
    )


def _energy_result(term: str, unit: str, analysis_id: str) -> AnalysisResult:
    request = EnergyRequest(
        analysis_type="energy",
        energy_file="energy.edr",
        energy_terms=(term,),
    )
    return AnalysisResult(
        analysis_type="energy",
        data={"time_ps": [0.0, 1.0], "series": {term: [1.0, 2.0]}},
        parameters={},
        units={"time_ps": "ps", "series": unit},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
        analysis_id=analysis_id,
    )


def _two_combined_plots() -> tuple:
    results = (
        _radial_result("rdf", "LI", "O_FSI", "rdf-fsi"),
        _radial_result("cumulative_rdf", "LI", "O_FSI", "cn-fsi"),
        _radial_result("rdf", "LI", "O_DME", "rdf-dme"),
        _radial_result("cumulative_rdf", "LI", "O_DME", "cn-dme"),
    )
    models = results_plots(
        results,
        group_ids=("fsi", "fsi", "dme", "dme"),
    )
    return plot_exports(results, models=models)


@pytest.mark.parametrize(
    ("analysis_type", "expected"),
    (("rdf", "rdf-LI-O_FSI"), ("cumulative_rdf", "cn-LI-O_FSI")),
)
def test_plot_export_names_standalone_radial_pair(
    analysis_type: AnalysisType,
    expected: str,
) -> None:
    result = _radial_result(analysis_type, "LI", "O_FSI", analysis_type)

    assert plot_exports((result,))[0].name == expected


def test_plot_export_uses_one_canonical_name_for_combined_rdf_cn() -> None:
    assert tuple(plot.name for plot in _two_combined_plots()) == (
        "rdf-cn",
        "rdf-cn",
    )


def test_plot_export_uses_fixed_name_for_combined_energy_terms() -> None:
    results = (
        _energy_result("Total Energy", "kJ/mol", "total"),
        _energy_result("Temperature", "K", "temperature"),
    )

    combined = plot_exports(results, group_ids=("shared", "shared"))
    standalone = plot_exports((results[0],))

    assert combined[0].name == "energy"
    assert standalone[0].name == "energy-Total-Energy"


@pytest.mark.parametrize(
    ("analysis_type", "name"),
    (("rdf", "rdf"), ("cumulative_rdf", "cn")),
)
def test_plot_export_uses_fixed_name_for_combined_radial_series(
    analysis_type: AnalysisType,
    name: str,
) -> None:
    results = (
        _radial_result(analysis_type, "LI", "O_FSI", f"{name}-fsi"),
        _radial_result(analysis_type, "LI", "O_DME", f"{name}-dme"),
    )

    combined = plot_exports(results)
    standalone = plot_exports((results[0],))

    assert combined[0].name == name
    assert standalone[0].name == f"{name}-LI-O_FSI"


def test_save_plots_numbers_every_combined_analysis_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    plots = {
        "rdf": plot_exports(
            (
                _radial_result("rdf", "LI", "O_FSI", "rdf-fsi"),
                _radial_result("rdf", "LI", "O_DME", "rdf-dme"),
            )
        ),
        "cn": plot_exports(
            (
                _radial_result("cumulative_rdf", "LI", "O_FSI", "cn-fsi"),
                _radial_result("cumulative_rdf", "LI", "O_DME", "cn-dme"),
            )
        ),
        "energy": plot_exports(
            (
                _energy_result("Total Energy", "kJ/mol", "total"),
                _energy_result("Temperature", "K", "temperature"),
            ),
            group_ids=("shared", "shared"),
        ),
    }
    for name in plots:
        (tmp_path / f"{name}.svg").write_text("existing", encoding="ascii")

    def fake_export(
        _model: PlotModel,
        output: str | Path,
        stem: str,
        _scheme: str,
        _limits: PlotLimits | None,
        _size: PlotSize | None,
    ) -> list[Path]:
        path = Path(output) / f"{stem}.png"
        path.touch()
        calls.append(stem)
        return [path]

    monkeypatch.setattr(exports_module, "export_plot_model", fake_export)

    for plan in plots.values():
        save_plots(plan, tmp_path)

    assert calls == ["rdf-2", "cn-2", "energy-2"]


def test_save_plots_increments_combined_names_across_batch_and_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    (tmp_path / "rdf-cn.svg").write_text("existing", encoding="ascii")

    def fake_export(
        _model: PlotModel,
        output: str | Path,
        stem: str,
        _scheme: str,
        _limits: PlotLimits | None,
        _size: PlotSize | None,
    ) -> list[Path]:
        path = Path(output) / f"{stem}.png"
        path.touch()
        calls.append(stem)
        return [path]

    monkeypatch.setattr(exports_module, "export_plot_model", fake_export)
    plots = _two_combined_plots()

    save_plots(plots, tmp_path)
    save_plots(plots, tmp_path)

    assert calls == ["rdf-cn-2", "rdf-cn-3", "rdf-cn-4", "rdf-cn-5"]


def test_export_bundle_rebuilds_standalone_radial_plots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    rdf = _radial_result("rdf", "LI", "O_FSI", "rdf")
    cn = _radial_result("cumulative_rdf", "LI", "O_FSI", "cn")
    plans = plot_exports(
        (rdf, cn),
        labels=("RDF label", "CN label"),
        color_ids=(2, 3),
        titles=("Pair comparison", "Pair comparison"),
    )
    exported: list[tuple[Path, str, PlotModel, PlotLimits | None, PlotSize | None]] = []

    def fake_result(
        _result: AnalysisResult,
        output: str | Path,
        *,
        include_figures: bool,
    ) -> list[Path]:
        assert not include_figures
        path = Path(output)
        path.mkdir(parents=True)
        return [path / "result.json"]

    def fake_plot(
        model: PlotModel,
        output: str | Path,
        stem: str,
        _scheme: str,
        limits: PlotLimits | None,
        size: PlotSize | None,
    ) -> list[Path]:
        exported.append((Path(output), stem, model, limits, size))
        return [Path(output) / f"{stem}.png"]

    monkeypatch.setattr(exports_module, "export_result", fake_result)
    monkeypatch.setattr(exports_module, "export_plot_model", fake_plot)
    limits = PlotLimits(1.0, 6.0, 0.0, 4.0, 0.5, 8.0)
    size = PlotSize(7.0, 5.0)

    export_bundle(plans, tmp_path, limits=limits, sizes=(size,))

    assert [(output.name, stem) for output, stem, *_rest in exported] == [
        ("rdf-LI-O_FSI", "rdf-LI-O_FSI"),
        ("cn-LI-O_FSI", "cn-LI-O_FSI"),
    ]
    rdf_export, cn_export = exported
    assert [series.quantity for series in rdf_export[2].series] == ["g(r)"]
    assert [series.quantity for series in cn_export[2].series] == ["N(r)"]
    assert {series.axis for series in rdf_export[2].series} == {"primary"}
    assert {series.axis for series in cn_export[2].series} == {"primary"}
    assert rdf_export[2].title == "Pair comparison"
    assert cn_export[2].title == "Pair comparison"
    assert rdf_export[2].series[0].color_id == 2
    assert cn_export[2].series[0].color_id == 3
    assert rdf_export[3] == PlotLimits(1.0, 6.0, 0.0, 4.0)
    assert cn_export[3] == PlotLimits(1.0, 6.0, 0.5, 8.0)
    assert rdf_export[4] == size
    assert cn_export[4] == size


def test_export_bundle_maps_limits_by_source_axis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    temperature = _energy_result("Temperature", "K", "temperature")
    pressure = _energy_result("Pressure", "bar", "pressure")
    plans = plot_exports(
        (temperature, pressure),
        group_ids=("shared", "shared"),
    )
    exported_limits: list[PlotLimits | None] = []

    def fake_result(
        _result: AnalysisResult,
        output: str | Path,
        *,
        include_figures: bool,
    ) -> list[Path]:
        assert not include_figures
        path = Path(output)
        path.mkdir(parents=True)
        return [path / "result.json"]

    def fake_plot(
        _model: PlotModel,
        output: str | Path,
        stem: str,
        _scheme: str,
        limits: PlotLimits | None,
        _size: PlotSize | None,
    ) -> list[Path]:
        exported_limits.append(limits)
        return [Path(output) / f"{stem}.png"]

    monkeypatch.setattr(exports_module, "export_result", fake_result)
    monkeypatch.setattr(exports_module, "export_plot_model", fake_plot)
    limits = PlotLimits(0.0, 1.0, 10.0, 20.0, 30.0, 40.0)

    assert [series.axis for series in plans[0].model.series] == [
        "primary",
        "secondary",
    ]
    assert plans[0].source_axes == ("primary", "secondary")
    assert [series.quantity for series in plans[0].model.series] == ["", ""]

    export_bundle(plans, tmp_path, limits=limits)

    assert exported_limits == [
        PlotLimits(0.0, 1.0, 10.0, 20.0),
        PlotLimits(0.0, 1.0, 30.0, 40.0),
    ]
