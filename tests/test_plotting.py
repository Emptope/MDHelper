from __future__ import annotations

from dataclasses import replace

import pytest
from matplotlib import pyplot as plt

from mdhelper.core.analysis import AnalysisResult, RadialRequest, analysis_label
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.plotting import (
    PLOT_SCHEMES,
    PlotAppearance,
    PlotLimits,
    PlotSelection,
    PlotState,
    draw_plot,
    result_plot,
    results_plot,
    results_plots,
)

plt.switch_backend("Agg")


def _result(reference: str = "A", selection: str = "B") -> AnalysisResult:
    request = RadialRequest(
        analysis_type="rdf",
        topology="topology",
        trajectory="trajectory",
        reference=reference,
        selection=selection,
    )
    return AnalysisResult(
        data={
            "radius_nm": [0.1, 0.2, 0.3],
            "g_r": [0.0, 2.0, 1.0],
        },
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )


def _cumulative_rdf_result() -> AnalysisResult:
    request = RadialRequest(
        analysis_type="cumulative_rdf",
        topology="topology",
        trajectory="trajectory",
        reference="A",
        selection="B",
    )
    return AnalysisResult(
        data={
            "radius_nm": [0.1, 0.2, 0.3],
            "cumulative_number": [0.0, 1.0, 2.0],
        },
        parameters={},
        units={},
        diagnostics={},
        provenance={},
        request=request.to_dict(),
    )


def test_results_plot_combines_selection_series_without_uncertainty() -> None:
    model = results_plot(
        (_result("A", "B"), _result("A", "C")),
        ("first shell", "second shell"),
    )

    assert [series.label for series in model.series] == [
        "first shell",
        "second shell",
    ]
    assert [series.quantity for series in model.series] == [
        "g(r)",
        "g(r)",
    ]
    assert model.series[0].y_error is None
    assert model.reference_y == 1.0
    assert model.series[0].x == (1.0, 2.0, 3.0)


def test_energy_terms_default_to_separate_plots_and_can_be_combined(
    energy_result: AnalysisResult,
) -> None:
    separate = results_plots((energy_result,))

    assert len(separate) == 3
    assert [model.series[0].label for model in separate] == [
        "Potential",
        "Temperature",
        "Pressure",
    ]
    assert [model.title for model in separate] == [
        "Energy Analysis: Potential",
        "Energy Analysis: Temperature",
        "Energy Analysis: Pressure",
    ]

    combined = results_plots(
        (energy_result, energy_result),
        ("Potential", "Temperature"),
        (0, 1),
        ("Potential", "Temperature"),
        ("group", "group"),
    )

    assert len(combined) == 1
    assert combined[0].title == "Energy Analysis"
    assert combined[0].source_indices == (0, 1)
    assert [series.label for series in combined[0].series] == [
        "Potential",
        "Temperature",
    ]


def test_results_plots_apply_custom_title_to_its_combined_plot() -> None:
    models = results_plots(
        (_result(), _cumulative_rdf_result()),
        titles=("Radial structure", None),
    )

    assert len(models) == 1
    assert models[0].title == "Radial structure"
    assert models[0].source_indices == (0, 1)
    with pytest.raises(ConfigurationError, match="titles must match"):
        results_plots((_result(),), titles=("First", "Second"))


def test_cumulative_rdf_plot_uses_coordination_number_labels() -> None:
    model = result_plot(_cumulative_rdf_result())

    assert model.y_label == "number"
    assert [series.quantity for series in model.series] == ["CN"]


def test_draw_plot_uses_selected_scheme_legend_and_user_limits() -> None:
    figure, axis = plt.subplots()
    try:
        draw_plot(
            axis,
            results_plot((_result(), _result("A", "C")), color_ids=(10, 1)),
            "fixed",
            PlotLimits(x_min=0.0, x_max=5.0, y_min=-0.1, y_max=3.0),
        )
        assert [scheme.key for scheme in PLOT_SCHEMES] == [
            "residue_name",
            "fixed",
        ]
        assert axis.lines[0].get_color() == "#40bfbf"
        assert axis.lines[1].get_color() == "#ff0000"
        assert axis.get_xlim() == pytest.approx((0.0, 5.0))
        assert axis.get_ylim() == pytest.approx((-0.1, 3.0))
        legend = axis.get_legend()
        assert legend is not None
        assert legend._loc == 2
        assert [text.get_text() for text in legend.get_texts()] == [
            "g(r) A-B",
            "g(r) A-C",
        ]
        assert legend.get_frame().get_boxstyle().__class__.__name__ == "Square"
        assert len(axis.get_figure().axes) == 1
        assert tuple(axis.lines[0].get_ydata()) == tuple(_result().data["g_r"])
        assert len(axis.collections) == 0
    finally:
        plt.close(figure)


def test_plot_appearance_round_trips_and_controls_rendering() -> None:
    appearance = PlotAppearance(
        legend_visible=True,
        legend_location="lower_right",
        grid_visible=False,
        line_width=3.2,
        title_font_size=18,
        label_font_size=13,
        tick_font_size=8,
        legend_font_size=7,
    )
    state = PlotState(appearance=appearance)
    raw = state.to_dict()

    assert "schema_version" not in raw
    assert PlotState.from_dict(raw) == state

    figure, axis = plt.subplots()
    try:
        draw_plot(axis, result_plot(_result()), appearance=appearance)

        assert axis.lines[0].get_linewidth() == pytest.approx(3.2)
        assert axis.title.get_fontsize() == pytest.approx(18.0)
        assert axis.xaxis.label.get_fontsize() == pytest.approx(13.0)
        assert axis.get_xticklabels()[0].get_fontsize() == pytest.approx(8.0)
        assert not any(line.get_visible() for line in axis.get_xgridlines())
        legend = axis.get_legend()
        assert legend is not None
        assert legend._loc == 4
        assert legend.get_texts()[0].get_fontsize() == pytest.approx(7.0)
    finally:
        plt.close(figure)


def test_plot_appearance_rejects_invalid_values() -> None:
    with pytest.raises(ConfigurationError, match="line width"):
        PlotAppearance(line_width=0.0).validate()

    raw = PlotAppearance().to_dict()
    raw["legend_location"] = "outside"
    with pytest.raises(ConfigurationError, match="legend location"):
        PlotAppearance.from_dict(raw)


def test_rdf_and_cumulative_rdf_are_combined_when_both_are_selected() -> None:
    models = results_plots((_result(), _cumulative_rdf_result()))

    assert len(models) == 1
    assert models[0].x_label == r"$r$ ($\mathrm{\AA}$)"
    assert models[0].y_label == r"$g(r)$"
    assert models[0].secondary_y_label == "number"
    assert [series.axis for series in models[0].series] == ["primary", "secondary"]
    figure = plt.figure()
    try:
        for index, model in enumerate(models, start=1):
            draw_plot(figure.add_subplot(len(models), 1, index), model)
        assert len(figure.axes) == 2
        assert [axis.get_title() for axis in figure.axes if axis.get_title()] == [
            f"RDF and {analysis_label('cumulative_rdf')}",
        ]
        assert figure.axes[0].get_xlim() == pytest.approx((0.0, 3.0))
        assert figure.axes[0].get_ylim()[0] == pytest.approx(0.0)
        assert figure.axes[1].get_ylim()[0] == pytest.approx(0.0)
        assert figure.axes[0].lines[0].get_color() == "#4040ff"
        assert figure.axes[1].lines[0].get_color() == "#202080"
        assert figure.axes[1].lines[0].get_linestyle() == "--"
    finally:
        plt.close(figure)


def test_rdf_and_cumulative_rdf_use_independent_y_limits() -> None:
    model = results_plots((_result(), _cumulative_rdf_result()))[0]
    figure, axis = plt.subplots()
    try:
        draw_plot(
            axis,
            model,
            limits=PlotLimits(
                x_min=0.0,
                x_max=5.0,
                y_min=-0.1,
                y_max=3.0,
                y2_min=-2.0,
                y2_max=8.0,
            ),
        )
        secondary = figure.axes[1]
        assert axis.get_xlim() == pytest.approx((0.0, 5.0))
        assert secondary.get_xlim() == pytest.approx((0.0, 5.0))
        assert axis.get_ylim() == pytest.approx((-0.1, 3.0))
        assert secondary.get_ylim() == pytest.approx((-2.0, 8.0))
        assert secondary.get_ylabel() == "number"
    finally:
        plt.close(figure)


def test_radial_auto_limits_ignore_data_outside_the_common_x_domain() -> None:
    cumulative = replace(
        _cumulative_rdf_result(),
        data={
            "radius_nm": [0.1, 0.2, 1.0],
            "cumulative_number": [0.0, 1.0, 1000.0],
        },
    )
    model = results_plots(
        (_result(), cumulative),
        ("RDF legend", "Cumulative legend"),
    )[0]
    figure, axis = plt.subplots()
    try:
        draw_plot(axis, model)

        secondary = figure.axes[1]
        assert axis.get_xlim() == pytest.approx((0.0, 3.0))
        assert tuple(secondary.lines[0].get_xdata()) == pytest.approx((1.0, 2.0))
        assert secondary.get_ylim()[1] < 2.0
        assert axis.lines[0].get_color() == "#4040ff"
        assert secondary.lines[0].get_color() == "#202080"
    finally:
        plt.close(figure)


def test_plot_limits_and_scheme_are_validated() -> None:
    with pytest.raises(ConfigurationError, match="X-axis minimum"):
        PlotLimits(x_min=2.0, x_max=1.0).validate()
    figure, axis = plt.subplots()
    try:
        with pytest.raises(ConfigurationError, match="Unknown plot color scheme"):
            draw_plot(axis, result_plot(_result()), "missing")
    finally:
        plt.close(figure)


def test_plot_state_round_trips_explicit_result_selections() -> None:
    state = PlotState(
        (
            PlotSelection("rdf-id", "RDF series", True, 10),
            PlotSelection("cumulative-id", "Cumulative series", False, 1),
            PlotSelection(
                "energy-id",
                "Potential",
                True,
                0,
                "Potential",
                "energy",
                "Energy comparison",
            ),
            PlotSelection(
                "energy-id",
                "Temperature",
                True,
                1,
                "Temperature",
                "energy",
                "Energy comparison",
            ),
        ),
        "fixed",
        PlotLimits(x_min=0.0, x_max=1.0),
    )

    assert PlotState.from_dict(state.to_dict()) == state
    with pytest.raises(ConfigurationError, match="duplicate"):
        PlotState((PlotSelection("same"), PlotSelection("same"))).validate()
    PlotState(
        (
            PlotSelection("same", series="Potential"),
            PlotSelection("same", series="Temperature"),
        )
    ).validate()


def test_plot_state_rejects_invalid_or_conflicting_titles() -> None:
    with pytest.raises(ConfigurationError, match="surrounding whitespace"):
        PlotSelection("rdf-id", title=" padded ").validate()
    with pytest.raises(ConfigurationError, match="cannot exceed"):
        PlotSelection("rdf-id", title="x" * 121).validate()
    with pytest.raises(ConfigurationError, match="must use one title"):
        PlotState(
            (
                PlotSelection("first", group="shared", title="First"),
                PlotSelection("second", group="shared", title="Second"),
            )
        ).validate()


@pytest.mark.parametrize(
    "scheme", ["atom_name", "paired", "classic", "accessible", "muted"]
)
def test_plot_state_rejects_unknown_coloring_scheme(scheme: str) -> None:
    raw = PlotState().to_dict()
    raw["scheme"] = scheme

    with pytest.raises(ConfigurationError, match="Unknown plot color scheme"):
        PlotState.from_dict(raw)


def test_category_coloring_uses_resolved_residue_names() -> None:
    first = replace(
        _result("A", "B"),
        diagnostics={
            "selection_resolution": {
                "selection": {"atom_names": ["O"], "residue_names": ["SOL"]}
            }
        },
    )
    second = replace(
        _result("A", "C"),
        diagnostics={
            "selection_resolution": {
                "selection": {"atom_names": ["O"], "residue_names": ["ION"]}
            }
        },
    )
    model = results_plot((first, second))
    figure, axis = plt.subplots()
    try:
        draw_plot(axis, model, "residue_name")
        assert [line.get_color() for line in axis.lines[:2]] == ["#4040ff", "#ff0000"]
    finally:
        plt.close(figure)


def test_plot_limits_reject_missing_secondary_axis_fields() -> None:
    with pytest.raises(ConfigurationError, match="missing or unknown"):
        PlotLimits.from_dict(
            {"x_min": 0.0, "x_max": 1.0, "y_min": -1.0, "y_max": 2.0}
        )
