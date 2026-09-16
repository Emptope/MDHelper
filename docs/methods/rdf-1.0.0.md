# Radial distribution function - method 1.0.0

[English](rdf-1.0.0.md) | [简体中文](rdf-1.0.0.zh-CN.md)

## Definition

For fixed reference set A, selection set B, frame `f`, and requested bin width `d`, sample `k` is centered at `k*d`. Its shell is `[0,d/2)` for `k = 0` and `[(k-1/2)d,(k+1/2)d)` otherwise. `H_fk` counts ordered A-B pairs in that shell after excluding equal topology indices. With frame volume `V_f` and shell volume `Delta V_k`:

```text
Delta V_0 = (4*pi/3) * (d/2)^3
Delta V_k = (4*pi/3) * [((k+1/2)d)^3 - ((k-1/2)d)^3], k > 0
g_k = sum_f H_fk / (|A| Delta V_k sum_f (|B| / V_f))
```

This matches default `gmx rdf -norm rdf` normalization. Self exclusions do not replace `|A||B|` with `|A||B|-|A intersection B|` in the denominator. Stored and exported `g(r)` is not smoothed.

The method applies to atom-based RDFs in three-dimensional periodic bulk trajectories. It excludes slab, non-periodic, orientational, center-of-mass, site-exclusion, intermolecular-only, and dynamic selection variants.

## Selection, frames, and PBC

MDAnalysis uses NDX groups or static MDAnalysis expressions. GROMACS uses NDX groups or native expressions. Frame ranges use zero-based Python slicing with inclusive `start`, exclusive `stop`, and stride relative to `start`.

Coordinates and radii use nm; `g(r)` is dimensionless. Pair distances use the minimum image for each frame's periodic box. `r_max_nm` must not exceed half the smallest perpendicular cell height on any processed frame. A missing, singular, or zero-volume box is invalid. Coordinates are not unwrapped, centered, fitted, or aligned.

## Grid

For `Q = round(2*r_max_nm/bin_width_nm)` half-width fine bins, RDF produces `floor((Q+1)/2)` samples at `0,d,2d,...`. Fine bins are left-closed and right-open. An unmatched final fine bin is omitted. The requested width is not adjusted to end at `r_max_nm`.

The request records selections, input source, `r_max_nm`, `bin_width_nm`, frame range, and backend. Invalid parameters, more than one million samples, empty selections, and all-self pair sets fail. CLI and GUI defaults of `1.0 nm` and `0.002 nm` are input defaults, not physical inference.

## GROMACS backend

With `analysis_backend = gromacs`, `gmx rdf` supplies the stored curve. MDHelper passes `-bin`, `-rmax`, `-ref`, `-sel`, `-o`, and optional `-n`, then maps XVG to `radius_nm,g_r`. It does not pass `-cn` or recompute the curve.

The full frame range uses original inputs. Other ranges use `gmx check` and one exact subset from `gmx trjconv -fr`; `gmx rdf -dt` is not used. Provenance records commands, executable identity, version, outputs, and frames. XVG precision can produce small differences from in-process values. Original XVG text is retained before temporary-file cleanup and exported as `rdf.xvg` alongside, not inside, the stdout `.out` and stderr `.err` logs. Project reload verifies the archived outputs with SHA-256.

## Diagnostic and output

First-shell diagnostic revision 2 uses a smoothed RDF copy to locate candidates, then resolves the first prominent peak and following minimum on the original samples. Filter artifacts without a matching raw extremum are rejected. An unresolved boundary is unavailable. Diagnostics never change the curve or `r_max_nm`. [Algorithm](../ALGORITHM.md) defines the detection rules.

JSON and CSV preserve the parsed floating-point values without additional rounding. Base results contain no block size, standard error, or uncertainty band. The method does not estimate equilibration, autocorrelation, convergence, or effective sample size.

The [validation report](../validation/rdf-1.0.0.md) defines automated coverage and limits.
