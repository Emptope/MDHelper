# MDHelper algorithm specification

[English](ALGORITHM.md) | [Simplified Chinese](ALGORITHM.zh-CN.md)

This document defines implemented engineering behavior for MDHelper. The versioned
[method documents](methods/README.md) are normative for scientific quantities and formulas.

## Conventions

- Stored distance uses nm, time uses ps, and volume uses nm^3. Plots convert radial distance to
  angstrom.
- Backend adapters convert coordinates and boxes once. Core frames use NumPy `float64` arrays.
- Frame ranges use zero-based Python slicing: inclusive `start`, exclusive `stop`, and stride
  relative to `start`. `stop = null` means the trajectory end.
- Selections resolve once to ordered, zero-based atom indices.
- Coordinates are not unwrapped, reconstructed, aligned, or fitted.
- `FrameAudit` records processed frame indices, times, and count.

## Backend dispatch

```text
mdanalysis -> MDAnalysis loading + selection + frame handling + calculation
gromacs    -> GROMACS input + selection + frame handling + calculation
```

`auto` tries eligible complete backends in registry order. MDAnalysis precedes GROMACS. GROMACS
frame subsets also require `trjconv` and `check`. A loading failure may advance to the next complete
backend. Explicit selection does not fall back. Provenance records requested and resolved values.

The MDAnalysis adapter creates one Universe, preserves atom order, converts angstrom to nm, and
maps molecules to `segid:residue_name:residue_id`. Missing finite charges remain null. Missing
elements use an atom-name fallback without chemical inference.

## Selection

MDAnalysis uses `NdxSelectionEngine` when an index file exists and otherwise uses a static
MDAnalysis expression. Injected engines cannot be combined with an index file. GROMACS quotes NDX
groups and otherwise passes native expressions to `gmx rdf`.

NDX parsing preserves order, converts one-based numbers to zero-based indices, and rejects missing
headers, duplicate groups or atoms, empty selected groups, invalid tokens, and out-of-range values.
Group names are exact and case-sensitive.

MDAnalysis rejects coordinate-dependent expressions including `around`, `sphzone`, `sphlayer`,
`isolayer`, `cyzone`, `cylayer`, `point`, `prop`, and `same x/y/z as`.

In-process selection records contain the source, count, atom and residue names, language, and
parser version. NDX records also contain the path and file hash. GROMACS records the native
expression or group and command.

## Periodic geometry and radial grid

For a box matrix `H` with row vectors `a`, `b`, and `c`:

```text
V = abs(a dot (b cross c))
G = inverse(H)
h_i = 1 / norm(G[:, i])
r_limit = min(h_0, h_1, h_2) / 2
```

Volume must be finite and greater than `1e-12 nm^3`. Each frame requires
`r_max <= r_limit + max(1e-12, r_limit * 1e-10)`.

The in-process path uses MDAnalysis `capped_distance` with minimum-image distances from each
frame's full periodic-box parameters. It excludes pairs with the same topology index and retains
distances at the cutoff.

For requested width `d`:

```text
Q = max(1, round(2 * r_max / d))
B_rdf = floor((Q + 1) / 2)
B_cumulative = floor(Q / 2)
h = d / 2
```

RDF radii are `k*d`; cumulative radii are `(k+1)*d`. An unmatched final fine bin is omitted. The
requested width is not adjusted to end at `r_max`. Radii are rounded to 15 decimal places. RDF may
not exceed 1,000,000 samples.

## In-process radial calculations

For reference size `N_R`, selection size `N_S`, overlap `O`, and processed frames `F`, the possible
non-self pair count per frame is `N_R * N_S - O` and must be positive. Pair exclusions do not
change the RDF normalization denominator.

Let `H_(f,k)` be a resampled frame count and `dV_k` its shell volume:

```text
D_S = sum_f (N_S / V_f)
g_k = sum_f H_(f,k) / (N_R * dV_k * D_S)

N_ref_obs = F * N_R
cumulative_number[k] = sum_(j=0..k) H_j / N_ref_obs
```

RDF stores `radius_nm,g_r`. Cumulative RDF stores `radius_nm,cumulative_number`. The cumulative
curve counts selected atoms per reference atom; it does not convert contacts to molecule counts.

## GROMACS radial calculations

The default frame range passes original inputs to one `gmx rdf` call. RDF uses `-o`; cumulative RDF
adds `-cn` and retains RDF output for shell diagnostics. Non-default ranges use `gmx check` for the
frame count and one `gmx trjconv -fr` call for an exact XTC subset. The original topology remains
the `-s` input. `-dt` is not used because its sampling origin differs from Python slicing.

`bin_width_nm` and `r_max_nm` map to `-bin` and `-rmax`. GROMACS owns pair selection, PBC, endpoints,
normalization, and cumulative integration. MDHelper accepts finite two-column XVG with increasing
radii, maps it to the result contract, and records all commands. It does not recompute the curve.

## Diagnostics and suggestions

First-shell detection consumes a completed RDF without changing it. It requires 11 points, uses a
Savitzky-Golay window of at most 11, then finds the first eligible peak and following minimum.

```text
peak prominence floor = max(0.05, 0.05 * max(smoothed_rdf))
minimum prominence floor = max(0.02, peak_floor / 2)
```

The first eligible peak and its following minimum define the suggested boundary. Results without
both features are unavailable and add a warning. Every available boundary requires user
confirmation and does not change `r_max` or another result.

Species are grouped by residue name and molecule ID. Recursively discovered `.itp` files in the project
directory provide role evidence: `[ moleculetype ]` names are matched to residue names and the
seventh field of each `[ atoms ]` record is summed with decimal arithmetic. Net charge above
`+1e-6 e` suggests cation, below `-1e-6 e` suggests anion, and values within that roundoff tolerance
suggest solvent. A complete matching definition produces a role suggestion; a missing definition
does not. Suggestions require confirmation and may be changed; roles do not change selections or
parameters.

If every species is matched, the system charge is the sum of each molecular charge multiplied by
the detected molecule count. An absolute system charge above `1e-6 e` produces a user warning.

## Plot construction

- RDF plots `g_r` as `g(r)` against angstrom distance.
- Cumulative RDF plots `cumulative_number` as `Cumulative RDF` with Y label `number`.
- Energy plots each selected EDR term against ps.

Compatible radial series share the intersection of their X domains. RDF uses the primary axis and
cumulative RDF the secondary axis. Each Y axis starts at zero and uses finite values in the visible
X range. User limits override automatic bounds.

Residue-name colors use sorted diagnostic residue names. Fixed colors use stored IDs. Secondary
series use a darker dashed variant. Titles are trimmed, printable, single-line strings of at most
120 characters. Preview and export use the same appearance state and do not modify result arrays.

## Provenance and persistence

In-process inputs use SHA-256 in 4 MiB chunks. Direct GROMACS runs record resolved paths and commands
without a pre-run hash pass. Provenance records runtime versions, platform, byte order, backend
resolution, inputs, configuration source, roles, and parameter decisions.

Requests, results, manifests, and plot state use strict schema-1 parsing. Project relocation accepts
only content-identical inputs. Result commit validates request and input identity, stores integration
streams as fingerprinted files, writes and hashes the result, then atomically replaces the manifest.
If manifest commit fails, the new unindexed files are removed. Loading checks path containment,
hashes, identities, and schemas. JSON and TOML writes use same-directory temporary files and
`os.replace`.

## External tools, configuration, and jobs

Executable candidates are ordered by run override, configured path, configured search paths,
adapter environment paths, `PATH`, then adapter paths. Detection and execution use argument vectors,
restricted environments, captured output, timeouts, and `shell=False`. Cancellation and timeout
terminate the process group and preserve captured output in the run record.

`MDHELPER_CONFIG` overrides the colocated `config.toml`. Configuration is validated before atomic
replacement. Templates are read in path order as non-empty ASCII and reject duplicate
case-insensitive keys.

Jobs move from pending to running and then completed, failed, or cancelled. Cancellation points
exist at hash chunks, frame boundaries, and process polling. One frame's distance search can delay
cancellation.

## Complexity and change checks

| Operation | Worst-case time | Additional memory |
| --- | --- | --- |
| RDF and cumulative RDF | `O(F * N_R * N_S)` | `O(N_R + N_S + P + B)` |
| File hash | File size | 4 MiB |
| Plot model | Result points | Result points |

Algorithm changes must update affected methods, schemas, validation, tests, and documentation.
They must preserve or revise units, endpoints, PBC, self exclusion, selection identity, resource
bounds, cancellation, and provenance without filename, sample, species, test, or output special
cases.
