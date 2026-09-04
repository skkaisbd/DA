# FORENSIC AUDIT — 06: DESIGN SYSTEM AUDIT
## UI/Pattern Consistency Findings

**Lensa:** L10 Design System + L11 Naming Consistency + L12 Interaction Patterns

---

## 1. COMPONENT LIBRARY USAGE

### ✅ STRENGTH: Shadcn/UI Adoption
Sistem sudah menggunakan Shadcn/UI components secara konsisten:
- `Button`, `Input`, `Select`, `Dialog`, `Card`, `Table` — widely used
- `Sonner` toast notifications standardized
- `Command` palette implemented
- `Tabs`, `Accordion`, `Collapsible` — used in module dashboards
- `Form` + `Label` + validation — used in CRUD modules

### ⚠️ WEAKNESS: Custom Components Bertumpuk
- `DataTable.jsx` AND `DataTableV2.jsx` (2 generations!)
- `Modal.jsx` (custom) di samping Shadcn's `Dialog`
- `Combobox.jsx` + `SearchableSelect.jsx` (functionally overlap)
- Custom `IconButton.jsx`, `PaginationBar.jsx`, `StatusBadge.jsx`, `ExportButtonGroup.jsx` — banyak yang bisa di-replace dengan Shadcn equivalents

### Recommendation
- **DataTable**: Standardize to `DataTableV2`, deprecate v1
- **Modal**: Standardize to Shadcn's `Dialog`, deprecate custom
- **Combobox/SearchableSelect**: Pilih satu (prefer Shadcn `Combobox`)
- **IconButton**: Use Shadcn `Button variant=ghost size=icon` consistently

---

## 2. TABLE PATTERN CONSISTENCY

### Patterns Observed (5 different!)

#### Pattern A: Modules using `DataTable.jsx` (custom v1)
- Used in: ~30 older modules (e.g., InvoiceModule, PaymentModule)
- Features: Custom sort, pagination, filter
- Style: Slightly different padding/borders than Shadcn

#### Pattern B: Modules using `DataTableV2.jsx`
- Used in: ~50 newer modules (e.g., RahazaWorkOrdersModule, MaklonPOModule)
- Features: TanStack Table-based, more flexible
- Style: Closer to Shadcn aesthetic

#### Pattern C: Inline `<table>` with Shadcn `Table` primitive
- Used in: ~20 simple-display modules
- Features: No sort/filter, just rendering

#### Pattern D: Card-grid layout (no table)
- Used in: KOL leaderboard, KPI portal, dashboard cards
- Style: Card-based

#### Pattern E: TanStack Table direct (no wrapper)
- Used in: ~10 modules
- Maintainability concern

### Recommendation
- Standardize to **Pattern B (`DataTableV2`)** for all data lists
- Use **Pattern C** only for read-only display
- Use **Pattern D** only for dashboard widgets
- Deprecate Pattern A & E

---

## 3. MODAL/DIALOG PATTERN

### Inconsistencies
- Custom `Modal.jsx` (3 props pattern) vs Shadcn `Dialog` (composition)
- `ConfirmDialog.jsx` (custom wrapper) vs inline Shadcn `AlertDialog`
- Some modules use `Sheet` (side panel), some use `Dialog` (center modal) for same use case
- Drawer pattern (e.g., `TaskDetailDrawer.jsx`, `AuditHistoryDrawer.jsx`) inconsistently applied

### Recommendation
- **Confirm actions** → Shadcn `AlertDialog`
- **Form modals** → Shadcn `Dialog` (or `Sheet` for >5 fields)
- **Detail views** → `Sheet` (right side panel)
- **Tour/Help** → dedicated `Popover` or custom guide UI (existing `ModuleHelpDrawer`)

---

## 4. FILTER & SEARCH PATTERN

### 4+ Inconsistent Patterns

| Pattern | Used In | Issue |
|---------|---------|-------|
| Filter Chips (toggleable) | Marketing modules | Inconsistent with others |
| Dropdown Select Filter | Production/HR modules | Most common |
| Search bar + Type-ahead | Customer/Vendor pickers | Standard, OK |
| Date Range Picker | Finance/Reports | Custom implementations differ |
| Faceted Sidebar Filter | Inventory views | Limited usage |
| Tab-based filtering | Order status | OK but mixed with above |

### Recommendation
Define **standard filter bar component** that supports:
- Free-text search
- 1-3 dropdown filters
- Optional date range
- Optional faceted (chip-based) filters
- Standardize "Clear all" button position

---

## 5. FORM PATTERN

### Inconsistencies
- Field label position: Top vs Left (mixed)
- Required field indicator: `*` vs `(required)` text vs subtle border
- Error message position: Below field vs Tooltip vs Top of form
- Submit button placement: Bottom-right vs Bottom-center vs Top
- "Cancel" button styling: Outlined vs Ghost vs Link (inconsistent)

### Recommendation
- Adopt Shadcn `Form` + `FormField` + `FormMessage` pattern uniformly
- Always: Label top, error below, submit bottom-right, cancel ghost
- Required: subtle red `*` after label

---

## 6. STATUS BADGE / PILL PATTERN

### Current State
- `StatusBadge.jsx` custom component used in some modules
- Inline `<span>` with color classes in others
- Shadcn `Badge` used in newest modules

### Issue: Color Coding Inconsistent
- Green: Sometimes "completed", sometimes "in_progress"
- Orange/Yellow: Sometimes "pending", sometimes "warning"
- Red: Sometimes "error", sometimes "cancelled"

### Recommendation
Define **status badge palette** dengan semantic mapping:
```
Green      → Success / Completed / Active / Approved
Blue       → In Progress / Processing / Open
Orange     → Pending / Awaiting Action
Red        → Error / Rejected / Cancelled / Critical
Gray       → Inactive / Archived / Draft
Purple     → Special / Featured / VIP
```

---

## 7. ICONS

### ✅ STRENGTH
- Sistem konsisten menggunakan `lucide-react` icons
- Tidak menggunakan emoji sebagai icon UI

### ⚠️ MINOR ISSUE
- Beberapa section labels di sidebar pakai emoji prefix (`📊`, `⚡`, `👕`, `📅`)
  - Ini OK untuk readability, tapi inkonsisten antar portal
- Icon sizes mixed: `w-3 h-3`, `w-3.5 h-3.5`, `w-4 h-4`, `w-5 h-5` — standardize ke 3 sizes max

### Recommendation
- Section emoji: gunakan **konsisten di semua portal** ATAU hapus semua
- Icon size scale: `w-3.5 h-3.5` (small), `w-4 h-4` (default), `w-5 h-5` (large)

---

## 8. COLOR & THEME

### ✅ STRENGTH
- Design tokens defined via CSS variables (`--primary`, `--accent`, etc.)
- Theme toggle (light/dark) implemented
- Glass-morphism effects used appropriately

### ⚠️ ISSUE
- Some modules hardcode `text-blue-500`, `bg-red-100`, etc. instead of using tokens
- Toast notifications sometimes use default green/red instead of theme-aligned

### Recommendation
- Audit & replace hardcoded color classes dengan token references
- Sonner toasts: configure theme integration

---

## 9. LAYOUT INCONSISTENCY

### Module Container Patterns
Di-observe **3 layout patterns** yang berbeda:

#### Pattern X: Card-based
```jsx
<div className="p-6 space-y-6">
  <Card>...</Card>
  <Card>...</Card>
</div>
```

#### Pattern Y: Page-level
```jsx
<div className="container mx-auto py-8 px-4">
  ...
</div>
```

#### Pattern Z: Full-bleed
```jsx
<div className="h-full overflow-auto">
  <header>...</header>
  <main>...</main>
</div>
```

### Recommendation
- Adopt **Pattern Z** as standard for modules
- Card-based content INSIDE this layout
- Document layout guidelines

---

## 10. INTERACTION PATTERN AUDIT

### CRUD Patterns
- **Create:** Button "+ Tambah" / "+ New" — mostly consistent
- **Edit:** Pencil icon vs "Edit" text — mixed
- **Delete:** Trash icon — mostly consistent, but confirm dialog inconsistent
- **View Details:** Eye icon vs row click vs "Detail" button — mixed

### Bulk Actions
- Inconsistent: some tables have checkbox selection, some don't
- Bulk action toolbar appearance differs
- "Select all" behavior inconsistent

### Sort & Filter
- Column sort indicators differ (arrow vs chevron vs no indicator)
- Filter persistence: Some modules persist filters in URL, most don't

### Pagination
- Mostly uses custom `PaginationBar.jsx`
- Page size selector inconsistent
- "Showing X-Y of Z" text format varies

---

## 11. RESPONSIVENESS

### Issues
- Tables not responsive (horizontal scroll only)
- Forms don't switch to single-column on mobile uniformly
- Sidebar mobile experience uses select dropdown (functional but not optimal)
- Modals can overflow on mobile (no max-height)

---

## 12. ACCESSIBILITY (A11Y)

### ✅ GOOD
- `data-testid` widely used (helps with testability)
- ARIA labels on most interactive elements
- Keyboard navigation works (Tab, Enter)

### ⚠️ IMPROVEMENT NEEDED
- Color contrast: Some text/background combinations below WCAG AA
- Focus indicators inconsistent (some use ring, some opacity)
- Screen reader announcements for dynamic content (toasts, updates) not consistent

---

## 13. NAMING CONSISTENCY (L11)

### Critical Inconsistencies

#### A. Indonesian vs English mix
- Sidebar labels: 90% Indonesian, 10% English ("Dashboard", "Approval Inbox", "Onboarding")
- Internal field names: Mostly English (`employee_id`, `created_at`)
- API params: Mostly English

**Recommendation:** Keep UI labels in Indonesian, internal code in English. OK.

#### B. Domain Terminology
- "Master Material" vs "Bahan Baku" vs "Material" (3 terms for same)
- "Order" vs "PO" vs "Pesanan" (3 terms)
- "Work Order" vs "WO" vs "Pekerjaan" (mixed)
- "CMT" vs "Maklon" (distinct concepts but often confused)

**Recommendation:** Define **glossary** dan apply uniformly.

#### C. ID Prefix Chaos
- `rahaza_` (PT Rahaza legacy)
- `dewi_` (CV. Dewi Aditya)
- `da_` (Dewi Aditya short)
- `wh_` (Warehouse)
- `wms_` (WMS)
- `acc_` (Accessory)
- `marketing_` (Marketing)
- `hr_` `hris_` (HR)
- No prefix (legacy generic)

**Recommendation:** Long-term, phase to domain-based prefix:
- `production_*`
- `inventory_*`
- `finance_*`
- `hr_*`
- `marketing_*`
- `maklon_*`
- `system_*`

---

## 14. DESIGN SYSTEM HEALTH SCORE

| Aspect | Score | Note |
|--------|-------|------|
| Component Library Usage | 7/10 | Shadcn adopted, but custom overlap exists |
| Table Patterns | 5/10 | 5 patterns coexisting |
| Modal/Dialog | 6/10 | 2 systems (custom + Shadcn) |
| Forms | 6/10 | Inconsistent label/error placement |
| Status Badges | 5/10 | Color semantics not standardized |
| Icons | 8/10 | Lucide consistent, sizes vary |
| Color/Theme | 7/10 | Tokens defined, some hardcodes remain |
| Layout | 6/10 | 3 layout patterns coexist |
| Interaction | 6/10 | CRUD OK, bulk action inconsistent |
| Responsiveness | 4/10 | Tables not mobile-friendly |
| Accessibility | 6/10 | Good test IDs, contrast issues |
| Naming | 5/10 | Mix prefix, mix terminology |

**Overall Design System Health: 5.9/10**

---

## 15. ACTION PLAN

### P0 (1 hari)
1. Audit & replace hardcoded color classes → use design tokens
2. Standardize status badge semantic colors
3. Fix Sonner toast theme integration

### P1 (1 minggu)
4. Deprecate custom `Modal.jsx` → migrate to Shadcn `Dialog`
5. Deprecate `DataTable.jsx` v1 → migrate 30 modules to V2
6. Standardize filter bar component
7. Standardize form layout (label top, error below)

### P2 (2 minggu)
8. Implement responsive table cards untuk mobile
9. Document & enforce naming glossary
10. Improve accessibility contrast issues
11. Standardize pagination component

### P3 (Long-term)
12. Phase out namespace prefixes (rahaza_, dewi_) → domain-based
13. Build Storybook untuk semua design system components
