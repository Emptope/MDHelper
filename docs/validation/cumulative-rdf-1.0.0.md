# Cumulative RDF validation - method 1.0.0

[English](cumulative-rdf-1.0.0.md) | [Simplified Chinese](cumulative-rdf-1.0.0.zh-CN.md)

## Reference system

The automated suite uses the same generated two-frame periodic GRO system as the RDF validation.
No external MD directory or stored XVG curve participates.

## Checks

The expected per-bin pair counts are written explicitly and accumulated with NumPy. Every radius
sample and cumulative number is compared with the analysis result. The suite also checks backend
neutrality, frame slicing, project persistence, CSV/JSON export, plotting, and the CLI and GUI
paths using generated inputs.

The GROMACS command adapter is covered with controlled process output. This verifies argument
construction and serialized curve handling without treating one external program run as a stored
truth source.

## Limits

The fixture checks deterministic counting and integration behavior, not convergence, statistical
uncertainty, chemical interpretation, or production-scale performance.
