# RDF validation - method 1.0.0

[English](rdf-1.0.0.md) | [Simplified Chinese](rdf-1.0.0.zh-CN.md)

Tests generate a two-frame, four-atom periodic GRO system. Expected shell counts and volumes are
calculated independently and compared with every radius and `g(r)` sample. Overlapping selections
check ordered normalization and self exclusion. Generated inputs also cover the application, CLI,
GUI, project, and export paths.

Controlled GROMACS output checks command arguments, frame conversion, input preservation, and XVG
mapping. It does not provide an independent production-trajectory comparison.

The fixture checks counting and normalization. It does not establish convergence, uncertainty,
force-field validity, production performance, or agreement across GROMACS versions.
