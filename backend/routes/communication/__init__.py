"""
CV. Dewi Aditya ERP — Communication Hub sub-package.

This package splits the original monolithic `dewi_communication.py` (1141 LOC)
into per-aggregate sub-modules. The shared `router` and the `comm_manager`
WebSocket connection manager live in `_helpers.py` and are imported by each
sub-module to register endpoints.

Load order is enforced by the orchestrator `routes/dewi_communication.py`.
"""
