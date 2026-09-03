# Versioned methods

[English](README.md) | [Simplified Chinese](README.zh-CN.md)

These documents are normative for MDHelper 0.1.0 analysis results. A result identifies its method by `analysis_type` and `method_version`; changing a definition that can change numbers requires a new method version. Presentation changes and performance changes that preserve the specified numbers do not.

| Analysis | Method specification | Validation report |
| --- | --- | --- |
| RDF | [rdf-1.0.0.md](rdf-1.0.0.md) | [rdf-1.0.0.md](../validation/rdf-1.0.0.md) |
| Cumulative Number RDF | [cumulative-rdf-1.0.0.md](cumulative-rdf-1.0.0.md) | [cumulative-rdf-1.0.0.md](../validation/cumulative-rdf-1.0.0.md) |

All methods store nm and ps. In-process trajectory methods use fixed atom identity, streaming
frames, and the shared [selection contract](../SELECTIONS.md). Explicit GROMACS RDF/cumulative RDF
follows `gmx rdf` selection and sampling rules described by the corresponding method sections;
the chosen backend is part of the result definition and provenance.

Base results are deterministic functions of the recorded trajectory, selections, frame range,
and method parameters. They do not include a fixed block size or a standard-error estimate.
Statistical analysis is outside the base methods and must be explicitly enabled if introduced.
