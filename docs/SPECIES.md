# Species recognition and role confirmation

[English](SPECIES.md) | [Simplified Chinese](SPECIES.zh-CN.md)

MDHelper 0.1.0 recognizes species from topology residue identity and counts distinct
topology-derived molecule identifiers. Recognition is descriptive: it does not silently assign a
chemical role from a residue name.

`mdhelper inspect` returns a versioned system summary with one explainable role suggestion per
species. When complete per-atom topology charges are available, consistently positive molecular
net charges suggest `cation` and consistently negative charges suggest `anion`; the stated
absolute tolerance is `0.25 e`. Of the consistently neutral species, a unique most-populous
component receives a low-confidence `solvent` suggestion. Population alone cannot distinguish a
solvent from an additive or another neutral component, so the evidence and ambiguity are shown.
Missing charges, mixed molecular charge signs, and tied neutral populations produce an unavailable
suggestion with candidate roles and a reason instead of a guessed value.

Every suggestion has a method, evidence, confidence, candidate roles, a reason, and
`requires_user_confirmation = true`. The CLI user confirms roles with a structured
`--roles '{LI: cation, SOL: solvent}'` mapping. The GUI shows the same suggestions, requires
confirmation, and keeps
every role editable. Interactive accepted and overridden decisions enter request parameter
provenance, and every frontend receives a normalized decision record in result provenance.
Confirmed roles are stored in the project manifest; `mdhelper project set-roles` can replace that
mapping without changing machine-local configuration.

Roles have one deliberately narrow effect: they preserve descriptive chemical context in project
metadata, analysis provenance, and later result interpretation. They never generate or replace an
atom selection, choose a cutoff or radial grid, select an algorithm, or alter a numerical result.
`inspect` publishes this policy together with definitions for every allowed role so CLI, TUI, and
GUI users see the same contract. During an analysis, every supplied role is paired with the current
topology-derived suggestion and recorded as accepted, overridden, or confirmed without an
available suggestion. This makes direct CLI requests as auditable as interactive confirmation.

The GUI exposes suggestion evidence in a full review dialog rather than a transient tooltip. Batch
application still asks for confirmation and only fills available suggestions; unavailable or
ambiguous species remain unset until the user chooses a role explicitly. TUI review presents the
same method and reason before confirmation.
