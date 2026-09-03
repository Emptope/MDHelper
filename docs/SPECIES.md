# Species roles

[English](SPECIES.md) | [Simplified Chinese](SPECIES.zh-CN.md)

`mdhelper inspect` groups species by topology residue identity and molecules by topology-derived
`molecule_id`. It recursively scans `.itp` files inside the project directory and matches each
topology residue name to a `[ moleculetype ]` name. For loose input files, the trajectory directory
is used because it is also the automatic project location.

The charge column in the matching `[ atoms ]` section is summed with decimal arithmetic. Values
above `+1e-6 e` suggest `cation`, values below `-1e-6 e` suggest `anion`, and values within that
roundoff tolerance suggest `solvent`. Parameter-only `.itp` files are ignored. Missing definitions
produce no suggestion; malformed, duplicated, or preprocessor-dependent molecule definitions are
rejected instead of guessed.

When every detected species has a matching molecule definition, inspection multiplies each
molecular charge by its molecule count and sums the terms. GUI inspection warns when the absolute
system charge exceeds `1e-6 e`. The check remains unavailable when any definition is missing.

Inspection reports the source file, molecular charge, confidence, reason, and
confirmation status. Automatic detection is advisory: CLI accepts
`--roles '{LI: cation, SOL: solvent}'`, and TUI and GUI allow every suggestion to be reviewed and changed.
Suggestions remain in the current inspection session and are not written to a schema. Only
confirmed roles are stored in `request.species_roles` and the project manifest. `mdhelper project
set-roles` replaces the project mapping. Allowed roles are `cation`, `anion`, and `solvent`.

Roles provide metadata only. They do not create selections, choose parameters or algorithms, or
change results.
