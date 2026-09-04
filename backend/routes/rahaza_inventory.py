"""rahaza_inventory — thin orchestrator.

Split dari monolith 1307 LOC → 6 modul:
- rahaza_inventory_shared.py    : router, constants, utility helpers
- rahaza_inventory_materials.py : Materials CRUD
- rahaza_inventory_stock.py     : Stock, Movement Ledger, Ops (receive/transfer/adjust)
- rahaza_inventory_issues.py    : Material Issues CRUD + approval workflow
- rahaza_inventory_workflow.py  : MI legacy confirm + post-to-gl + cancel + delete
- rahaza_inventory_fg.py        : FG Movements + FG Issues
"""
from routes.rahaza_inventory_shared import router  # noqa: F401  re-exported
import routes.rahaza_inventory_materials  # noqa: F401
import routes.rahaza_inventory_thresholds # noqa: F401  Ambang stok (W3)
import routes.rahaza_inventory_stock      # noqa: F401
import routes.rahaza_inventory_issues     # noqa: F401
import routes.rahaza_inventory_workflow   # noqa: F401
import routes.rahaza_inventory_fg         # noqa: F401
