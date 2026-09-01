# Atom and group selection

[English](SELECTIONS.md) | [Simplified Chinese](SELECTIONS.zh-CN.md)

MDHelper 0.1.0 normally resolves each selection to a fixed, ordered tuple of zero-based atom
indices before trajectory streaming. The preferred source is a GROMACS `.ndx` group file. Without
one, built-in analyses use a static MDAnalysis expression. Explicit GROMACS RDF/CN instead passes
the request expression to `gmx rdf` as GROMACS selection syntax. Every route records its selection
language and source in the same result contract.

## Preferred: GROMACS index groups

Files created with tools such as `gmx make_ndx` can be passed with `--index`. Each analysis selection argument is then an exact group name, including spaces:

```text
[ Cations ]
1 8 15

[ Solvent oxygen ]
2 5 9 12
```

```bash
mdhelper analyze rdf \
  --topology topol.tpr --trajectory md.xtc --index index.ndx \
  --reference "Cations" --selection "Solvent oxygen" \
  --r-max 1.0 --bin-width 0.002 --output results/rdf
```

The `.ndx` format uses one-based atom numbers; MDHelper converts them to internal zero-based indices. Group names are case-sensitive and must be unique. Semicolon comments and atom lists spanning multiple lines are supported. MDHelper rejects data before the first header, non-integer or out-of-range atom numbers, duplicate group names, duplicate atoms within a group, a selected empty group, and a file with no groups. It does not silently deduplicate or clamp values.

The request field `index_file` records the file used. When it is non-null, `reference` and
`selection` are group names. Result diagnostics record the group,
parser version, resolved count, ordered-index SHA-256, canonical file path, and file SHA-256. The
index is also a fingerprinted project/provenance input so moving or changing it has the same
deterministic behavior as moving or changing topology and trajectory inputs.

After the topology, trajectory, and optional index files are selected, the GUI automatically loads
the parsed groups. RDF and Cumulative Coordination Number selections become group pickers.
Switching to the expression source restores free-form expression editors; switching back restores
the selected index groups.

## Expression syntax by backend

If no `.ndx` file can be supplied, omitting `--index` selects expression mode. `native`,
`mdanalysis`, and `auto` trajectory analyses use the MDAnalysis Atom Selection Language described
below. Explicit `gromacs` RDF/CN passes both expressions directly to GROMACS; use the syntax
accepted by the installed `gmx rdf -ref` and `-sel`.

The fallback uses the **MDAnalysis Atom Selection Language**. Common topology-stable selectors include:

| Selector | Meaning | Example |
| --- | --- | --- |
| `all` | Every atom | `all` |
| `name` | Atom name; shell-style patterns are accepted | `name O*` |
| `type` | Topology atom type | `type OW` |
| `element` | Chemical element | `element O` |
| `resname` | Residue/species name | `resname SOL` |
| `resid` | Topology residue ID; ranges are allowed | `resid 10:20` |
| `index` | Zero-based atom index | `index 0 4 8` |
| `bynum` | One-based atom serial number | `bynum 1:10` |

Boolean operators are `and`, `or`, and `not`; parentheses make precedence explicit:

```text
resname SOL and element O
(resname SOL or resname ADD) and name O*
resname ANI and not name C*
bynum 1:100
```

Quote expressions in a shell. Matching follows the declared MDAnalysis 2.x parser and available topology attributes. A missing attribute is an error; MDHelper does not invent charges, masses, molecule numbers, or bonds. Legacy custom aliases such as `species` and `molecule` are not supported.

## Static-identity restriction

Built-in RDF and cumulative RDF methods in 0.1.0 require fixed atom identity.
Coordinate-dependent MDAnalysis expressions are rejected, including:

```text
around, sphzone, sphlayer, isolayer, cyzone, cylayer, point, prop
same x as, same y as, same z as
```

Evaluating one of these expressions on a dummy or first frame would silently freeze a dynamic selection and change its meaning. Dynamic selections require a separately versioned per-frame method and are outside the 0.1.0 contract.
