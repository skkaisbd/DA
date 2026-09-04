"""
Fabric costing from Tech Pack `fabric_consumption` (+ `fabrics`) and material prices.

Shared by:
  - RnD HPP Calculator (#1)  → auto fabric cost per pcs (per size)
  - RnD Pola & Marking (#3a) → auto fabric usage & fabric HPP per pcs

meters_per_pcs = (length_cm / 100) / yield_pcs   (length is fabric length that yields
`yield_pcs` pieces at the given width). Fallback to length/100 if yield missing.

Price resolution order per fabric name (2026-08-02: SADAR SATUAN):
  1. dewi_rnd_materials.material_name (case-insensitive) → price_per_unit/price_per_meter
  2. dewi_rnd_materials.material_code (== name upper)     → idem
  3. rahaza_materials.name (case-insensitive)             → unit_cost (per SATUAN DASAR)
Unresolved → price 0 + source 'unresolved' (UI prompts to set price in Riset Material).

CATATAN PENTING: konsumsi kain dihitung dalam METER, sedangkan `rahaza_materials.unit_cost`
adalah harga per satuan dasar material — untuk kain rajut satuan dasarnya biasanya **kg**.
Dulu harga per kg dipakai langsung sebagai harga per meter (biaya kain salah besar).
Sekarang harga per kg dikonversi ke harga per meter memakai gramasi (gsm) & lebar (cm)
material, atau kemasan/uoms yang terdaftar; bila datanya belum ada, harga TIDAK dipakai
dan sumbernya dilaporkan `needs_gsm_width` supaya RnD melengkapi datanya.
"""
import re

from core import bom_uom


def _num(v, d=0.0):
    try:
        if v is None or v == "":
            return float(d)
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _price_per_meter_from_base(material: dict, price_base: float):
    """Ubah harga per satuan dasar material → harga per METER.

    Return (price_per_meter, note). price_per_meter None bila tak bisa dikonversi.
    """
    base = bom_uom.norm_unit(material.get("base_uom") or material.get("unit") or "")
    if not base or price_base <= 0:
        return None, "no_price"
    if base in ("m", "meter", "mtr"):
        return price_base, ""
    # 1 meter = `factor` satuan dasar → harga/meter = factor × harga/satuan dasar
    factor, _base, status, _note = bom_uom.line_factor(material, "m")
    if status in ("uom", "global", "fabric") and factor:
        return price_base * factor, status
    return None, "needs_gsm_width"


async def resolve_fabric_price(db, name: str):
    name = (name or "").strip()
    if not name:
        return 0.0, "empty"
    rx = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
    for query, src in ((({"material_name": rx}), "rnd_material"),
                       (({"material_code": name.upper()}), "rnd_material_code")):
        m = await db.dewi_rnd_materials.find_one(query, {"_id": 0})
        if not m:
            continue
        price = _num(m.get("price_per_unit") or m.get("price_per_meter"))
        unit = bom_uom.norm_unit(m.get("price_unit") or m.get("unit") or "m")
        if price <= 0:
            continue
        if unit in ("m", "meter", "mtr"):
            return price, src
        # Harga RnD dinyatakan dalam satuan lain (mis. per kg) → coba konversi ke meter
        mat = await db.rahaza_materials.find_one({"name": rx, "type": {"$ne": "fg"}}, {"_id": 0}) or {}
        gf = bom_uom.global_factor("m", unit)
        if gf:
            return price * gf, f"{src}_converted"
        conv, _n = _price_per_meter_from_base({**mat, "base_uom": unit}, price)
        if conv:
            return conv, f"{src}_converted"
        return 0.0, f"{src}_needs_conversion"

    r = await db.rahaza_materials.find_one({"name": rx, "type": {"$ne": "fg"}}, {"_id": 0})
    if r and _num(r.get("unit_cost")) > 0:
        conv, note = _price_per_meter_from_base(r, _num(r.get("unit_cost")))
        if conv:
            base = bom_uom.norm_unit(r.get("base_uom") or r.get("unit") or "")
            return conv, "rahaza_material" if base in ("m", "meter") else "rahaza_material_converted"
        # Harga per kg tanpa gramasi/lebar → JANGAN dipakai sebagai harga per meter.
        return 0.0, "rahaza_material_needs_gsm_width"
    return 0.0, "unresolved"


async def compute_fabric_cost(db, techpack: dict, size: str = None) -> dict:
    """Return per-size fabric cost breakdown derived from a tech pack."""
    fabrics = techpack.get("fabrics") or []
    consumption = techpack.get("fabric_consumption") or []

    priced, role_price, role_name = [], {}, {}
    for fb in fabrics:
        price, src = await resolve_fabric_price(db, fb.get("name"))
        role = fb.get("role", "main")
        priced.append({"name": fb.get("name"), "role": role, "price_per_meter": price, "price_source": src})
        # keep the FIRST price per role
        role_price.setdefault(role, price)
        role_name.setdefault(role, fb.get("name"))

    def price_for(role):
        return role_price.get(role, role_price.get("main", 0.0))

    def name_for(role):
        return role_name.get(role, role_name.get("main", ""))

    def source_for(role):
        return next((p["price_source"] for p in priced if p["role"] == role), "unresolved")

    sizes = {}
    for e in consumption:
        sz = (e.get("size") or "ALLSIZE")
        role = e.get("fabric_role", "main")
        length = _num(e.get("length_cm"))
        yld = _num(e.get("yield_pcs"))
        meters = (length / 100.0) / yld if yld > 0 else (length / 100.0)
        price = price_for(role)
        cost = meters * price
        s = sizes.setdefault(sz, {"size": sz, "entries": [], "meters_per_pcs": 0.0, "fabric_cost_per_pcs": 0.0})
        s["entries"].append({
            "fabric_role": role,
            "fabric_name": name_for(role),
            "length_cm": length,
            "yield_pcs": yld,
            "meters_per_pcs": round(meters, 4),
            "price_per_meter": price,
            "cost_per_pcs": round(cost, 2),
            "price_source": source_for(role),
        })
        s["meters_per_pcs"] += meters
        s["fabric_cost_per_pcs"] += cost

    size_list = []
    for s in sizes.values():
        wp = (s["fabric_cost_per_pcs"] / s["meters_per_pcs"]) if s["meters_per_pcs"] > 0 else 0.0
        size_list.append({
            "size": s["size"],
            "entries": s["entries"],
            "meters_per_pcs": round(s["meters_per_pcs"], 4),
            "fabric_cost_per_pcs": round(s["fabric_cost_per_pcs"], 2),
            "weighted_price_per_meter": round(wp, 2),
        })
    size_list.sort(key=lambda x: str(x["size"]))
    avg = round(sum(x["fabric_cost_per_pcs"] for x in size_list) / len(size_list), 2) if size_list else 0.0

    result = {
        "fabrics": priced,
        "sizes": size_list,
        "avg_fabric_cost_per_pcs": avg,
        "has_unresolved_price": any(p["price_source"] == "unresolved" for p in priced),
    }
    if size and size_list:
        sel = next((x for x in size_list if str(x["size"]).upper() == str(size).upper()), None)
        result["selected"] = sel or size_list[0]
    elif size_list:
        result["selected"] = size_list[0]
    else:
        result["selected"] = None
    return result
