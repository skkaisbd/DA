"""Shared service layer (thin, modular).

Folders:
- ai/             : LLM client + prompt templates + response cache
- ai_aggregates/  : Domain-specific MongoDB aggregation helpers (small modules)

Rule: each file <= ~600 LOC. Routes stay thin; logic lives here.
"""
