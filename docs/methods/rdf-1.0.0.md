# Radial distribution function — method 1.0.0

[English](rdf-1.0.0.md) | [Simplified Chinese](rdf-1.0.0.zh-CN.md)

Status: release method specification for MDHelper 0.1.0.

## Quantity and applicability

For the in-process backend, fixed reference set A and selection set B, frame `f`, and periodic cell
volume `V_f`, RDF sample `k` is centered at `k*d`, where `d` is the requested bin width. The first
shell is `[0,d/2)` and later shells are `[(k-1/2)d,(k+1/2)d)`. MDHelper counts ordered pairs
`(i,j)` where `i` is in A, `j` is in B, `i != j`, and the minimum-image distance lies in that shell.
Let `H_fk` be that count and `Delta V_k` the exact shell volume. The reported curve is

```text
g_k = sum_f H_fk / (|A| Delta V_k sum_f (|B| / V_f)).
```

This is the default `gmx rdf -norm rdf` normalization: average raw counts are divided by the
average number of reference positions, shell volume, and average selection number density. Pair
order matters only when the selected sets differ; self pairs are excluded by topology atom index,
but, as in GROMACS, exclusions do not change the normalization from `|A||B|` to
`|A||B|-|A intersection B|`. No smoothing is applied to stored, exported, or plotted `g(r)`.
Reports, JSON, CSV, and plots retain the direct full-frame curve. Cumulative RDF is a separate,
explicit analysis and is never added to an RDF result or plot implicitly. The method is applicable to
three-dimensional periodic bulk trajectories with a valid box on every processed frame. It does
not define slab, non-periodic, orientational, center-of-mass, site-exclusion, or
intermolecular-only RDFs.

## Selection, frames, units, and PBC

MDAnalysis uses exact NDX names when supplied and otherwise accepts static MDAnalysis expressions.
GROMACS RDF uses exact NDX names or, without NDX, explicit GROMACS selection expressions. Frame
sampling always follows Python slicing: `start` is an inclusive zero-based index, `stop` is
exclusive, and `stride` is applied relative to `start`.

Coordinates and radii are nm; `g(r)` is dimensionless. Displacements use the triclinic cell vectors and minimum-image fractional wrapping. `r_max_nm` must not exceed half the smallest perpendicular cell height on any processed frame, because spherical-shell normalization beyond that radius is ambiguous under this convention. A missing, singular, or zero-volume box is an error.

Coordinates are consumed as stored after backend unit conversion to nm. Method 1.0.0 performs no
trajectory unwrapping, centering, fitting, or alignment; it applies the minimum-image convention to
each pair displacement in each frame. Results record the first/last selected frame indices and
times as well as this preprocessing record.

The request follows the `gmx rdf` interface and records `bin_width_nm`, not a bin count. The
in-process backend first creates `round(2*r_max_nm/bin_width_nm)` bins of half the requested width,
then applies the same two resamplings as GROMACS. RDF radii are `0,d,2d,...`; the RDF sample count
is `floor((Q+1)/2)` for `Q` fine bins. The requested width is preserved and is not adjusted to put
the final shell on `r_max_nm`. A final fine half-bin not consumed by RDF resampling is omitted.
Fine bins are left-closed and right-open; a distance on the fine histogram's final edge is not
included.

## GROMACS backend

When `analysis_backend = gromacs`, stored `g(r)` samples come directly from `gmx rdf`. MDHelper passes
`-bin`, `-rmax`, `-ref`, `-sel`, `-o`, and optional `-n`, without requesting `-cn`, then standardizes
the RDF XVG as `radius_nm,g_r`. The in-process grid, shell resampling, and
normalization follow the same default GROMACS definitions; GROMACS still owns its PBC and floating
point implementation on the external branch. MDHelper preserves zero-based frame slicing:
the default full range reads the original inputs directly, while non-default ranges use one exact
converted subset rather than `gmx rdf -dt`. Every non-default range first obtains the frame count
with `gmx check`. Integration arguments,
executable identity, version, outputs, and frame audit are retained in provenance. MDHelper does
not recompute the GROMACS curve. MDAnalysis in-process values can differ below practical tolerance
from serialized XVG values because GROMACS versions use finite output precision.

## Parameters

The request must record `r_max_nm`, `bin_width_nm`, frame range, `analysis_backend`, and complete selection source. CLI/GUI defaults (`1.0 nm`, `0.002 nm`) are visible convenience defaults, not inferred physical facts. Invalid radii or widths, a grid above one million bins, empty selections, or a pair set containing only self pairs fail.

`r_max_nm`, bin width, and stride are explicit user choices. MDHelper does not infer or recommend an RDF maximum radius. The in-process backend validates every frame against its reliable minimum-image radius; the GROMACS backend delegates radial validity to `gmx rdf`. Neither path silently adjusts the request.

The first-shell suggestion is diagnostic and never silently changes another analysis. Method 1.0.0:

1. replaces non-finite curve values with zero for suggestion processing only;
2. applies a Savitzky–Golay filter with the largest odd window no greater than 11 (minimum 5) and polynomial order up to 3;
3. finds the first peak after the filter half-window with prominence at least `max(0.05, 0.05 max(g_smooth))`;
4. finds the first following minimum separated by at least one intervening bin, with prominence at least `max(0.02, peak_prominence_floor/2)`;
5. labels confidence high for smoothed peak-minus-minimum contrast at least 0.5, medium for at least 0.2, otherwise low.

The suggestion records peak/minimum values, method, diagnostics, confidence, and `requires_user_confirmation = true`. If no peak or following minimum is resolved, `available = false`, a reason and warning are returned, and no arbitrary cutoff is substituted.

JSON and CSV exports use at most 15 significant decimal digits. This preserves precision well beyond the validation tolerance while removing decimal text that only reflects binary floating-point representation, for example serializing the intended radial coordinate `0.009` instead of `0.009000000000000001`. The float64 calculation itself is unchanged.

## Deterministic result and statistical scope

For a fixed trajectory, selections, frame range, and numerical parameters, method 1.0.0 reports the deterministic curve obtained from all selected frames. The base request has no block-size parameter, and the result has no standard-error field or uncertainty band.

Method 1.0.0 does not estimate equilibration, autocorrelation time, statistical inefficiency, convergence, uncertainty, or effective sample size. A future statistical analysis must be separate and explicitly enabled. It must first produce an auditable observable time series, then evaluate equilibration, autocorrelation, and block-size convergence; it must not replace or alter the base RDF curve.

## Validation contract

The automated contract uses a generated, hand-checkable periodic system. Expected shell counts
and volumes are assembled independently and compared with `pytest.approx`; overlapping selections
also verify ordered-pair normalization and self exclusion. See the version-matched validation
report for coverage and limits.
