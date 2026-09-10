# MDHelper algorithm notes

[English](ALGORITHM.md) | [简体中文](ALGORITHM.zh-CN.md)

Scientific definitions, normalization, endpoints, and limitations live in the versioned [RDF](methods/rdf-1.0.0.md) and [cumulative RDF](methods/cumulative-rdf-1.0.0.md) methods. This document covers implementation decisions not defined there.

## Backend dispatch

`auto` tries complete eligible backends in registry order: MDAnalysis, then GROMACS. A loading failure may advance to the next attempt; explicit selection does not fall back. Provenance records both requested and resolved backends. One backend owns loading, selection, frames, and calculation.

MDAnalysis preserves atom order, converts coordinates and boxes from angstrom to nm once, and uses NumPy `float64` core frames. Molecule IDs are `segid:residue_name:residue_id`; missing finite charges remain null. Missing elements use atom names without chemical inference. Selection syntax, NDX validation, and advisory species roles are defined in [Selections](SELECTIONS.md).

## Periodic geometry and grid

For a box matrix `H` whose rows are cell vectors:

```text
V = abs(det(H))
h_i = 1 / norm(inverse(H)[:, i])
r_limit = min(h_i) / 2
```

Require finite `V > 1e-12 nm^3` and `r_max <= r_limit + max(1e-12, r_limit * 1e-10)` on every processed frame. MDAnalysis `capped_distance` supplies minimum-image distances using the full box. Equal topology indices are excluded; distances at the cutoff are retained.

The fine grid uses `Q = max(1, round(2*r_max/bin_width))` half-width bins. Resampling follows the versioned methods; radii are rounded to 15 decimal places. RDF is limited to one million samples. `FrameAudit` records processed indices, times, and count.

GROMACS supplies its own curves. Non-default frame ranges require `check` and `trjconv -fr`, not `rdf -dt`; XVG must contain finite, increasing radii and two columns. MDHelper does not recompute GROMACS normalization or cumulative integration.

## First-shell diagnostics

Detection consumes a copy of the completed RDF, never changing the curve. It requires 11 points and a Savitzky-Golay window of at most 11, then finds the first eligible peak and following minimum:

```text
peak prominence floor = max(0.05, 0.05 * max(smoothed_rdf))
minimum prominence floor = max(0.02, peak_floor / 2)
```

Without both features, the boundary is unavailable and a warning is added. Available boundaries require user confirmation and never change `r_max`. Cumulative coordination uses the first sample at or beyond the boundary, as defined by the cumulative method.

## Plotting and provenance

Radial plots convert nm to angstrom; energy plots use ps. Compatible radial series share the intersection of their X domains, with RDF on the primary axis and cumulative RDF on the secondary. Automatic Y bounds use finite visible values and start at zero; explicit limits override them. Residue colors use sorted names, fixed colors use stored IDs, and secondary curves are darker and dashed. Titles are printable, single-line, and at most 120 characters. Plotting never changes arrays.

In-process inputs use SHA-256 in 4 MiB chunks. Direct GROMACS runs record paths and commands without a pre-run hash pass. Provenance includes versions, platform, byte order, inputs, backend resolution, configuration source, roles, and parameter decisions. Storage, job cancellation, and process boundaries are described in [Architecture](ARCHITECTURE.md).

Worst-case radial time is `O(F * N_R * N_S)` with additional memory `O(N_R + N_S + P + B)` for frames, reference/selection atoms, returned pairs, and bins. One distance search can delay cancellation. Algorithm changes must update affected method versions, validation, schemas, and regressions; do not introduce sample-specific or output-specific exceptions.
