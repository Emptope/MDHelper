# MDHelper 0.1.0 known limitations

[English](KNOWN_LIMITATIONS.md) | [Simplified Chinese](KNOWN_LIMITATIONS.zh-CN.md)

- RDF method 1.0.0 is defined for static atom selections in three-dimensional periodic
  bulk systems. It does not implement center-of-mass, slab, orientational, dynamic-selection,
  intermolecular-only, or site-exclusion RDF variants.
- Base RDF and cumulative RDF results are deterministic values over the selected frames. MDHelper
  0.1.0 does not estimate equilibration, autocorrelation time, statistical inefficiency,
  convergence, uncertainty, or effective sample size. Statistical analysis will require a
  separate, explicitly enabled workflow with auditable time series and convergence checks.
- First-minimum detection is an explainable diagnostic. It can be unavailable or low-confidence.
  Cumulative RDF reports the running value at that boundary for review, but the diagnostic does
  not alter the cumulative curve.
- Species roles are suggestions rather than chemical perception. Net-charge sign is used only
  when complete topology charges exist; neutral population dominance is low-confidence, and all
  roles require confirmation.
- Input identity is static: coordinate-dependent MDAnalysis selections are rejected.
- In-process trajectory-format support depends on the bundled MDAnalysis version; a newer TPR may
  require a compatible GRO/PDB topology snapshot. TNG is a GROMACS trajectory format but is not
  supported in MDHelper 0.1.0 because
  the current MDAnalysis/PyTNG reader does not reliably read valid GROMACS TNG output.
- GROMACS is optional. Auto can select a detected complete GROMACS pipeline after earlier complete
  candidates cannot load the input. Explicit `gromacs` RDF/cumulative RDF uses the installed
  `gmx trjconv` and
  `gmx rdf`, so numerical behavior can depend on that GROMACS version. Executable compatibility
  remains the user's responsibility after version/capability detection.
- Windows and Linux portable-archive smoke tests must pass in their release workflows. Their
  workflow definitions are not evidence of a successful target run.
- The bounded electrolyte regression dataset and hand-checkable generic system cover the
  release analyses. A second independently sourced production MD trajectory is still desired
  as additional validation evidence.

Observable-specific validation tolerances are published in the version-matched method and
validation documents under `docs/methods/` and `docs/validation/`.
