# Cumulative Number RDF - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [Simplified Chinese](cumulative-rdf-1.0.0.zh-CN.md)

Status: release method specification for MDHelper 0.1.0.

The serialized analysis type is `cumulative_rdf`, and the MDHelper CLI command is
`cumulative-rdf`. GROMACS 2026.3 documents that `gmx rdf -cn` produces the **cumulative number
RDF**, describes the output file as **Cumulative RDFs**, and uses `rdf_cn` as its default basename.
The GROMACS implementation sets the plot title to **Cumulative Number RDF** and the Y-axis label
to **number**. MDHelper uses those same user-facing terms.

## Quantity and applicability

For the in-process backend, fixed reference set A, selection set B, frame `f`, and requested width
`d`, let `H_fk` be the number of ordered non-self A-B pairs in `[k*d,(k+1)*d)`. These bins are
obtained by pairing the same half-width fine histogram used for RDF. The reported cumulative curve
at radius `(k+1)*d` is

```text
cumulative_number[k] = sum_f sum_{j <= k} H_fj / (number_of_frames * |A|).
```

For the bulk RDF normalization used by this method, the same quantity is

```text
cumulative_number(r) =
    4 * pi * rho_selection * integral_0^r g_reference,selection(r') * r'^2 dr'.
```

The cumulative number is the mean number of selection atoms within radius `r` of each reference
atom. A
selection atom with the same topology index as the reference atom is excluded. The result data
contains only `radius_nm` and `cumulative_number`. It does not calculate a fixed-cutoff time
series, per-reference counts, residue-grouped counts, or a count probability distribution.

The selection defines the counting basis and is always shown in the report. For example,
`Li-O_FSI` reports selected FSI oxygen contacts per selected Li atom. It is not the number of
distinct FSI anions unless the selection contains one representative atom per anion. MDHelper
does not silently convert atom contacts into molecule counts.

The cumulative analysis is explicit. RDF results contain only `g(r)`, and a cumulative RDF curve
is plotted only when the user runs or loads a `cumulative_rdf` result and enables it in the plot
selection.

## GROMACS backend

When `analysis_backend = gromacs`, the stored cumulative samples come directly from the `-cn` output of the
same `gmx rdf` run that produces the diagnostic RDF. MDHelper standardizes the XVG as
`radius_nm,cumulative_number`; it does not integrate `g(r)` or recompute pair counts. GROMACS owns
the cumulative definition, grid, PBC, and endpoints on this branch. Exact Python frame slicing,
selection syntax, and Integration provenance follow RDF method 1.0.0.

## Selection, frames, units, PBC, and grid

The in-process static selection contract, frame-range semantics, box validation, preprocessing
record, and triclinic minimum-image convention are identical to RDF method 1.0.0. The GROMACS
branch follows the corresponding GROMACS RDF rules. Distance is in nm and cumulative number is a
count.

The request records `reference`, `selection`, `r_max_nm`, and `bin_width_nm`. The in-process backend
creates `Q = round(2*r_max_nm/bin_width_nm)` half-width fine bins. The cumulative RDF contains
`floor(Q/2)` samples at `d,2d,...`; an unmatched final fine bin is omitted, matching
`gmx rdf -cn`. The requested width is preserved rather than adjusted to end at `r_max_nm`.
`r_max_nm` is validated against every selected frame's reliable minimum-image radius. Empty
selections, an all-self pair set, invalid boxes, invalid radial parameters, or a grid above one
million RDF samples fail with actionable errors.

## First-shell coordination reporting

The cumulative RDF is a nondecreasing running count. Its global minimum is normally the
zero-distance end, and its global maximum is normally the requested outer radius. Neither is, by
itself, a chemically meaningful shell coordination number. MDHelper therefore never summarizes
the curve using global extrema or the terminal value at `r_max_nm`.

The reported first-shell coordination follows the common electrolyte-simulation convention:

1. derive the RDF from the same pair histogram and normalization used by the cumulative run;
2. resolve the first prominent RDF peak and first following minimum with RDF method 1.0.0;
3. use that first-minimum radius as the first-shell boundary;
4. report `cumulative_number` at the first cumulative-RDF endpoint greater than or equal to that
   RDF radius as the `coordination_number`, together with the boundary and detection confidence.

This single value is a first-shell coordination number; the complete distance-dependent array
remains the cumulative number. If the RDF has no resolved following minimum, MDHelper reports
first-shell coordination as unavailable and retains the full curve. It does not substitute the
terminal value, an arbitrary slope threshold, or a hard-coded chemical cutoff. The diagnostic
requires user review and never changes the stored curve.

Pierini et al. report that running RDF integration numbers up to the first minimum give ligand
coordination numbers in the first Li solvation shell and use later plateaus as structural
evidence (Molecules 2025, DOI `10.3390/molecules30020230`). Mabrouk et al. report Li coordination
from the area under the first RDF peak and use the corresponding first minimum as the
coordination-distance threshold (Scientific Reports 2024, DOI
`10.1038/s41598-024-60063-0`).

## Deterministic result and statistical scope

For a fixed trajectory, selections, frame range, and numerical parameters, method 1.0.0 reports
the deterministic cumulative curve obtained from all selected frames. The base request has no
block-size parameter, and the result has no standard-error field or uncertainty band.

The base method does not estimate equilibration, autocorrelation, convergence, uncertainty, or
effective sample size. Any future statistical analysis must be separate and explicitly enabled,
start from an auditable time series, and leave the base cumulative curve unchanged.

## Plot composition and export

A standalone result uses distance in &Aring; on the X axis and **number** on the Y axis.
The plotted radius is converted from the stored `radius_nm` field. When explicit RDF and
cumulative results are both selected, their shared radial-distance domain allows one figure with
`g(r)` on the primary Y axis and the **Cumulative RDF** series on the secondary Y axis. The two Y
scales remain independent, while the automatic X range is the intersection of visible series
domains.

CSV export is `rdf_cn.csv` with `radius_nm` and `cumulative_number`. No uncertainty, probability, or
distribution column is produced. JSON and CSV exports use at most 15 significant decimal digits.
This formatting does not change the in-memory calculation.

## GROMACS terminology source

- [GROMACS 2026.3 `gmx rdf` manual](https://manual.gromacs.org/current/onlinehelp/gmx-rdf.html)
- [GROMACS `rdf.cpp` implementation](https://gitlab.com/gromacs/gromacs/-/blob/main/src/gromacs/trajectoryanalysis/modules/rdf.cpp)

## Validation contract

The automated contract uses a generated, hand-checkable periodic system. Every radius sample and
cumulative value is compared with an independently accumulated histogram. The GROMACS adapter is
tested separately at its controlled command boundary. See the version-matched validation report.
