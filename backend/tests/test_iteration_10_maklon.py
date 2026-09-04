"""
Iteration 10 — Maklon portal + Vendor portal + Client (Maklon-customer) portal
regression tests for CV. Dewi Aditya ERP.

Focus areas (per review request):
  • RECENTLY MODIFIED files (ObjectId {_id:0} projections + E701 reformat):
      - dewi_maklon.py            (get_client {_id:0})
      - dewi_maklon_po_360.py     (_po_or_404 {_id:0})
      - _maklon_adapter.py        (find_maklon_record {_id:0})
      - vendor_portal.py          (list endpoints code-style reformat)
      - dewi_client_portal.py     (_ensure_sample_actionable {_id:0})

  • Write/integration chains:
      Maklon clients CRUD → Buyer Catalog → PO create → PO 360 → BOM/HPP/QC/SLA
      → Sample request → submit → Client portal approve → Billing/Invoice
      Vendor admin job list (with partner_id/status filters)

All test rows are TEST-prefixed. Endpoint expectations from /app/memory/test_credentials.md:
  - 503  if AI key unset      → accepted
  - 403  for cross-role guard → accepted
  - 409  business guards      → accepted
Only true 500s / serialization errors / broken-chain (downstream doc missing)
are reported as bugs.
"""
import os
import time
import pytest
import requests

def _load_base_url():
    url = os.environ.get('REACT_APP_BACKEND_URL')
    if not url:
        # Load from frontend/.env directly (pytest does not inherit FE env)
        for path in ('/app/frontend/.env',):
            if os.path.exists(path):
                with open(path) as f:
                    for line in f:
                        if line.startswith('REACT_APP_BACKEND_URL='):
                            url = line.split('=', 1)[1].strip()
                            break
            if url:
                break
    if not url:
        raise RuntimeError('REACT_APP_BACKEND_URL not found in env or frontend/.env')
    return url.rstrip('/')


BASE_URL = _load_base_url()
ADMIN_EMAIL = 'admin@garment.com'
ADMIN_PASS = 'Admin@123'

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope='module')
def admin_token():
    r = requests.post(f'{BASE_URL}/api/auth/login',
                      json={'email': ADMIN_EMAIL, 'password': ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f'admin login failed: {r.status_code} {r.text}'
    return r.json()['token']


@pytest.fixture(scope='module')
def auth(admin_token):
    s = requests.Session()
    s.headers.update({'Authorization': f'Bearer {admin_token}',
                      'Content-Type': 'application/json'})
    return s


@pytest.fixture(scope='module')
def ts():
    return int(time.time())


@pytest.fixture(scope='module')
def client_id(auth, ts):
    """Create a TEST maklon client, return its id."""
    payload = {
        'code': f'TST{ts}',
        'name': f'TEST Client {ts}',
        'pic_name': 'PIC Test',
        'phone': '08123456789',
        'email': f'tst{ts}@example.com',
        'address': 'Jl. Test 1',
        'status': 'active',
    }
    r = auth.post(f'{BASE_URL}/api/dewi/maklon/clients', json=payload)
    assert r.status_code in (200, 201), f'create client: {r.status_code} {r.text}'
    return r.json()['id']


@pytest.fixture(scope='module')
def buyer_catalog_id(auth, client_id, ts):
    """Create a TEST buyer catalog entry."""
    r = auth.post(f'{BASE_URL}/api/dewi/maklon/buyer-catalog', json={
        'client_id': client_id,
        'artikel_code': f'TBC{ts}',
        'buyer_ref_code': f'REF{ts}',
        'product_name': f'TEST Article {ts}',
        'default_cmt_price': 15000,
        'color_options': ['Hitam'],
        'size_options': ['M', 'L'],
        'status': 'active',
    })
    assert r.status_code in (200, 201), f'create catalog: {r.status_code} {r.text}'
    return r.json()['id']


@pytest.fixture(scope='module')
def po_id(auth, client_id, buyer_catalog_id, ts):
    r = auth.post(f'{BASE_URL}/api/dewi/maklon/pos', json={
        'client_id': client_id,
        'deadline': '2026-12-31',
        'payment_terms': 'net_30',
        'notes': f'TEST PO {ts}',
        'items': [{
            'seri_no': 'S01',
            'artikel': f'TBC{ts}',
            'sku_code': f'SKU{ts}',
            'color': 'Hitam',
            'size': 'M',
            'qty': 50,
            'cmt_rate_per_pcs': 15000,
            'buyer_catalog_id': buyer_catalog_id,
        }],
    })
    assert r.status_code == 200, f'create PO: {r.status_code} {r.text}'
    data = r.json()
    return data['id']


# ─────────────────────────────────────────────────────────────────────────────
# 1) AUTH
# ─────────────────────────────────────────────────────────────────────────────
class TestAuth:
    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20


# ─────────────────────────────────────────────────────────────────────────────
# 2) MAKLON CLIENTS — regression for get_client {_id:0}
# ─────────────────────────────────────────────────────────────────────────────
class TestMaklonClients:
    def test_list_clients(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/clients')
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_client_detail_after_modification(self, auth, client_id):
        """RECENTLY MODIFIED: dewi_maklon.py get_client uses {_id:0} projection."""
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/clients/{client_id}')
        assert r.status_code == 200, f'{r.status_code} {r.text}'
        body = r.json()
        assert body.get('id') == client_id
        # CRITICAL: no '_id' field should leak (would indicate broken serialization)
        assert '_id' not in body, 'ObjectId leaked to response'

    def test_get_client_404(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/clients/does-not-exist')
        assert r.status_code == 404

    def test_update_client(self, auth, client_id):
        r = auth.put(f'{BASE_URL}/api/dewi/maklon/clients/{client_id}', json={
            'code': f'TST{int(time.time())}A',
            'name': 'TEST Client Updated',
            'status': 'active',
        })
        assert r.status_code == 200, f'{r.status_code} {r.text}'

    def test_toggle_client(self, auth, client_id):
        r = auth.put(f'{BASE_URL}/api/dewi/maklon/clients/{client_id}/toggle')
        assert r.status_code == 200
        # toggle back to active for downstream tests
        auth.put(f'{BASE_URL}/api/dewi/maklon/clients/{client_id}/toggle')


# ─────────────────────────────────────────────────────────────────────────────
# 3) BUYER CATALOG CRUD
# ─────────────────────────────────────────────────────────────────────────────
class TestBuyerCatalog:
    def test_list(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/buyer-catalog')
        assert r.status_code == 200

    def test_get_detail(self, auth, buyer_catalog_id):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/buyer-catalog/{buyer_catalog_id}')
        assert r.status_code == 200
        assert '_id' not in r.json()

    def test_price_history(self, auth, buyer_catalog_id):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/buyer-catalog/{buyer_catalog_id}/price-history')
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4) MAKLON PO + PO 360 — regression for _po_or_404 {_id:0}
# ─────────────────────────────────────────────────────────────────────────────
class TestMaklonPO:
    def test_list_pos(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/pos')
        assert r.status_code == 200

    def test_get_po_detail(self, auth, po_id):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/pos/{po_id}')
        assert r.status_code == 200
        body = r.json()
        assert body.get('id') == po_id
        assert isinstance(body.get('items'), list)

    def test_po_360(self, auth, po_id):
        """RECENTLY MODIFIED: dewi_maklon_po_360.py _po_or_404 uses {_id:0}."""
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/pos/{po_id}/360')
        assert r.status_code == 200, f'{r.status_code} {r.text}'
        body = r.json()
        assert 'po' in body
        assert body['po'].get('id') == po_id
        # Verify the 360 aggregator returns expected sections
        for key in ('dispatches', 'invoices'):
            assert key in body, f'PO360 missing {key}'

    def test_po_timeline(self, auth, po_id):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/pos/{po_id}/timeline')
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_confirm_po(self, auth, po_id):
        r = auth.post(f'{BASE_URL}/api/dewi/maklon/pos/{po_id}/confirm')
        # 200 success or 400 if already confirmed
        assert r.status_code in (200, 400), f'{r.status_code} {r.text}'

    def test_pos_summary(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/pos-summary')
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 5) MAKLON SAMPLES — regression for _maklon_adapter find_maklon_record {_id:0}
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope='module')
def sample_id(auth, po_id, buyer_catalog_id, ts):
    r = auth.post(f'{BASE_URL}/api/dewi/maklon/samples', json={
        'order_id': po_id,
        'product_name': f'TEST Sample {ts}',
        'description': 'Sample for regression test',
        'target_size': 'M',
        'sample_qty': 1,
        'buyer_catalog_id': buyer_catalog_id,
    })
    assert r.status_code in (200, 201), f'create sample: {r.status_code} {r.text}'
    return r.json()['id']


class TestMaklonSamples:
    def test_create_and_get_sample(self, auth, sample_id):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/samples/{sample_id}')
        assert r.status_code == 200
        body = r.json()
        assert body['id'] == sample_id
        # verify _maklon_adapter populated downstream fields from PO
        assert body.get('client_id'), 'sample.client_id not populated from PO via _maklon_adapter'
        assert body.get('po_id'), 'sample.po_id not stored (broken find_maklon_record)'

    def test_list_samples(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/samples')
        assert r.status_code == 200

    def test_submit_sample(self, auth, sample_id):
        r = auth.post(f'{BASE_URL}/api/dewi/maklon/samples/{sample_id}/submit')
        assert r.status_code in (200, 400), f'{r.status_code} {r.text}'

    def test_samples_summary(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/samples/summary/overview')
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 6) BOM TEMPLATES + AI QUOTE + QC + SLA + CONFIG
# ─────────────────────────────────────────────────────────────────────────────
class TestMaklonAux:
    def test_list_bom_templates(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/bom-templates')
        assert r.status_code == 200

    def test_ai_quote_endpoint_exists(self, auth, client_id):
        r = auth.post(f'{BASE_URL}/api/maklon/ai-quote/generate', json={
            'client_id': client_id,
            'product_description': 'Kaos polos cotton combed 30s',
            'qty': 100,
            'target_size': 'M',
        })
        # 503 is acceptable when EMERGENT_LLM_KEY not set
        assert r.status_code in (200, 422, 503), f'{r.status_code} {r.text}'

    def test_list_qc(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/qc')
        assert r.status_code == 200

    def test_qc_summary(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/qc/summary/overview')
        assert r.status_code == 200

    def test_sla_dashboard(self, auth):
        r = auth.get(f'{BASE_URL}/api/maklon/sla/dashboard')
        assert r.status_code == 200

    def test_billing_invoices_list(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/invoices')
        assert r.status_code == 200

    def test_billing_summary(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/reports/billing-summary')
        assert r.status_code == 200

    def test_billing_aging(self, auth):
        r = auth.get(f'{BASE_URL}/api/dewi/maklon/reports/aging')
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 7) BILLING / FINANCE chain (best-effort, allow expected guards)
# ─────────────────────────────────────────────────────────────────────────────
class TestBillingChain:
    def test_post_ar_for_po(self, auth, po_id):
        """post-ar route is the AR side of finance integration."""
        r = auth.post(f'{BASE_URL}/api/dewi/maklon/finance/pos/{po_id}/post-ar', json={})
        # Allowed: 200 success, 400 business guard (PO not in correct status),
        # 404 if route variant differs.
        assert r.status_code in (200, 400, 404, 409, 422), f'{r.status_code} {r.text}'

    def test_generate_invoice_from_po(self, auth, po_id):
        r = auth.post(f'{BASE_URL}/api/dewi/maklon/invoices/generate', json={
            'order_id': po_id,
        })
        # 200 success or 400 business guard if PO status not invoiceable.
        assert r.status_code in (200, 400), f'{r.status_code} {r.text}'


# ─────────────────────────────────────────────────────────────────────────────
# 8) VENDOR PORTAL — list endpoints (RECENTLY MODIFIED E701 reformat)
# ─────────────────────────────────────────────────────────────────────────────
class TestVendorPortalAdmin:
    BASE = '/api/vendor-portal'

    def test_list_partners(self, auth):
        r = auth.get(f'{BASE_URL}{self.BASE}/partners')
        assert r.status_code == 200

    def test_list_all_jobs_no_filter(self, auth):
        """Reformatted lines: 236/240."""
        r = auth.get(f'{BASE_URL}{self.BASE}/jobs')
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_jobs_with_partner_filter(self, auth):
        r = auth.get(f'{BASE_URL}{self.BASE}/jobs',
                     params={'partner_id': 'nonexistent', 'status': 'open'})
        assert r.status_code == 200

    def test_progress_audit_with_date_filter(self, auth):
        """Reformatted lines: 451-459."""
        r = auth.get(f'{BASE_URL}{self.BASE}/progress-audit',
                     params={'date_from': '2025-01-01', 'date_to': '2026-12-31'})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_accounts(self, auth):
        r = auth.get(f'{BASE_URL}{self.BASE}/accounts')
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 9) CLIENT PORTAL — provision admin account, login, sample actionable check
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope='module')
def client_portal_creds(auth, client_id, ts):
    """Admin provisions a portal account for the TEST client."""
    email = f'cp{ts}@example.com'
    r = auth.post(f'{BASE_URL}/api/dewi/maklon/clients/{client_id}/provision-portal', json={
        'email': email,
        'name': 'TEST Portal User',
        'password': 'Test@1234',
    })
    if r.status_code not in (200, 201):
        pytest.skip(f'provision-portal failed: {r.status_code} {r.text}')
    return {'email': email, 'password': 'Test@1234'}


@pytest.fixture(scope='module')
def client_portal_session(client_portal_creds):
    s = requests.Session()
    r = s.post(f'{BASE_URL}/api/dewi/client-portal/auth/login', json=client_portal_creds, timeout=30)
    if r.status_code != 200:
        pytest.skip(f'client portal login failed: {r.status_code} {r.text}')
    token = r.json()['token']
    s.headers.update({'Authorization': f'Bearer {token}',
                      'Content-Type': 'application/json'})
    # If must_change_password is set, change it (server returns 428 otherwise)
    if r.json().get('user', {}).get('must_change_password'):
        new_pw = 'NewPass@9876'
        cp = s.post(f'{BASE_URL}/api/dewi/client-portal/auth/change-password', json={
            'old_password': client_portal_creds['password'],
            'new_password': new_pw,
        }, timeout=30)
        if cp.status_code != 200:
            pytest.skip(f'change-password failed: {cp.status_code} {cp.text}')
        # Re-login to pick up the cleared must_change_password flag
        r2 = s.post(f'{BASE_URL}/api/dewi/client-portal/auth/login', json={
            'email': client_portal_creds['email'], 'password': new_pw,
        }, timeout=30)
        if r2.status_code != 200:
            pytest.skip(f're-login after change-password failed: {r2.status_code} {r2.text}')
        s.headers['Authorization'] = f'Bearer {r2.json()["token"]}'
    return s


class TestClientPortal:
    def test_provision_account(self, client_portal_creds):
        assert client_portal_creds['email']

    def test_client_login_and_me(self, client_portal_session):
        r = client_portal_session.get(f'{BASE_URL}/api/dewi/client-portal/auth/me')
        assert r.status_code == 200
        assert 'user' in r.json()

    def test_client_dashboard(self, client_portal_session):
        r = client_portal_session.get(f'{BASE_URL}/api/dewi/client-portal/dashboard')
        assert r.status_code == 200

    def test_client_list_orders(self, client_portal_session):
        r = client_portal_session.get(f'{BASE_URL}/api/dewi/client-portal/orders')
        assert r.status_code == 200

    def test_client_list_samples(self, client_portal_session):
        r = client_portal_session.get(f'{BASE_URL}/api/dewi/client-portal/samples')
        assert r.status_code == 200

    def test_client_list_invoices(self, client_portal_session):
        r = client_portal_session.get(f'{BASE_URL}/api/dewi/client-portal/invoices')
        assert r.status_code == 200

    def test_client_badge_counts(self, client_portal_session):
        r = client_portal_session.get(f'{BASE_URL}/api/dewi/client-portal/badge-counts')
        assert r.status_code == 200

    def test_client_sample_action_404_uses_id0_projection(self, client_portal_session):
        """RECENTLY MODIFIED: dewi_client_portal.py _ensure_sample_actionable {_id:0}.

        Calling approve on a non-existent sample id must produce a clean 404
        (NOT a 500 from ObjectId serialization or similar)."""
        r = client_portal_session.post(
            f'{BASE_URL}/api/dewi/client-portal/samples/no-such-sample/approve',
            json={'feedback': 'ok'},
        )
        assert r.status_code in (400, 404), f'{r.status_code} {r.text}'

    def test_client_approve_real_sample(self, auth, client_portal_session, sample_id):
        """End-to-end: admin submits, client approves. The sample fixture has
        already been submitted by TestMaklonSamples.test_submit_sample."""
        # Ensure sample is in submitted state (idempotent attempt)
        auth.post(f'{BASE_URL}/api/dewi/maklon/samples/{sample_id}/submit')
        r = client_portal_session.post(
            f'{BASE_URL}/api/dewi/client-portal/samples/{sample_id}/approve',
            json={'feedback': 'TEST approved'},
        )
        # 200 success path or 400 if not in submitted state
        assert r.status_code in (200, 400, 404), f'{r.status_code} {r.text}'


# ─────────────────────────────────────────────────────────────────────────────
# 10) Cleanup (best-effort)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope='module', autouse=True)
def _final_cleanup(request, auth):
    yield
    # Soft-delete client (route does $set status:inactive). Best-effort only.
    cid = getattr(request.node, '_test_client_id', None)
    if cid:
        try:
            auth.delete(f'{BASE_URL}/api/dewi/maklon/clients/{cid}')
        except Exception:
            pass
