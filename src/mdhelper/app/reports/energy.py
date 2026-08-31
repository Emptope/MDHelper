"""GROMACS energy result report."""

from __future__ import annotations

from .base import Report, ReportRows, number, series


class EnergyReport(Report):
    def result_rows(self) -> ReportRows:
        rows: list[tuple[str, str]] = []
        raw_series = self.result.data.get("series")
        if isinstance(raw_series, dict):
            for name, values in raw_series.items():
                values_series = series(values)
                if values_series:
                    rows.append(
                        (
                            str(name),
                            f"{number(min(values_series))} to "
                            f"{number(max(values_series))}",
                        )
                    )
        return tuple(rows)

    def configuration_rows(self) -> ReportRows:
        return (
            ("Energy file", self.request.energy_file or ""),
            ("Terms", ", ".join(self.request.energy_terms)),
            ("Samples", str(self.result.diagnostics.get("n_samples", "unknown"))),
        )
