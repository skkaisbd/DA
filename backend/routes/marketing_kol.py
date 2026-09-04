"""marketing_kol — thin orchestrator.

Split dari monolith 1298 LOC → 5 modul:
- marketing_kol_shared.py   : router, constants, Pydantic models, helper functions
- marketing_kol_portal.py   : Creator Portal endpoints
- marketing_kol_creators.py : Admin KOL Creator CRUD
- marketing_kol_ops.py      : Sessions, Requests, Catalog, FG Products, Leaderboard, Seed
"""
from routes.marketing_kol_shared import router  # noqa: F401  re-exported
import routes.marketing_kol_portal    # noqa: F401
import routes.marketing_kol_creators  # noqa: F401
import routes.marketing_kol_ops       # noqa: F401
