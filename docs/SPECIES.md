# Species roles

[English](SPECIES.md) | [Simplified Chinese](SPECIES.zh-CN.md)

`mdhelper inspect` groups species by topology residue identity and molecules by topology-derived
`molecule_id`. Residue names do not imply chemical roles.

With complete charges, molecular net charges above `+0.25 e` suggest `cation`; values below
`-0.25 e` suggest `anion`. A unique most-populous neutral species gets a low-confidence `solvent`
suggestion. Missing charges, mixed signs, and tied neutral populations produce no suggestion.

Inspection reports method, evidence, confidence, candidates, reason, and confirmation status. CLI
accepts `--roles '{LI: cation, SOL: solvent}'`; TUI and GUI expose the same choices. Confirmed roles
are stored in `request.species_roles` and the project manifest. `mdhelper project set-roles` replaces
the project mapping. Allowed roles are `cation`, `anion`, `solvent`, `additive`, `polymer`,
`surface`, and `other`.

Roles provide metadata only. They do not create selections, choose parameters or algorithms, or
change results.
