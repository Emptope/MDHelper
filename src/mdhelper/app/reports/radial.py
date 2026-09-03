"""RDF and cumulative RDF result reports."""

from __future__ import annotations

from mdhelper.core.analysis import AnalysisRequest, RadialRequest
from mdhelper.core.errors import ConfigurationError
from mdhelper.core.units import ANGSTROM_SYMBOL, convert_distance

from .base import Report, ReportRows, number, scalar, series


class RadialReport(Report):
    @property
    def request(self) -> RadialRequest:
        request = AnalysisRequest.from_dict(self.result.request)
        if not isinstance(request, RadialRequest):
            raise ConfigurationError("A radial report requires a radial request.")
        return request

    def radial_configuration_rows(self) -> ReportRows:
        radii = series(self.result.data.get("radius_nm"))
        radius = scalar(self.result.parameters.get("r_max_nm"))
        if radius is None:
            radius = self.request.r_max_nm
        width = scalar(self.result.parameters.get("bin_width_nm"))
        if width is None:
            width = self.request.bin_width_nm
        rows = [
            ("Calculated distance range", f"0 to {_angstrom(radius)} {ANGSTROM_SYMBOL}"),
            ("Bin width", f"{_angstrom(width)} {ANGSTROM_SYMBOL}"),
            ("Data points", str(len(radii))),
            ("Frames analyzed", self.frame_count),
        ]
        if self.frame_range:
            rows.append(("Time range", self.frame_range))
        return tuple(rows)


class RdfReport(RadialReport):
    def result_rows(self) -> ReportRows:
        rows = [("Pair", f"{self.request.reference} - {self.request.selection}")]
        rows.extend(_curve_rows(self, "g_r", "g(r)"))
        rows.extend(_shell_rows(self.result.diagnostics.get("first_shell_suggestion")))
        return tuple(rows)

    def configuration_rows(self) -> ReportRows:
        return self.radial_configuration_rows()


class CumulativeRdfReport(RadialReport):
    def result_rows(self) -> ReportRows:
        rows = [("Pair", f"{self.request.reference} - {self.request.selection}")]
        rows.extend(
            _coordination_rows(self.result.diagnostics.get("first_shell_suggestion"))
        )
        return tuple(rows)

    def configuration_rows(self) -> ReportRows:
        return (
            ("Counting basis", "Selection atoms per reference atom"),
            *self.radial_configuration_rows(),
        )


def _curve_rows(
    report: Report,
    value_key: str,
    label: str,
) -> list[tuple[str, str]]:
    radii = series(report.result.data.get("radius_nm"))
    values = series(report.result.data.get(value_key))
    count = min(len(radii), len(values))
    if not count:
        return []
    high = max(range(count), key=values.__getitem__)
    return [(f"{label} maximum", _curve_value(radii, values, high))]


def _curve_value(
    radii: tuple[float, ...],
    values: tuple[float, ...],
    index: int,
) -> str:
    return f"{number(values[index])} at {_angstrom(radii[index])} {ANGSTROM_SYMBOL}"


def _shell_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, dict) or not value.get("available"):
        return []
    rows: list[tuple[str, str]] = []
    for label, radius_key, value_key in (
        ("First resolved peak", "first_peak_nm", "first_peak_g_r"),
        ("First resolved minimum", "first_minimum_nm", "first_minimum_g_r"),
    ):
        radius = scalar(value.get(radius_key))
        height = scalar(value.get(value_key))
        if radius is not None and height is not None:
            rows.append(
                (label, f"g(r) = {number(height)} at {_angstrom(radius)} {ANGSTROM_SYMBOL}")
            )
    return rows


def _coordination_rows(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, dict) or not value.get("available"):
        return [
            ("First-shell coordination number", "Unavailable"),
            ("First-shell cutoff", "No resolved RDF first minimum"),
        ]
    radius = scalar(value.get("first_minimum_nm"))
    coordination = scalar(value.get("coordination_number"))
    if radius is None or coordination is None:
        return [
            ("First-shell coordination number", "Unavailable"),
            ("First-shell cutoff", "Incomplete RDF shell diagnostic"),
        ]
    rows = [
        ("First-shell coordination number", number(coordination)),
        (
            "First-shell cutoff",
            f"{_angstrom(radius)} {ANGSTROM_SYMBOL} (first RDF minimum)",
        ),
    ]
    return rows


def _angstrom(value_nm: float) -> str:
    return number(convert_distance((value_nm,), "nm", "angstrom")[0])
