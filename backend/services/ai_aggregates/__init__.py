"""Domain aggregator helpers for AI endpoints.

Each domain has a small module that exposes pure async functions returning
minimal, AI-ready dicts. Implementation uses MongoDB aggregation pipelines
and strict projections to avoid over-fetching.

Files:
- finance_aggregates.py    : invoices, payments, monthly revenue rollup
- production_aggregates.py : WO/maklon/capacity
- wms_aggregates.py        : fabric rolls QC, CMT dispatches, opname variances
- hr_aggregates.py         : attendance, employee counts
- rahaza_aggregates.py     : WIP/QC/downtime/alerts for Rahaza ERP
"""
