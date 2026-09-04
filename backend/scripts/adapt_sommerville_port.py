"""One-shot mechanical adaptation of the 5 ported SOMMERVILLE route modules.
Applies: RBAC constant remap, vendor identity helper, klien_maklon deny on all
handlers, and rbac import injection. Targeted business logic edits (business_type,
vendor/buyer resolve, finance hooks) are applied separately via search_replace.
"""
import re

FILES = [
    '/app/backend/routes/production_pos.py',
    '/app/backend/routes/vendor_shipment.py',
    '/app/backend/routes/production_execution.py',
    '/app/backend/routes/exceptions.py',
    '/app/backend/routes/buyer_shipment.py',
]

IMPORT_ANCHOR = "from auth import require_auth, check_role, log_activity, serialize_doc"
RBAC_IMPORT = (
    IMPORT_ANCHOR
    + "\nfrom routes.production_rbac import (PROD_ADMIN_ROLES, PROD_VENDOR_ROLES,"
    + "\n    is_vendor, vendor_identity, deny_klien, resolve_vendor_doc, resolve_buyer_name)"
)

for path in FILES:
    with open(path) as f:
        src = f.read()

    # 1. rbac import
    src = src.replace(IMPORT_ANCHOR, RBAC_IMPORT, 1)

    # 2. role-list remaps
    src = src.replace("check_role(user, ['admin', 'superadmin'])", "check_role(user, PROD_ADMIN_ROLES)")
    src = src.replace("check_role(user, ['admin', 'vendor'])", "check_role(user, PROD_ADMIN_ROLES + PROD_VENDOR_ROLES)")
    src = src.replace("check_role(user, ['admin'])", "check_role(user, PROD_ADMIN_ROLES)")

    # 3. vendor identity remaps
    src = src.replace("user.get('role') == 'vendor'", "is_vendor(user)")
    src = src.replace("user.get('vendor_id')", "vendor_identity(user)")

    # 4. deny_klien after every handler auth line
    src = re.sub(
        r"(\n(    )user = await require_auth\(request\)\n)",
        r"\1\2deny_klien(user)\n",
        src,
    )
    # handlers that discard the user object
    src = re.sub(
        r"(\n(    )await require_auth\(request\)\n)",
        lambda m: f"\n{m.group(2)}user = await require_auth(request)\n{m.group(2)}deny_klien(user)\n",
        src,
    )

    with open(path, 'w') as f:
        f.write(src)
    print(f"adapted {path}")

# 5. strip serial tracking section from buyer_shipment.py (kept in DA operations_serials.py)
BS = '/app/backend/routes/buyer_shipment.py'
with open(BS) as f:
    src = f.read()
marker = src.index('# ─── SERIAL TRACKING TIMELINE')
src = src[:marker].rstrip() + '\n'
with open(BS, 'w') as f:
    f.write(src)
print('stripped serial section from buyer_shipment.py')
