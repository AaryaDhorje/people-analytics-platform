"""Metric services, one module per domain.

Populated in phase 3, test-first, in this order: retention, acquisition,
engagement, productivity, then flight_risk.

Two rules apply to every function added here:

1. The formula comes from docs/METRICS.md verbatim. Never invent one.
2. Rate metrics divide by AVERAGE headcount for the period, never end-of-period
   headcount. This is the most common bug in HR analytics.
"""
