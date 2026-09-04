# Versioned methods

[English](README.md) | [Simplified Chinese](README.zh-CN.md)

Results identify a method by the request's `analysis_type` and the result's `method_version`.
A numerical definition change requires a new method version. Presentation and equivalent
performance changes do not.

| Analysis | Method | Validation |
| --- | --- | --- |
| RDF | [1.0.0](rdf-1.0.0.md) | [Report](../validation/rdf-1.0.0.md) |
| Cumulative Number RDF | [1.0.0](cumulative-rdf-1.0.0.md) | [Report](../validation/cumulative-rdf-1.0.0.md) |

Methods store nm and ps, use fixed atom identity, and report deterministic values over selected
frames. They do not include uncertainty estimates.
