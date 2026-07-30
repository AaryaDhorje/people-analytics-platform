"""Synthetic data generation. Populated in phase 2 by the data-generator subagent.

- scenarios.py  the six planted signals, as explicit data
- generate.py   builds the warehouse from those scenarios plus volume targets

Seeded randomness only: random.seed(42) and numpy.random.default_rng(42). The
database is regenerated repeatedly during the build, and non-deterministic data
breaks the hand-computed test fixtures.
"""
