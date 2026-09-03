# Cumulative Number RDF - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [Simplified Chinese](cumulative-rdf-1.0.0.zh-CN.md)

Status: released for MDHelper 0.1.0. The analysis type is `cumulative_rdf`; the CLI command is
`cumulative-rdf`.

## Definition

For fixed reference set A, selection set B, frame `f`, and requested width `d`, `H_fk` counts
ordered non-self A-B pairs in `[k*d,(k+1)*d)`. At radius `(k+1)*d`:

```text
cumulative_number[k] = sum_f sum_{j <= k} H_fj / (number_of_frames * |A|)
```

Under the matching bulk RDF normalization:

```text
cumulative_number(r) =
    4 * pi * rho_selection * integral_0^r g_reference,selection(r') * r'^2 dr'
```

The value is the mean selected-atom count within `r` per reference atom. It does not convert atom
contacts to molecule counts. Results contain `radius_nm,cumulative_number`; they do not contain a
fixed-cutoff time series, per-reference counts, grouped counts, or a probability distribution.

## Selection, frames, PBC, and grid

Selection, frame slicing, preprocessing, box validation, and minimum-image rules match
[RDF method 1.0.0](rdf-1.0.0.md). Distance uses nm and cumulative number is a count.

For `Q = round(2*r_max_nm/bin_width_nm)` half-width fine bins, the curve has `floor(Q/2)` samples at
`d,2d,...`. An unmatched final fine bin is omitted. The requested width is not adjusted to end at
`r_max_nm`. Invalid parameters, more than one million RDF samples, invalid boxes, empty selections,
and all-self pair sets fail.

## GROMACS backend

With `analysis_backend = gromacs`, stored samples come from `gmx rdf -cn`; the same run produces RDF
for shell diagnostics. MDHelper maps XVG to `radius_nm,cumulative_number` and does not integrate or
recompute it. GROMACS owns pair selection, PBC, grid, and endpoints on this branch. Frame handling
and provenance match RDF method 1.0.0.

The terminology follows [`gmx rdf`](https://manual.gromacs.org/current/onlinehelp/gmx-rdf.html):
the UI uses **Cumulative Number RDF**, the plotted quantity is **Cumulative RDF**, and the Y-axis
label is **number**.

## First-shell coordination

The terminal cumulative value is not a shell coordination number. MDHelper derives RDF from the
same in-process histogram or uses the GROMACS RDF output, finds the first peak and following
minimum, then reports the first cumulative sample at or beyond that radius as
`coordination_number`.

If no minimum is resolved, coordination is unavailable and the curve remains valid. The diagnostic
requires user confirmation and never changes the curve. The rule follows the first-minimum
coordination convention used in electrolyte analysis; see DOI `10.3390/molecules30020230` and
`10.1038/s41598-024-60063-0`.

## Output and statistics

Standalone plots convert radius to angstrom and use Y label `number`. CSV output is `rdf_cn.csv`
with `radius_nm,cumulative_number`. JSON and CSV use at most 15 significant digits.

Base results contain no block size, standard error, or uncertainty band. The method does not
estimate equilibration, autocorrelation, convergence, uncertainty, or effective sample size.

The [validation report](../validation/cumulative-rdf-1.0.0.md) defines automated coverage and
limits.
