# 🚨 AGENT DEVELOPMENT RULES — MANDATORY READING
## CV. Dewi Aditya ERP — Anti-Technical-Debt Protocol

**Status:** 🔴 **MANDATORY — TIDAK BOLEH DI-SKIP**  
**Version:** 1.0  
**Established:** 22 Mei 2026  
**Updated by:** Neo (after 12-Lens Forensic Audit)

---

## 🌐 LANGUAGE RULE (ABSOLUTE PRIORITY)

> **SEMUA komunikasi dengan user WAJIB dalam BAHASA INDONESIA (id-ID).**

- Target user: Indonesian businesses
- All UI labels are Indonesian
- User prompts are Indonesian
- **JANGAN PERNAH** balas user dengan English
- Boleh pakai istilah teknis Inggris (endpoint, schema, migration, dll) sebagai bahasa developer, **tapi narasi/penjelasan harus Indonesia**

---

## 📖 KENAPA DOKUMEN INI ADA — ROOT CAUSE ANALYSIS

### 🔥 Penyebab Technical Debt yang Sudah Terjadi

Sistem ini punya **technical debt parah** karena agent-agent sebelumnya melakukan kesalahan berikut:

| ❌ Kesalahan | 💀 Akibat |
|--------------|-----------|
| Asumsi tanpa baca kode | 4 menu broken, fallback ke ManagementDashboard |
| Build feature paralel tanpa cek existing | 4 sistem aksesoris paralel (`acc_items`, `rahaza_materials`, `accessories`, dll) |
| Buat collection baru daripada extend yang ada | 280+ collections, banyak duplicate |
| Tidak update old code saat build new | `dewi_maklon_orders` vs `dewi_maklon_pos` coexist |
| Skip cleanup setelah refactor | 30+ orphan registry IDs, 5+ legacy redirects |
| Tambah badge "BARU" tanpa expiry | 25+ badge clutter |
| Naming inkonsisten (rahaza_/dewi_/wms_/wh_) | Cognitive overload, hard to maintain |
| Buat file monster (>3000 lines) | `AssetManagementPortal.jsx` (3124 lines), `dewi_asset_management.py` (2392 lines) |
| Tidak document keputusan strategis | Setiap agent re-invent the wheel |
| Skip testing setelah perubahan | Bug recurring di setiap session |

### 🎯 Tujuan Dokumen Ini

**Mencegah pola-pola di atas terjadi LAGI di session-session berikutnya.**

Aturan-aturan di bawah ini WAJIB diikuti tanpa pengecualian.

---

# 🔒 PROTOCOL #1 — PRE-DEVELOPMENT (MANDATORY)

## Sebelum nulis SATU baris kode pun, lakukan:

### Step 1: Read the Map (5-10 menit)
```bash
# WAJIB baca:
cat /app/memory/PRD.md
cat /app/FORENSIC_00_EXECUTIVE_SUMMARY.md
cat /app/FORENSIC_11_MIGRATION_ROADMAP.md

# RECOMMENDED baca (sesuai task):
cat /app/FORENSIC_04_DATA_ARCHITECTURE.md  # jika task tentang DB
cat /app/FORENSIC_07_INFORMATION_ARCHITECTURE.md  # jika task tentang sidebar/menu
cat /app/FORENSIC_09_CONSOLIDATION_PLAN.md  # jika task tentang refactor
cat /app/design_guidelines.md  # jika task tentang UI
```

### Step 2: Code Discovery (10-15 menit)

**ATURAN ABSOLUT: SELALU baca existing code dulu sebelum buat baru.**

```bash
# Sebelum buat collection baru:
cd /app/backend && grep -rohE "db\.[a-z_][a-z0-9_]*" --include="*.py" routes/ | sort -u | grep <keyword>

# Sebelum buat component baru:
find /app/frontend/src -iname "*<KeyWord>*" -type f

# Sebelum buat endpoint baru:
grep -rn "@router\.(get|post|put|delete|patch)" /app/backend/routes/ | grep <pattern>

# Cek apakah module sudah pernah ada di registry:
grep -i "<keyword>" /app/frontend/src/components/erp/moduleRegistry.js
```

### Step 3: Decision Tree

```
┌─────────────────────────────────────────────────┐
│ Apakah fitur/feature yang diminta SUDAH ADA?    │
└────────────┬────────────────────────────────────┘
             │
        ┌────┴────┐
        │  YES    │  → Apakah berfungsi 100%?
        │         │     ├─ YA → JANGAN buat baru. Tanya user "Apakah ini yang Anda maksud?"
        │         │     └─ TIDAK → Perbaiki yang ada. JANGAN build paralel
        │  NO     │  → Apakah ADA yang mirip business goal-nya?
        │         │     ├─ YA → Extend / refactor existing. JANGAN duplikasi
        │         │     └─ TIDAK → Build baru sesuai standar di doc ini
        └─────────┘
```

### Step 4: User Confirmation (untuk major changes)

**WAJIB tanya user dulu jika:**
- Akan delete/migrate collection MongoDB
- Akan rename/restructure menu di lebih dari 3 portal
- Akan refactor file lebih dari 500 baris
- Akan ubah API contract (breaking change)
- Akan tambah dependency baru

---

# 📐 PROTOCOL #2 — CODE STANDARDS (NON-NEGOTIABLE)

## 2.1 File Size Limits

### 🚫 NO MONSTER FILES

| File Type | MAX Lines | Soft Warning | Action Needed |
|-----------|-----------|--------------|---------------|
| React Component (.jsx) | **500** | 400 | Split into sub-components |
| Python Route File (.py) | **800** | 600 | Split by domain/aggregate |
| Utility/Helper (.js/.ts) | **300** | 250 | Decompose by concern |
| CSS File | **400** | 300 | Use Tailwind classes |
| Test File | **800** | 600 | Split by test category |

**Saat ini violations yang harus di-refactor (tracked di FORENSIC_06):**
- `AssetManagementPortal.jsx` (3124 lines) → Split: Dashboard, Detail, Transfer, Photo modules
- `LiveHostModule.jsx` (~2300 lines) → Split per feature
- `CommunicationHubPortal.jsx` (1751 lines) → Extract MessageItem, ChannelList, Sidebar
- `WorkspacePortal.jsx` (1364 lines) → Extract SpreadsheetEditor, ShareDialog, etc.
- `dewi_asset_management.py` (2392 lines) → Split: assets, transfers, maintenance, depreciation
- `dewi_communication.py` (1141 lines) → Split: channels, messages, threads, presence
- `server.py` (1542 lines) → **JANGAN REWRITE**, hanya tambah `app.include_router()` di akhir

### Rule of Thumb: One Component = One Responsibility

```jsx
// ❌ BAD: Monster component
function AssetManagementPortal() {
  // 3000 lines of dashboard + list + create + edit + transfer + photo + ...
}

// ✅ GOOD: Decomposed
function AssetManagementPortal() {
  return (
    <Routes>
      <AssetDashboard />
      <AssetList />
      <AssetDetail>
        <AssetInfoTab />
        <AssetTransferTab />
        <AssetMaintenanceTab />
      </AssetDetail>
    </Routes>
  );
}
```

## 2.2 Naming Conventions

### Files
```
PascalCase.jsx              # React components
camelCase.js                # Utilities, hooks (prefix with `use` for hooks)
snake_case.py               # Python files
kebab-case.css              # Stylesheets (if any)
SCREAMING_SNAKE_CASE.md     # Documentation
```

### Variables
```javascript
// JavaScript/React
const userId = 'uuid';                    // camelCase variables
const MAX_RETRIES = 3;                     // SCREAMING_SNAKE for constants
function calculateTotal() {}               // camelCase functions
class UserService {}                       // PascalCase classes
const UserAvatar = () => {};               // PascalCase components
const isLoading = useState(false);         // is/has/can prefix for booleans
```

```python
# Python
user_id = "uuid"                          # snake_case variables
MAX_RETRIES = 3                           # SCREAMING_SNAKE for constants
def calculate_total(): pass                # snake_case functions
class UserService: pass                    # PascalCase classes
is_active = True                          # is/has/can prefix for booleans
```

### Database Collections (MongoDB)
```
TARGET CONVENTION (Phase 3+):
production_*       — Production domain
inventory_*        — Stock & warehouse
finance_*          — AR/AP/Accounting
hr_*               — Human Resources
marketing_*        — Marketing channels
maklon_*           — Maklon B2B
rnd_*              — Research & Design
collab_*           — Collaboration

CURRENT (legacy, do not create new with these prefixes):
rahaza_*           — Legacy PT Rahaza prefix
dewi_*             — Legacy CV. Dewi Aditya prefix
wms_*              — Legacy WMS
acc_*              — Legacy Accessories
```

### API Routes
```
/api/<domain>/<resource>                  # e.g., /api/inventory/items
/api/<domain>/<resource>/<id>             # e.g., /api/inventory/items/{uuid}
/api/<domain>/<resource>/<id>/<action>    # e.g., /api/orders/{uuid}/approve

# Specific BEFORE generic (FastAPI route order)
@router.get("/users/me")           # ← Define FIRST
@router.get("/users/{user_id}")    # ← Define AFTER
```

## 2.3 DRY Principle (Don't Repeat Yourself)

### Frontend: Component Composition
```jsx
// ❌ BAD: Copy-pasted dialog 5 places
// dialogs/ConfirmDeleteDialog.jsx, ConfirmCancelDialog.jsx, etc.

// ✅ GOOD: One generic component
function ConfirmDialog({ title, message, onConfirm, variant = 'default' }) { }
```

### Backend: Shared Services
```python
# ❌ BAD: counter logic copy-pasted in 20 routes
async def get_next_po_number(): pass
async def get_next_wo_number(): pass

# ✅ GOOD: Centralized
from services.counters import next_number
po_num = await next_number(db, "PO")
```

## 2.4 Code Comments

```python
# ❌ BAD: Useless comments
i = i + 1  # increment i

# ✅ GOOD: Why, not what
# Use timezone.utc because frontend expects ISO 8601 UTC
created_at = datetime.now(timezone.utc)

# ✅ GOOD: Section markers (large files)
# ─── Master Data Endpoints ────────────────────────────────────
@router.get("/items")
```

## 2.5 No Dead Code

```
🚫 NEVER commit:
- Commented-out code blocks (>5 lines)
- console.log() / print() debug statements
- Unused imports
- Unused variables
- Backup files (.backup, .old, _v1)

✅ ALWAYS:
- Remove before commit
- Use git for history (not file copies)
- Use linter (ruff for Python, ESLint for JS)
```

---

# 🔐 PROTOCOL #3 — SECURITY STANDARDS

## 3.1 Authentication & Authorization

### JWT Token Handling
```python
# ✅ Backend: Always validate token
from middleware.auth import require_auth
@router.get("/users/me")
async def get_me(user = Depends(require_auth)):
    return user
```

```javascript
// ✅ Frontend: Always include token
const res = await fetch(url, {
  headers: { Authorization: `Bearer ${token}` }
});

// ❌ NEVER: Hardcode tokens
const TOKEN = "eyJhbGciOiJ..."; // ❌ NEVER
```

### Role-Based Access Control (RBAC)
```python
# ✅ Check permissions at endpoint level
@router.post("/admin/users")
async def create_user(user = Depends(require_role("admin"))):
    pass
```

### Session Management
- JWT expiry: 24 hours max (current setup)
- Refresh tokens via /api/auth/refresh
- No infinite sessions

## 3.2 Input Validation

### Pydantic Models (Backend)
```python
# ✅ Always use Pydantic for request bodies
from pydantic import BaseModel, Field, validator

class CreateOrderRequest(BaseModel):
    customer_id: str = Field(..., min_length=1)
    items: list[OrderItem] = Field(..., min_length=1)
    total_amount: float = Field(..., ge=0)
    
    @validator('customer_id')
    def validate_uuid(cls, v):
        # Validate UUID format
        return v
```

### Frontend Input Sanitization
```jsx
// ✅ Use form library validation
import { useForm } from 'react-hook-form';
// Or Shadcn Form pattern
```

## 3.3 NoSQL Injection Prevention

```python
# ❌ BAD: Direct user input to query
await db.users.find_one({"email": request_data["email"]})  # Unsafe if email is {"$ne": null}

# ✅ GOOD: Validate type first
email = str(request_data.get("email", "")).strip()
if not email or "@" not in email:
    raise HTTPException(400, "Invalid email")
await db.users.find_one({"email": email})
```

## 3.4 XSS Prevention

```jsx
// ❌ BAD: Inject raw HTML
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// ✅ GOOD: React auto-escapes
<div>{userInput}</div>

// ✅ Only use dangerouslySetInnerHTML for SANITIZED markdown/HTML
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }} />
```

## 3.5 Secrets Management

```
✅ ALWAYS:
- Use environment variables (.env)
- .env file added to .gitignore
- Access via os.environ.get() or process.env
- Use EMERGENT_LLM_KEY for AI integrations

🚫 NEVER:
- Hardcode API keys in code
- Commit .env files
- Log secrets to console/file
- Send secrets in error responses
- Use secrets in URLs (use headers instead)
```

## 3.6 Audit Logging

```python
# ✅ Log critical actions
await db.rahaza_audit_logs.insert_one({
    "id": str(uuid.uuid4()),
    "action": "ORDER_APPROVED",
    "entity_type": "order",
    "entity_id": order_id,
    "user_id": user["id"],
    "user_name": user.get("name"),
    "before": prev_state,
    "after": new_state,
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
```

**MANDATORY audit log for:**
- User authentication (login/logout)
- Permission changes
- Financial transactions (payment, invoice, journal)
- Master data changes
- User account creation/deletion
- Sensitive data access (payroll, employee personal info)

## 3.7 Rate Limiting

```python
# Current: rate_limit_buckets collection
# Apply rate limit on:
- Login endpoints (5 req/min)
- Password reset (3 req/15min)
- File upload (10 req/min)
- AI/LLM calls (per user quota)
```

---

# 🎨 PROTOCOL #4 — UI/UX STANDARDS

## 4.1 Component Library (MANDATORY)

### Shadcn/UI Components Only
```jsx
// ✅ ALWAYS use Shadcn from @/components/ui/
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Card, CardContent, CardHeader } from '@/components/ui/card';

// ❌ NEVER use raw HTML for interactive elements
<button>Click me</button>  // ❌ NEVER
<select>...</select>  // ❌ NEVER
<input type="text">  // ❌ NEVER (unless inside Form pattern)
```

### Icons: Lucide-React ONLY
```jsx
// ✅ ALWAYS
import { Search, Trash2, Edit3 } from 'lucide-react';

// ❌ NEVER
<span>🔍</span>   // No emoji icons in UI
<i className="fa fa-search" />  // No FontAwesome
```

## 4.2 Design Tokens

```jsx
// ✅ ALWAYS use design tokens
<div className="bg-background text-foreground border-border">

// ❌ NEVER hardcode colors
<div className="bg-white text-black border-gray-200">  // ❌
<div style={{ color: '#FF0000' }}>  // ❌
```

### Allowed Tailwind Color Scales
```
Use semantic tokens:
- bg-background / bg-card / bg-popover
- text-foreground / text-muted-foreground
- border-border / border-input
- primary / secondary / accent / destructive
- success (green-600) / warning (orange-500) / info (blue-500)
```

## 4.3 Layout Patterns

### Page Layout (consistent)
```jsx
function MyModule() {
  return (
    <div className="h-full overflow-auto">
      <PageHeader title="..." description="..." />
      <div className="container mx-auto px-4 py-6 space-y-6">
        <Card>
          <CardContent>...</CardContent>
        </Card>
      </div>
    </div>
  );
}
```

### Spacing Scale
```
Use multiples of 4px (Tailwind default):
- gap-2 (8px) — tight elements
- gap-4 (16px) — related elements
- gap-6 (24px) — section separation
- gap-8 (32px) — major sections
- py-12 (48px) — page-level breathing room
```

## 4.4 Loading / Error / Empty States (MANDATORY)

```jsx
function DataModule() {
  const { data, loading, error } = useData();
  
  // ✅ Loading state
  if (loading) return <Skeleton className="h-32 w-full" />;
  
  // ✅ Error state
  if (error) return (
    <Alert variant="destructive">
      <AlertCircle />
      <AlertTitle>Gagal memuat data</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
      <Button onClick={retry}>Coba Lagi</Button>
    </Alert>
  );
  
  // ✅ Empty state
  if (!data || data.length === 0) return (
    <EmptyState
      icon={Inbox}
      title="Belum ada data"
      description="Mulai dengan menambah item pertama"
      action={<Button>+ Tambah Baru</Button>}
    />
  );
  
  // ✅ Success state
  return <DataTable data={data} />;
}
```

## 4.5 Form Patterns

```jsx
// ✅ Use Shadcn Form + react-hook-form
<Form {...form}>
  <FormField
    control={form.control}
    name="email"
    render={({ field }) => (
      <FormItem>
        <FormLabel>Email <span className="text-red-500">*</span></FormLabel>
        <FormControl>
          <Input {...field} type="email" data-testid="email-input" />
        </FormControl>
        <FormMessage />
      </FormItem>
    )}
  />
</Form>
```

### Form Layout Rules
- Label: top of field (not left)
- Required indicator: `*` red after label
- Error message: below field, in red
- Submit button: bottom-right
- Cancel button: ghost variant, left of submit

## 4.6 Naming in UI (Indonesian)

```
✅ Indonesian labels untuk user-facing:
- "Simpan" not "Save"
- "Hapus" not "Delete"
- "Tambah Baru" not "Add New"
- "Cari..." not "Search..."
- "Kembali" not "Back"

✅ Allowed English (technical, widely-understood):
- "Dashboard"
- "OK"
- "Email"
- "Upload"
- Domain terms: "PO", "WO", "GRN", "CMT", "Maklon"
```

## 4.7 Badge Discipline

```jsx
// ❌ NEVER: Stale "BARU" badges that never expire
{ badge: 'BARU' }  // Will become forgotten clutter

// ✅ ONLY use badges for:
{ badge: 'AI' }       // Indicates AI-powered feature (semantic, doesn't expire)
{ badge: '5' }        // Notification count (dynamic, real)
{ badge: 'Beta' }     // Experimental feature (with timeline to remove)

// 🚫 NEVER expose internal priority:
{ badge: 'P0' }   // Internal task priority, not for UI
{ badge: 'P1' }   // Internal task priority, not for UI
```

## 4.8 Accessibility (A11y)

### Mandatory
```jsx
// ✅ data-testid on ALL interactive elements
<Button data-testid="save-order-btn">Simpan</Button>
<Input data-testid="email-input" />
<div data-testid="user-info" />  // Even read-only

// ✅ ARIA labels for icon-only buttons
<Button size="icon" aria-label="Hapus item">
  <Trash2 />
</Button>

// ✅ Keyboard navigation works
- Tab moves focus
- Enter activates buttons
- Esc closes modals

// ✅ Color contrast: WCAG AA minimum (4.5:1 for text)
```

## 4.9 Mobile Responsive

```jsx
// ✅ Mobile-first breakpoints
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

// ✅ Touch targets minimum 44x44px
<Button className="min-h-[44px] min-w-[44px]">

// ✅ Tables: horizontal scroll OR card view on mobile
<div className="hidden md:block"><DataTable /></div>
<div className="md:hidden"><MobileCardView /></div>
```

## 4.10 Animations & Motion

```css
/* ✅ Specific properties only */
.fade { transition: opacity 200ms ease-out; }
.slide { transition: transform 250ms cubic-bezier(0.16,1,0.3,1); }

/* ❌ NEVER */
.bad { transition: all 200ms; }  /* Performance + side-effects issue */
```

### Duration Guidelines
- Micro-interactions: 150-200ms
- UI feedback (button press): 100ms
- Page transitions: 250-350ms
- **NEVER >500ms** for routine interactions

---

# 🗄️ PROTOCOL #5 — DATABASE STANDARDS

## 5.1 SSOT (Single Source of Truth)

### Every business entity = 1 authoritative collection

```
Material Master → rahaza_materials (with type field)
Stock → rahaza_material_stock
Customer → rahaza_customers
Maklon PO → dewi_maklon_pos (NOT dewi_maklon_orders)
Marketing Order → marketing_orders
KOL → marketing_kol_creators
```

### Before creating new collection, ASK:
```
1. Apakah entity ini sudah ada di collection existing?
2. Apakah field yang dibutuhkan bisa ditambah ke existing schema?
3. Apakah bisa dipisah dengan `type` field di existing collection?
4. Hanya buat baru jika BENAR-BENAR domain berbeda (different lifecycle/access)
```

## 5.2 Schema Standards

```python
# ✅ Every document
{
    "id": str(uuid.uuid4()),                                # UUID, not ObjectId
    "created_at": datetime.now(timezone.utc).isoformat(),  # ISO string, UTC
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "created_by": user["id"],                              # Audit trail
    "tenant_id": "default",                                # Multi-tenant ready
    # ... business fields
}
```

### Naming Fields
```
id              — Primary UUID
*_id            — Foreign key to another entity
*_at            — Timestamp (created_at, updated_at, deleted_at)
*_by            — User reference (created_by, modified_by)
is_*            — Boolean flags
has_*           — Boolean flags
status          — String enum: pending/active/completed/cancelled
```

## 5.3 Migration Protocol

### Step-by-step (MANDATORY)

```python
# 1. BACKUP first
# 2. Write migration script in /app/backend/migrations/
# 3. Dry-run mode first (count + sample, no writes)
# 4. Validate counts
# 5. Run migration with --execute flag
# 6. Validate counts match expected
# 7. Update routes to use new schema
# 8. Keep OLD collection for 1 week monitoring
# 9. Then delete old collection
```

### Example Migration Template
```python
"""
Migration: <description>
Created: YYYY-MM-DD
Reversible: YES/NO
"""
import asyncio, argparse
from database import get_db

async def migrate(dry_run=True):
    db = get_db()
    
    # Read from source
    source_count = await db.old_collection.count_documents({})
    print(f"Source: {source_count} records")
    
    cursor = db.old_collection.find({})
    migrated = 0
    
    async for doc in cursor:
        new_doc = transform(doc)
        if not dry_run:
            await db.new_collection.update_one(
                {"id": new_doc["id"]},
                {"$set": new_doc},
                upsert=True
            )
        migrated += 1
    
    print(f"Migrated: {migrated}")
    print(f"Dry-run: {dry_run}")
    
    if not dry_run:
        target_count = await db.new_collection.count_documents({})
        print(f"Target: {target_count} records")
        assert target_count >= source_count, "Migration data loss!"

def transform(old):
    return {
        "id": old["_id"] or str(uuid.uuid4()),
        # ... transform fields
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=not args.execute))
```

## 5.4 Indexes (PERFORMANCE)

```python
# ✅ Add index for:
- Foreign keys (e.g., customer_id, employee_id)
- Fields used in WHERE/filter
- Sort fields (created_at descending)
- Unique constraints

# Example
await db.rahaza_orders.create_index([("customer_id", 1), ("status", 1)])
await db.rahaza_orders.create_index([("created_at", -1)])
await db.users.create_index("email", unique=True)
```

## 5.5 Query Optimization

```python
# ❌ BAD: N+1 query
for order in orders:
    customer = await db.customers.find_one({"id": order["customer_id"]})
    order["customer"] = customer

# ✅ GOOD: Single aggregation
pipeline = [
    {"$lookup": {
        "from": "customers",
        "localField": "customer_id",
        "foreignField": "id",
        "as": "customer"
    }}
]
results = await db.rahaza_orders.aggregate(pipeline).to_list(None)
```

```python
# ❌ BAD: Load all into memory
all_docs = await db.collection.find({}).to_list(None)  # Could be 1M+

# ✅ GOOD: Paginate
docs = await db.collection.find({}).skip(skip).limit(limit).to_list(None)
total = await db.collection.count_documents({})
```

---

# 🚀 PROTOCOL #6 — PERFORMANCE STANDARDS

## 6.1 Frontend Performance

### React Optimization

```jsx
// ✅ Lazy load heavy modules
const HeavyModule = lazy(() => import('./HeavyModule'));

// ✅ Memoize expensive computations
const totalRevenue = useMemo(() => 
  orders.reduce((sum, o) => sum + o.amount, 0),
  [orders]
);

// ✅ Memoize callback props to prevent re-renders
const handleClick = useCallback(() => {
  doSomething();
}, [dependency]);

// ✅ Avoid inline objects/arrays in JSX
// ❌ BAD: New object every render → child re-renders
<Component options={{ a: 1, b: 2 }} />

// ✅ GOOD
const options = useMemo(() => ({ a: 1, b: 2 }), []);
<Component options={options} />
```

### Bundle Size

```
Target Bundle Size:
- Initial bundle: < 500 KB gzipped
- Per-route lazy chunk: < 200 KB gzipped

Monitor with:
- yarn build → check build output
- Webpack bundle analyzer

Avoid:
- Importing entire library (e.g., lodash)
- import _ from 'lodash'  // ❌ 70KB

Prefer:
- import debounce from 'lodash/debounce'  // ✅ 2KB
- Or use built-in: setTimeout debounce
```

### Data Fetching

```jsx
// ✅ Debounce search inputs
const debouncedSearch = useDebouncedValue(searchInput, 300);
useEffect(() => {
  if (debouncedSearch) fetchData(debouncedSearch);
}, [debouncedSearch]);

// ✅ Cancel in-flight requests on unmount
useEffect(() => {
  const controller = new AbortController();
  fetch(url, { signal: controller.signal });
  return () => controller.abort();
}, []);

// ✅ Pagination for lists > 50 items
const [page, setPage] = useState(1);
useEffect(() => fetchData(page), [page]);
```

## 6.2 Backend Performance

### Async Everywhere
```python
# ✅ ALWAYS async with Motor
async def get_data():
    return await db.collection.find_one({"id": id})

# ❌ NEVER sync MongoDB calls in async route
def get_data():  # ❌ Sync
    return db.collection.find_one({"id": id})
```

### Avoid N+1

```python
# ✅ Use $lookup or batch fetch
order_ids = [o["id"] for o in orders]
customers = await db.customers.find({"id": {"$in": [o["customer_id"] for o in orders]}}).to_list(None)
customer_map = {c["id"]: c for c in customers}
for order in orders:
    order["customer"] = customer_map.get(order["customer_id"])
```

### Caching Strategy

```python
# In-memory cache untuk master data
from functools import lru_cache

@lru_cache(maxsize=100)
def get_coa_tree():
    pass

# Redis cache untuk session/heavy queries (future)
```

### Background Jobs

```python
# ✅ Use APScheduler for periodic tasks
# Not blocking request thread
@scheduler.scheduled_job('cron', hour=2)
async def daily_aggregate():
    pass
```

### Response Size

```python
# ✅ Project only needed fields
await db.collection.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(None)

# ✅ Paginate large responses
# Limit: 100 max per page
limit = min(int(request.query_params.get("limit", 20)), 100)
```

## 6.3 Database Performance

### Index Coverage

```python
# Check if query uses index
explain = await db.collection.find({"field": "value"}).explain()
# Look for "stage": "IXSCAN" (good) vs "COLLSCAN" (bad)
```

### Connection Pooling

```python
# Motor handles this automatically
# But set reasonable maxPoolSize
client = AsyncIOMotorClient(
    MONGO_URL,
    maxPoolSize=50,
    minPoolSize=10,
)
```

---

# 🧪 PROTOCOL #7 — TESTING STANDARDS

## 7.1 When to Test

### MANDATORY Testing
```
- ✅ After ANY backend route change → call testing_agent_v3 OR curl test
- ✅ After ANY frontend module change → screenshot verify
- ✅ After data migration → count + sample validation
- ✅ Before declaring feature "DONE" → end-to-end test
- ✅ After fixing bug → regression test for related areas
- ✅ Before delete operations → confirmation + dry-run
```

## 7.2 Testing Tools

```bash
# Linting (do before testing)
ruff check /app/backend/routes/your_file.py
eslint /app/frontend/src/components/erp/YourModule.jsx

# Backend testing
curl -X GET ${BACKEND_URL}/api/your-endpoint \
  -H "Authorization: Bearer ${TOKEN}"

# Or use testing_agent_v3 for comprehensive tests
```

### Test Coverage Targets
```
Backend critical paths: 60%+
Frontend critical paths: 40%+ (more manual via screenshot)
New code (added in your session): 80%+
```

## 7.3 Bug Verification Protocol

```
1. Reproduce bug (from logs or user report)
2. Identify root cause (use troubleshoot_agent if stuck >2 attempts)
3. Fix
4. Verify fix
5. Check for related areas that might have same bug
6. Update test cases if testable
```

---

# 📚 PROTOCOL #8 — DOCUMENTATION STANDARDS

## 8.1 When to Document

### MANDATORY Updates
```
After each major change, UPDATE /app/memory/PRD.md with:
- What was changed
- Why (business reason)
- Affected files
- Migration steps (if any)
- Known issues
```

### Per-Session Log Format
```markdown
### Session YYYY-MM-DD (Agent: Name)
**Tasks Completed:**
- [Item 1]
- [Item 2]

**Files Modified:**
- /app/path/to/file.py — what changed
- /app/path/to/file.jsx — what changed

**Database Changes:**
- New collection: ...
- Migrated: ...
- Deleted: ...

**Decisions Made:**
- [Decision] — [Rationale]

**Known Issues / Tech Debt:**
- ...

**Next Action Items:**
- ...
```

## 8.2 Code Documentation

```python
# ✅ Module-level docstring
"""
Maklon PO Management Routes
============================
Handles full lifecycle of Maklon Purchase Orders (B2B client orders).

Endpoints:
- GET    /api/maklon/pos              List POs with filter
- POST   /api/maklon/pos              Create new PO
- GET    /api/maklon/pos/{id}         Get PO detail
- PATCH  /api/maklon/pos/{id}         Update PO
- POST   /api/maklon/pos/{id}/approve Approve PO

Dependencies:
- db.dewi_maklon_pos (SSOT)
- db.dewi_maklon_clients (for client lookup)
- db.dewi_maklon_bom (for BOM cascade)

Last refactored: 2026-05-22 (consolidate from dewi_maklon_orders)
"""

# ✅ Function docstring for non-trivial
async def calculate_hpp(po_id: str) -> dict:
    """
    Calculate HPP (Cost of Goods Sold) for a Maklon PO.
    
    Includes: material cost, CMT cost, overhead allocation.
    Excludes: profit margin (calculated separately).
    
    Returns:
        dict: { material_cost, cmt_cost, overhead, total_hpp }
    
    Raises:
        ValueError: if PO not found or status invalid
    """
    pass
```

## 8.3 What NOT to Document

```
🚫 Don't write redundant docs:
- Don't document obvious code
- Don't repeat what variable names already say
- Don't write tutorial-style docs (use comments + tests instead)

✅ DO document:
- Why (business logic)
- Non-obvious algorithms
- Edge cases
- Workarounds
- TODOs with context
```

---

# 🛑 PROTOCOL #9 — STOP & ASK TRIGGERS

## You MUST STOP and ask user before:

### 🔴 Critical Triggers
1. **Database structural changes** (new collection, drop collection, schema migration)
2. **Breaking API changes** (remove/rename endpoint)
3. **Sidebar / menu restructure** affecting >3 portals
4. **Authentication changes**
5. **File deletions** (collection, route, component)
6. **Data migrations** (even if reversible)
7. **Third-party integration** addition
8. **Dependency** addition/removal

### 🟡 Confirmation Triggers
1. **Refactor file >500 lines**
2. **Change naming convention**
3. **Modify shared utility/service**
4. **Add new portal/section**

### 🟢 Auto-Execute OK (within roadmap)
1. Fix typo / styling
2. Add data-testid
3. Add missing form validation
4. Bug fixes (with regression test)
5. Performance optimization
6. Add unit tests

---

# 🔄 PROTOCOL #10 — CONTINUOUS HYGIENE

## After Every Session

### Cleanup Checklist (5 menit)
```
☐ Remove console.log() / print() debug statements
☐ Remove commented-out code blocks
☐ Run ruff/eslint on modified files
☐ Update PRD.md with session log
☐ Update relevant FORENSIC_*.md if strategic change
☐ Verify services running (supervisorctl status)
☐ Take final screenshot of changed UI
☐ Tell user clearly what was done + what's next
```

## Tech Debt Tracking

```markdown
# When you encounter tech debt during your work:

ADD to PRD.md under "## 🚨 TECH DEBT BACKLOG":
- [TD-001] File `XYZ.jsx` is 2000 lines — split needed
- [TD-002] Collection `abc_*` and `xyz_*` have overlap — merge candidate
- [TD-003] Endpoint `/api/old-path` no longer used — delete candidate

This way next agent knows what to fix.
```

---

# 🏗️ PROTOCOL #11 — ARCHITECTURE INVARIANTS

## Things that MUST NEVER change

### Environment
```
🚫 NEVER MODIFY:
- /app/frontend/.env REACT_APP_BACKEND_URL value
- /app/backend/.env MONGO_URL value
- Backend port (must bind 0.0.0.0:8001)
- Supervisor configuration
- /api/* prefix on all backend routes
```

### Identifier Format
```
🚫 NEVER USE MongoDB ObjectId
✅ ALWAYS use UUID v4: str(uuid.uuid4())
```

### Datetime Format
```
🚫 NEVER naive datetime
✅ ALWAYS timezone.utc: datetime.now(timezone.utc).isoformat()
```

### File Operations
```
🚫 NEVER:
- Use npm (use yarn)
- Run python server.py directly (use supervisor)
- Hardcode API keys
- Use HTML entities for special chars in code

✅ ALWAYS:
- yarn add <package> (auto-updates package.json)
- pip install <pkg> && pip freeze > requirements.txt
- supervisorctl restart <service> after env changes
```

---

# 🔌 PROTOCOL #12 — INTEGRATION GUIDELINES

## When User Requests 3rd-Party Integration

```
Step 1: Call integration_playbook_expert_v2 with integration name + version
Step 2: Read returned playbook
Step 3: List required credentials → ask user
Step 4: Implement EXACTLY as playbook says
Step 5: Test
Step 6: Document in PRD.md
```

### LLM-Specific (OpenAI/Anthropic/Google)
```
🚫 NEVER install OpenAI/Anthropic/Google SDKs directly
✅ ALWAYS use emergentintegrations library
✅ ALWAYS use EMERGENT_LLM_KEY (universal key)
✅ Trust user's specified model version (verify via web_search if unknown)
```

---

# 📝 FINAL CHECKLIST (Before Marking Task DONE)

## Pre-Commit Quality Gate

```
☐ Code follows naming conventions (Section 2.2)
☐ No file exceeds size limits (Section 2.1)
☐ No dead code (commented out, unused) (Section 2.5)
☐ Used Shadcn components, no raw HTML (Section 4.1)
☐ Used Lucide icons, no emoji-as-icon (Section 4.1)
☐ Used design tokens, no hardcoded colors (Section 4.2)
☐ Loading/Error/Empty states implemented (Section 4.4)
☐ data-testid on interactive elements (Section 4.8)
☐ Forms use Shadcn Form pattern (Section 4.5)
☐ Indonesian labels in UI (Section 4.6)
☐ Backend validates input (Section 3.2)
☐ Backend has audit log for critical actions (Section 3.6)
☐ UUIDs not ObjectIds (Section 11)
☐ Timezone-aware datetimes (Section 11)
☐ Linter clean (ruff for Python, eslint for JS)
☐ Services running (supervisorctl status)
☐ Manually verified via screenshot/curl
☐ PRD.md updated with session log
☐ User communicated in Indonesian
☐ User informed of changes + next steps
```

---

# 🎯 GOLDEN RULES SUMMARY

> Print these and keep visible during work:

1. **🇮🇩 Bahasa Indonesia untuk user, ALWAYS**
2. **📖 Baca FORENSIC docs + existing code SEBELUM development**
3. **🔍 Code Discovery > Code Creation**
4. **🚫 No monster files (>500 lines React, >800 Python)**
5. **🎨 Shadcn + Lucide + Design tokens only**
6. **🗄️ SSOT — extend existing, don't create parallel**
7. **🔐 Validate input, log audit, encrypt secrets**
8. **⚡ Performance: lazy, memo, paginate, index**
9. **🧪 Test after every change**
10. **📝 Document in PRD.md every session**
11. **🛑 STOP & ASK before destructive operations**
12. **🧹 Clean as you go — no tech debt left behind**

---

## VERSION HISTORY

### v1.0 — 22 Mei 2026 (Neo)
Initial creation after deep audit revealed massive technical debt from past assumptions and ad-hoc development. Established as MANDATORY reading for all future agents.

---

**Pelanggaran terhadap aturan ini = pengulangan technical debt yang sama. JANGAN.**
