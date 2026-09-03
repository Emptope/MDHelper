# Cumulative RDF validation - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [Simplified Chinese](cumulative-rdf-1.0.0.zh-CN.md)

Tests use the generated two-frame periodic GRO system from RDF validation. Expected bin counts are
accumulated independently and compared with every radius and cumulative-number sample. Generated
inputs also cover frame slicing, application, CLI, GUI, project, plotting, and export paths.

Controlled GROMACS output checks command arguments and XVG mapping. It does not serve as stored
reference data.

The fixture checks counting and accumulation. It does not establish convergence, uncertainty,
chemical interpretation, or production performance.
