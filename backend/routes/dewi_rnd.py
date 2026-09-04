"""dewi_rnd — thin orchestrator.

Semua endpoint hidup di sub-modul; file ini hanya mengimport mereka
sehingga @router.get/@router.post decorator terdaftar di shared router.

Split dari monolith 1533 LOC → 7 modul ≤ 320 LOC masing-masing.
"""
from routes.dewi_rnd_shared import router  # noqa: F401  (re-exported for server.py)
import routes.dewi_rnd_styles    # noqa: F401
import routes.dewi_rnd_samples   # noqa: F401
import routes.dewi_rnd_materials  # noqa: F401
import routes.dewi_rnd_design    # noqa: F401
import routes.dewi_rnd_colors    # noqa: F401  (F1: warna multi fan-out + SKU kanonik)
import routes.dewi_rnd_sizes     # noqa: F401  (F2: size_list bebas per style)
import routes.dewi_rnd_size_mapping  # noqa: F401  (Padankan Ukuran → master produksi)
import routes.dewi_rnd_hpp       # noqa: F401
import routes.dewi_rnd_overview  # noqa: F401
import routes.dewi_rnd_techpack_import  # noqa: F401  (Excel V5 importer)
