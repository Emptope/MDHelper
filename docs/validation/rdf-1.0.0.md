# Radial distribution function validation - method 1.0.0

[English](rdf-1.0.0.md) | [Simplified Chinese](rdf-1.0.0.zh-CN.md)

## Reference system

The automated suite builds a two-frame, four-atom periodic GRO system in a temporary directory.
Its coordinates, box, selections, frame range, and histogram edges are explicit in the test. No
external trajectory or stored reference curve is required.

## Checks

The expected shell counts and exact shell volumes are assembled independently from the reported
curve. Radius samples and normalized `g(r)` values are compared with `pytest.approx`. A separate
case uses overlapping reference and selection sets to verify ordered-pair normalization and self
exclusion. Application, CLI, project persistence, export, and GUI paths also run against generated
GRO inputs.

The GROMACS adapter is tested at the command boundary with controlled output, including frame
range conversion and input preservation. These checks validate MDHelper's adapter behavior; they
do not claim an independent production-trajectory comparison.

## Limits

The self-contained numerical fixture is deliberately small and orthorhombic. It does not establish
scientific convergence, uncertainty, force-field validity, or agreement across GROMACS versions.
Those remain user responsibilities for each scientific dataset.
