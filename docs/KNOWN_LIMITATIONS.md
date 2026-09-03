# MDHelper 0.1.0 known limitations

[English](KNOWN_LIMITATIONS.md) | [Simplified Chinese](KNOWN_LIMITATIONS.zh-CN.md)

- RDF supports static atom selections in three-dimensional periodic bulk systems. It excludes
  center-of-mass, slab, orientational, dynamic, intermolecular-only, and site-exclusion variants.
- RDF methods do not estimate equilibration, autocorrelation, convergence, uncertainty, or
  effective sample size.
- First-shell detection can be unavailable or low-confidence and never changes a curve.
- Species roles require confirmation and do not perform chemical perception.
- In-process format support follows the bundled MDAnalysis version. TNG is unsupported in 0.1.0.
- GROMACS is optional. Its version can affect external-backend results after capability detection.
- Release workflow definitions do not prove that target-platform smoke tests passed.
- Current validation lacks a second independently sourced production trajectory.

Method-specific scope and checks are in [methods](methods/README.md) and [validation](validation/).
