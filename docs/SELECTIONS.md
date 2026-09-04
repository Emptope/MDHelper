# Selections and species roles

[English](SELECTIONS.md) | [Simplified Chinese](SELECTIONS.zh-CN.md)

One backend owns selection syntax for a run. MDAnalysis uses NDX groups or static MDAnalysis
expressions. GROMACS uses NDX groups or native `gmx rdf` expressions. Results record the language
and source.

Topology and trajectory files must describe the same atoms in the same order. Equal atom counts do
not prove matching order. MDHelper does not infer file pairs from names.

## NDX groups

Pass an index file with `--index`, then use exact group names for `--reference` and `--selection`:

```text
[ Cations ]
1 8 15

[ Solvent oxygen ]
2 5 9 12
```

NDX atom numbers are one-based; MDHelper converts them to zero-based indices. Group names are
case-sensitive and unique. Semicolon comments and multiline atom lists are supported. Parsing
rejects data before a header, invalid or out-of-range numbers, duplicate groups or atoms, empty
selected groups, and files without groups.

In-process diagnostics record the group, parser version, count, ordered-index SHA-256, path, and
file SHA-256. GROMACS parses NDX itself; MDHelper records the group, path, and command.

## Expressions

Without NDX, `mdanalysis` uses the MDAnalysis 2.x selection language and `gromacs` passes expressions
to `gmx rdf -ref` and `-sel`. Auto uses the selected complete backend's parser.

| Selector | Meaning | Example |
| --- | --- | --- |
| `all` | All atoms | `all` |
| `name` | Atom name or pattern | `name O*` |
| `type` | Topology atom type | `type OW` |
| `element` | Element | `element O` |
| `resname` | Residue name | `resname SOL` |
| `resid` | Residue ID or range | `resid 10:20` |
| `index` | Zero-based atom index | `index 0 4 8` |
| `bynum` | One-based atom number | `bynum 1:10` |

Use `and`, `or`, `not`, and parentheses. Quote shell expressions. A missing topology attribute is an
error. Custom aliases such as `species` and `molecule` are unsupported.

RDF methods require fixed atom identity. MDAnalysis rejects `around`, `sphzone`, `sphlayer`,
`isolayer`, `cyzone`, `cylayer`, `point`, `prop`, and `same x/y/z as`. Dynamic selection requires a
separate method version.

## Species roles

`mdhelper inspect` groups species by topology residue identity and molecules by topology-derived
`molecule_id`. It recursively scans project `.itp` files and matches residue names to
`[ moleculetype ]` names. For loose input files, it scans from the trajectory directory.

The matching `[ atoms ]` charges are summed with decimal arithmetic. Values above `+1e-6 e`
suggest `cation`, values below `-1e-6 e` suggest `anion`, and values within that tolerance suggest
`solvent`. Parameter-only files are ignored. Missing definitions produce no suggestion; malformed,
duplicated, or preprocessor-dependent definitions are rejected instead of guessed. When every
species is matched, GUI inspection warns if the inferred system charge exceeds `1e-6 e`.

Suggestions are advisory and session-only. CLI accepts
`--roles '{LI: cation, SOL: solvent}'`; TUI and GUI allow review and changes. Only confirmed roles
are stored in requests and project manifests. Roles provide metadata only and do not create
selections, choose parameters, or change results.
