"""
CV. Dewi Aditya — Returns/Refunds (DEPRECATED)
===============================================

REMOVED (P1.D Phase C, 2026-05-23):
  All 12 endpoints (returns + reviews CRUD) deleted. Frontend migrated to
  marketing namespace:
    /api/dewi/toko/returns/*  →  /api/marketing/returns/*
    /api/dewi/toko/reviews/*  →  /api/marketing/reviews/*

This file is kept as a placeholder so the router registration in server.py
remains valid. Empty router exposes ZERO endpoints (safe to remove from
server.py later if desired, but kept for back-compat with import order).
"""
from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

# Empty router — endpoints removed after Phase B cutover.
router = APIRouter(prefix='/api/dewi/toko', tags=['Dewi-Toko-Returns-Deprecated'])
