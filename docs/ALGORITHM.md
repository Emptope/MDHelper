# MDHelper 0.1.0 algorithm specification

[English](ALGORITHM.md) | [Simplified Chinese](ALGORITHM.zh-CN.md)

This document describes the numerical and deterministic engineering algorithms implemented by
MDHelper 0.1.0. Package responsibilities are defined in [Architecture](ARCHITECTURE.md), released
method definitions in [methods](methods/README.md), and validation tolerances in
[validation](validation/).

Only implemented behavior is described. MDHelper does not infer an RDF cutoff, evaluate dynamic
selections, estimate statistical uncertainty, or cache analysis results.

## 1. Conventions

- Internal distance and coordinates use nm; time uses ps and volume uses nm^3.
- GRO coordinates are already in nm. MDAnalysis coordinates and box vectors are divided by 10.
- Core frames store coordinates as `float64` NumPy arrays. Readers perform format and unit
  conversion once at the backend boundary.
- Radial plots convert nm to angstrom; persisted arrays remain in nm.
- A frame range is zero-based and follows Python slicing: `start` is inclusive, `stop` is
  exclusive, and `stop = null` means the end of the trajectory. `stride` is relative to `start`.
- In-process selections are resolved once to fixed, ordered, zero-based atom-index tuples.
- Coordinates are not unwrapped, reconstructed, aligned, or fitted. Every pair uses the current
  frame's triclinic minimum image.

The following notation is used for radial calculations:

- `F`: number of frames actually processed;
- `R`: reference indices, with size `N_R`;
- `S`: selection indices, with size `N_S`;
- `O = |R intersect S|`: number of overlapping indices;
- `H_f`: the frame box matrix with box vectors stored as rows;
- `V_f = |det(H_f)|`: frame volume;
- `r_max`: requested maximum radial distance;
- `d_req`: requested maximum bin width.

`FrameAudit` records the actual first/last frame indices and times as well as `F`.

## 2. Trajectory reader dispatch

Reader selection is deterministic:

```text
native                         -> GroTrajectorySource
auto + GRO topology and GRO trajectory -> GroTrajectorySource
auto or mdanalysis             -> MDAnalysisTrajectorySource
gromacs                        -> GromacsTrajectorySource via Integrations
anything else                  -> error
```

`auto` does not retry with MDAnalysis after a native parse error. Provenance records the reader
that was actually used.

The native reader validates both paths and extensions, builds atom metadata from the topology's
first frame, scans the trajectory to count and validate frames, and then streams requested frames
during analysis. Atom identity at each index must remain constant. Three box values produce a
diagonal matrix; nine values are reordered according to the GRO format.

The MDAnalysis adapter creates one Universe, preserves its atom order, converts positions and
triclinic dimensions from angstrom to nm, and maps each molecule to
`segid:residue_name:residue_id`. Missing finite charges remain null. Missing elements use a small,
format-independent atom-name fallback; this is not chemical perception.

## 3. Selection resolution

Selection dispatch is:

```text
injected engine + index file -> error
index file                   -> NdxSelectionEngine
injected engine              -> that engine
otherwise                    -> MDAnalysisSelectionEngine
```

This dispatch applies to in-process analyses. Explicit GROMACS RDF/CN quotes an NDX group as
`group "name"`; without NDX it passes the request value directly as a GROMACS selection expression.

NDX parsing preserves group and atom order, converts one-based atom numbers to zero-based indices,
and rejects missing headers, duplicate groups, duplicate atoms, empty selected groups, non-integer
tokens, and out-of-range indices. Group names are exact and case-sensitive.

The MDAnalysis route supports topology-stable expressions. It rejects coordinate-dependent tokens
such as `around`, `sphzone`, `sphlayer`, `isolayer`, `cyzone`, `cylayer`, `point`, `prop`, and
`same x/y/z as`. The remaining expression is evaluated against a lightweight topology-only
Universe.

Every resolution record contains the original expression or group, count, an order-sensitive
SHA-256 of the index sequence, sorted atom/residue names, language and parser version, and, for
NDX, the index path and file SHA-256.

## 4. Periodic geometry and pair iteration

For row box vectors `a`, `b`, and `c`:

```text
V = abs(a dot (b cross c))
```

The volume must be finite and greater than `1e-12 nm^3`. For a triclinic box, the reliable radial
limit is half the shortest cell height:

```text
G = inverse(H)
h_i = 1 / norm(G[:, i])
r_limit = min(h_0, h_1, h_2) / 2
```

Every processed frame must satisfy
`r <= r_limit + max(1e-12, r_limit * 1e-10)`.

For a reference position `x_r` and selection position `x_s`, the minimum image is:

```text
delta = x_s - x_r
fractional = delta @ inverse(H)
fractional = fractional - rint(fractional)
delta_mic = fractional @ H
```

A pair is retained when its two atom indices differ and its squared distance is no greater than
the squared cutoff. Distinct atoms at identical coordinates remain valid pairs.

Pair matrices are bounded by `max_pairs_per_chunk`. Small searches and searches whose cutoff spans
most cells use direct selection and reference chunks. Larger local searches first assign both
selections to periodic fractional-coordinate cells. The reciprocal box vectors define a
conservative fractional cutoff on each axis, so only neighboring occupied cells can contain a
retained pair. Candidate blocks still use the triclinic minimum-image calculation above. This cell
pruning changes neither pair identity nor histogram order-independent results and avoids enumerating
the full `N_R * N_S` product when the cutoff is local.

The RDF/CN neighbor-search cutoff is exactly the request's user- or template-supplied `r_max`.
Cell pruning does not infer, reduce, or otherwise adjust this cutoff.

## 5. In-process radial grid

The in-process grid reproduces the half-width histogram and resampling used by `gmx rdf`. For
requested width `d`:

```text
Q = max(1, round(2 * r_max / d))
B_rdf = floor((Q + 1) / 2)
B_cn = floor(Q / 2)
h = d / 2
```

`Q` is the number of fine bins of width `h`. RDF sample `k` is reported at `k*d`. Its first shell
is `[0, d/2)`; later shells are `[(k-1/2)d, (k+1/2)d)`. The shell volume is

```text
dV_0 = (4 * pi / 3) * (d/2)^3
dV_k = (4 * pi / 3) * ((k+1/2)^3 - (k-1/2)^3) * d^3, k > 0
```

CN sample `k` is reported at `(k+1)*d` and combines fine bins `2k` and `2k+1`. A final unmatched
fine bin is omitted by the relevant resampling, just as in GROMACS. The requested width is not
adjusted to make the final sample land on `r_max`. Reported radii are rounded to 15 decimal places
for stable serialization, and the RDF sample count may not exceed 1,000,000.

## 6. In-process radial distribution function

RDF uses ordered reference-selection pairs. The possible non-self pair count per frame is

```text
N_pair = N_R * N_S - O
```

and must be positive. This count is a validity check and diagnostic; following GROMACS, exclusions
do not reduce the RDF normalization from `N_R*N_S` to `N_pair`. For each selected frame, MDHelper
validates `r_max` and accumulates the fine pair histogram. Fine bins are then resampled into RDF
counts `H_(f,k)`. Define

```text
D_S = sum_f (N_S / V_f)
```

The final curve is

```text
H_k = sum_f H_(f,k)
g_k = H_k / (N_R * dV_k * D_S)
```

This is algebraically the GROMACS sequence of averaging raw frame counts, dividing by the average
number of reference positions, shell volume, and average selection number density. The persisted
arrays are `radius_nm` and `g_r`.

## 7. In-process cumulative RDF

The GROMACS-style cumulative number RDF resamples the same fine pair histogram into width-`d`
intervals `[k*d, (k+1)*d)` without the RDF ideal-gas normalization. With
`N_ref_obs = F * N_R`:

```text
N_k = (sum_(j=0..k) H_j) / N_ref_obs
```

`N_k` is reported at radius `(k+1)*d` and is the mean number of selection particles inside that
upper edge around one reference particle. This is the discrete form corresponding to

```text
N(r) = 4 * pi * rho_selection * integral_0^r g_ref,selection(r') * r'^2 dr'
```

The result field is `cumulative_number`; the analysis identifier is `cumulative_rdf`. The UI calls
the curve **Cumulative Coordination Number (CN)** and labels its Y axis **Coordination number**.
A single value evaluated at a shell boundary is a first-shell `coordination_number` diagnostic,
not the name of the complete distance-dependent array.

### GROMACS RDF/CN backend

An explicit `gromacs` request does not use the formulas above as its curve source. The application
uses a built-in reader for metadata and frame bounds, then invokes `gmx rdf` once with both `-o`
and `-cn`. Full, single-frame, and contiguous ranges pass the original topology and trajectory
directly, with no time filter or exact `-b`/`-e` bounds. A strided Python range is written as an exact
temporary XTC subset by translating its zero-based frame indices to the one-based NDX entries
accepted by `gmx trjconv -fr`. The original topology remains the `gmx rdf -s` input. GROMACS
`-dt` is not used because it samples an absolute time grid rather than a stride relative to `start`.

The request's `bin_width_nm` and `r_max_nm` are passed as `-bin` and `-rmax`. GROMACS owns pair
selection, PBC, grid endpoints, RDF normalization, and cumulative integration on this branch.
MDHelper requires two finite numeric XVG columns with strictly increasing radii, maps them to
`radius_nm` plus `g_r` or `cumulative_number`, applies the common first-shell diagnostic, and
records both conversion and `rdf` Integration runs when conversion is required. It does not
recompute or replace either curve.

## 8. First-shell diagnostic

The diagnostic consumes the finished RDF and never modifies RDF or cumulative RDF values. It:

1. requires at least 11 points and finite data;
2. replaces non-finite values by zero for detection only;
3. applies a Savitzky-Golay window of at most 11 points;
4. finds the first eligible prominent peak;
5. finds the first sufficiently prominent minimum after that peak.

Peak prominence is `max(0.05, 0.05 * max(smoothed_rdf))`; minimum prominence is
`max(0.02, peak_prominence / 2)`. Confidence is high for a peak-to-minimum contrast at least 0.5,
medium for at least 0.2, and low otherwise. Every available boundary requires user confirmation.
An unavailable or low-confidence result produces a warning but does not select a cutoff.

## 9. Species-role suggestions

Species are grouped by residue name and molecules by `molecule_id`; no residue-name special cases
exist. With complete charges, molecular net charges above `+0.25 e` suggest cation and values below
`-0.25 e` suggest anion. Consistently neutral species are candidates; only a unique most-populous
neutral species receives a low-confidence solvent suggestion. Missing, mixed, or tied evidence is
reported as unavailable. Confirmation metadata never changes selections or numerical parameters.

## 10. Plot construction

- RDF plots `g_r` as `g(r)` against angstrom distance.
- Cumulative RDF plots `cumulative_number` as `N(r)` with Y label `Coordination number`.
- Energy plots each explicitly selected EDR term against time in ps.

RDF and cumulative RDF share the `radial_distance` domain. If both are selected, RDF uses the
primary axis and cumulative RDF the secondary axis. Residue-name coloring uses the resolved
selection residue names; fixed coloring uses a stored color ID. Secondary-axis lines use
a darker version of the related color and a dashed line.

A non-empty persisted title overrides the generated title of its grouped plot. GUI title edits are
copied to every currently visible source series in that plot. If grouping later joins independently
titled series, the first non-empty title in input order is deterministic. Titles are single-line,
trimmed, printable strings of at most 120 characters; an empty title restores generated naming.

For compatible radial series, the automatic X range is their domain intersection. Automatic
primary and secondary Y ranges are calculated independently from finite points visible in the
current X range and start at zero. Explicit user limits override corresponding automatic bounds.

## 11. Provenance and project persistence

Input files are SHA-256 hashed in 4 MiB chunks. Provenance records package/runtime versions,
platform, byte order, actual reader, input paths and hashes, configuration source, role decisions,
and parameter decisions.

Project manifests, nested requests, plot state, and results use strict schema-1 parsing. Unknown
or missing fields fail; 0.1.0 does not migrate development-era request names or plot states.
Project input relocation is accepted only when the content hash is unchanged.

Result commit validates the embedded request, input fingerprints, IDs, and paths; writes one full
result under `results/data/`; hashes that file; and then atomically commits the manifest. If manifest
commit fails, the new unindexed file is removed.
Every manifest result entry requires that hash. Loading checks path containment, file existence,
content identity, and the strict result contract in that order.
JSON and TOML atomic writes use a same-directory temporary file and `os.replace`.

## 12. External tools, configuration, and tasks

External executable candidates are ordered by per-run override, configured executable, configured
search paths, adapter environment candidates, `PATH`, then adapter candidate paths. Identity and
capabilities are detected with an argument vector, restricted environment, timeout, captured output,
and `shell=False`. Execution records argv, cwd, environment summary, logs, timing, status, exit code,
and requested output fingerprints.

Configuration selection honors an explicit `MDHELPER_CONFIG` and otherwise uses `config.toml`
next to the executable. Saved TOML is validated before atomic replacement. Templates are discovered in stable
path order, decoded as non-empty ASCII, and rejected on duplicate case-insensitive keys.

Background tasks move through pending, running, and a terminal state. Cancellation is cooperative
at file-hash chunks, analysis-frame boundaries, and external-process polling. Pair chunking bounds
memory but does not itself guarantee cancellation latency within a very large frame.

## 13. Complexity and change checks

| Operation | Worst-case time | Main additional memory |
| --- | --- | --- |
| RDF/cumulative RDF | worst-case `O(F * N_R * N_S)`; local cells reduce candidates | `O(N_R + N_S + M + B)` |
| Native GRO scan | `O(F * N_atoms)` | one frame |
| File fingerprint | input bytes | 4 MiB |

Any algorithm change must preserve or explicitly revise formulas, units, endpoint inclusion,
triclinic PBC, self exclusion, selection identity, resource bounds, cancellation points,
provenance, method version, schemas, method documents, validation evidence, and tests. It must not
special-case a filename, sample, species, software name, or expected test value.
