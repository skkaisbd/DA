# 🔄 SYSTEM FLOW DIAGRAM - PORTAL PRODUKSI & MAKLON

## CV. Dewi Aditya ERP System - Visual Flow Documentation

---

## 📊 HIGH-LEVEL SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         CV. DEWI ADITYA ERP SYSTEM                              │
│                              (Full-Stack Architecture)                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
          ┌─────────▼──────────┐              ┌──────────▼─────────┐
          │   FRONTEND (React)  │              │  BACKEND (FastAPI) │
          │   ----------------  │              │  ---------------   │
          │   • Portal Shell    │◄────REST────►│  • MongoDB Motor   │
          │   • Tailwind UI     │   API/JSON   │  • Pydantic Models │
          │   • Shadcn/UI       │              │  • JWT Auth        │
          │   • State Management│              │  • Business Logic  │
          └─────────────────────┘              └────────┬───────────┘
                                                        │
                                                        │
                                              ┌─────────▼────────┐
                                              │  MongoDB Atlas   │
                                              │  --------------  │
                                              │  • Collections   │
                                              │  • Indexes       │
                                              │  • Transactions  │
                                              └──────────────────┘
```

---

## 🏭 FLOW 1: PRODUKSI INTERNAL (END-TO-END)

### A. ORDER TO PRODUCTION

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        ORDER TO PRODUCTION FLOW                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

SALES ORDER                    PRODUCTION ORDER               WORK ORDER
(Customer)                     (Planning)                     (Execution)
    │                              │                              │
    │  1. Customer PO              │                              │
    ├──────────────►│              │                              │
    │               │  2. Create   │                              │
    │               │     PO       │                              │
    │               ├──────────────►│                              │
    │               │              │  3. BOM Check                │
    │               │              ├──────────┐                   │
    │               │              │          │ Material          │
    │               │              │◄─────────┘ Available?        │
    │               │              │                              │
    │               │              │  4. Material Reservation     │
    │               │              ├──────────────────────┐       │
    │               │              │                      │       │
    │               │              │  5. Create WO        ▼       │
    │               │              ├────────────────►[Warehouse]  │
    │               │              │                      │       │
    │               │              │◄─────────────────────┘       │
    │               │              │     Material Issued          │
    │               │              │                              │
    │               │              │  6. WO → Production Floor    │
    │               │              ├──────────────────────────────►│
    │               │              │                              │
    │               │              │                         [PRODUCTION]
    │               │              │                         Cutting
    │               │              │                            ↓
    │               │              │                         Sewing
    │               │              │                            ↓
    │               │              │                        Finishing
    │               │              │                            ↓
    │               │              │                        QC Final
    │               │              │                            ↓
    │               │              │                         Packing
    │               │              │                            ↓
    │               │              │◄─────────────────────[FG Complete]
    │               │              │
    │               │◄─────────────┤  7. PO Status: COMPLETED
    │               │              │
    │◄──────────────┤  8. Ready    │
    │               │     to Ship  │
    [DELIVERY]      │              │
```

### B. PRODUCTION FLOOR EXECUTION (4 STAGES)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    PRODUCTION FLOOR - 4 STAGE PROCESS                           │
└─────────────────────────────────────────────────────────────────────────────────┘

MATERIAL         STAGE 1          STAGE 2          STAGE 3         STAGE 4
READY            CUTTING          SEWING           FINISHING       QC & PACKING
  │                │                │                │                │
  │  Fabric        │                │                │                │
  │  Accessories   │                │                │                │
  │  Issued        │                │                │                │
  ├────────────────►│                │                │                │
  │                │                │                │                │
  │                │  1. Lay Plan   │                │                │
  │                │  2. Marker     │                │                │
  │                │  3. Cut Fabric │                │                │
  │                │  4. Bundle Gen │                │                │
  │                ├────────────────►│                │                │
  │                │                │                │                │
  │                │                │  1. Assign     │                │
  │                │                │     Line       │                │
  │                │                │  2. Sew        │                │
  │                │                │  3. Attach     │                │
  │                │                │     Component  │                │
  │                │                ├────────────────►│                │
  │                │                │                │                │
  │                │                │                │  1. Steam/Iron │
  │                │                │                │  2. Trim       │
  │                │                │                │  3. Label/Tag  │
  │                │                ├────────────────►│                │
  │                │                │                │                │
  │                │                │                │  1. QC Inspect │
  │                │                │                │  2. Defect Log │
  │                │                │                │  3. Pack       │
  │                │                │                │  4. Label      │
  │                │                │                │                │
  │                │                │                │◄───Rework?     │
  │                │                │                │    (if fail)   │
  │                │                │◄───────────────┤                │
  │                │                │                │                │
  │                │                │                │                ▼
  │                │                │                │           [Warehouse]
  │                │                │                │           FG Stored
  │                │                │                │                │
  └────────────────┴────────────────┴────────────────┴────────────────┘
                                                                      │
                                                                      ▼
                                                              [Ready for Shipment]
```

### C. REAL-TIME MONITORING & ALERTS

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      MONITORING & ALERT SYSTEM                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

 PRODUCTION FLOOR                MONITORING LAYER              STAKEHOLDER
 ----------------                ----------------              -----------
      │                                │                            │
      │  Real-time Progress            │                            │
      ├────────────────────────────────►│                            │
      │                                │  Dashboard Update          │
      │                                │  KPI Calculation           │
      │                                │                            │
      │  Andon Alert                   │                            │
      │  (Quality/Machine/Material)    │                            │
      ├────────────────────────────────►│                            │
      │                                │  Alert Threshold Check     │
      │                                │                            │
      │                                │  ✓ Critical Alert          │
      │                                ├────────────────────────────►│
      │                                │  SMS / Push Notification   │
      │                                │                     [Manager]
      │                                │                            │
      │  Downtime Event                │                            │
      ├────────────────────────────────►│                            │
      │                                │  Log & Calculate OEE       │
      │                                │                            │
      │  Quality Defect                │                            │
      ├────────────────────────────────►│                            │
      │                                │  Pareto Update             │
      │                                │  FPY Calculation           │
      │                                │                            │
      │                                │  Predictive Maintenance    │
      │                                │  AI Alert                  │
      │                                ├────────────────────────────►│
      │                                │                  [Maintenance]
      │                                │                            │
```

---

## 🏢 FLOW 2: MAKLON BUSINESS (TOLL MANUFACTURING)

### A. COMPLETE MAKLON FLOW

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        COMPLETE MAKLON BUSINESS FLOW                            │
└─────────────────────────────────────────────────────────────────────────────────┘

CLIENT                DA MAKLON              PRODUCTION           FINANCE
  │                      │                       │                   │
  │  1. Sample Request   │                       │                   │
  ├──────────────────────►│                       │                   │
  │                      │  RnD Create Sample    │                   │
  │                      ├───────────────────────►│                   │
  │                      │                       │                   │
  │◄─────────────────────┤  2. Send Sample       │                   │
  │  Approve/Revise      │                       │                   │
  ├──────────────────────►│                       │                   │
  │                      │                       │                   │
  │  3. Issue PO Maklon  │                       │                   │
  │     (Artikel, Qty,   │                       │                   │
  │      CMT Rate)       │                       │                   │
  ├──────────────────────►│                       │                   │
  │                      │  Create PO Record     │                   │
  │                      │  Status: DRAFT        │                   │
  │                      │                       │                   │
  │  4. Send Material    │                       │                   │
  │     (Fabric +        │                       │                   │
  │      Accessories)    │                       │                   │
  ├──────────────────────►│                       │                   │
  │                      │  Warehouse Receive    │                   │
  │                      │  & Inspect Material   │                   │
  │                      │                       │                   │
  │                      │  5. Confirm PO        │                   │
  │                      │     Status: CONFIRMED │                   │
  │                      │                       │                   │
  │                      │  6. Auto Create WO    │                   │
  │                      ├───────────────────────►│                   │
  │                      │                       │                   │
  │                      │                       │  Production       │
  │                      │                       │  Execution        │
  │                      │                       │  (4 Stages)       │
  │                      │                       │                   │
  │                      │◄──────────────────────┤  7. FG Ready      │
  │                      │  Status: IN_PRODUCTION│                   │
  │                      │                       │                   │
  │                      │  8. Packing &         │                   │
  │                      │     Dispatch (Partial │                   │
  │                      │     or Full)          │                   │
  │◄─────────────────────┤                       │                   │
  │  Delivery Note       │                       │                   │
  │                      │                       │                   │
  │                      │  9. Generate Invoice  │                   │
  │                      │     (Qty × CMT Rate)  │                   │
  │                      ├───────────────────────────────────────────►│
  │◄─────────────────────┤  Send Invoice         │                   │
  │                      │                       │                   │
  │  10. Payment         │                       │                   │
  ├──────────────────────►│                       │                   │
  │                      ├───────────────────────────────────────────►│
  │                      │  Post AR to GL        │                   │
  │                      │  Status: INVOICED     │                   │
  │                      │                       │                   │
```

### B. MULTI-DISPATCH FLOW (FLEXIBLE PARTIAL DELIVERY)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        MULTI-DISPATCH FLOW EXAMPLE                              │
│                    PO Total: 1000 pcs | CMT Rate: Rp 15,000                    │
└─────────────────────────────────────────────────────────────────────────────────┘

TIME        PO STATUS             DISPATCH EVENT              INVOICE
────        ─────────             ──────────                  ───────
Day 0       CONFIRMED             -                           -
            Total: 1000 pcs
            Delivered: 0 pcs
            │
            │
Day 15      IN_PRODUCTION         Dispatch #1                 Invoice #1
            │                     Qty: 300 pcs                Rp 4,500,000
            │                     ────────────►               (300 × 15,000)
            │
            ├─► Status: PARTIAL_DELIVERED
            │   Delivered: 300 pcs
            │   Remaining: 700 pcs
            │
            │
Day 22      IN_PRODUCTION         Dispatch #2                 Invoice #2
            │                     Qty: 450 pcs                Rp 6,750,000
            │                     ────────────►               (450 × 15,000)
            │
            ├─► Status: PARTIAL_DELIVERED
            │   Delivered: 750 pcs
            │   Remaining: 250 pcs
            │
            │
Day 28      IN_PRODUCTION         Dispatch #3 (Final)         Invoice #3
            │                     Qty: 250 pcs                Rp 3,750,000
            │                     ────────────►               (250 × 15,000)
            │
            └─► Status: COMPLETED
                Delivered: 1000 pcs
                Remaining: 0 pcs
                                                              ───────────────
                                                              Total Invoiced:
                                                              Rp 15,000,000
```

### C. MAKLON WITH CMT VENDOR (SUB-CONTRACT)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   MAKLON + CMT VENDOR SUB-CONTRACT FLOW                         │
└─────────────────────────────────────────────────────────────────────────────────┘

CLIENT          DA MAKLON           VENDOR CMT          DA PRODUCTION
  │                │                     │                     │
  │  PO Maklon     │                     │                     │
  ├────────────────►│                     │                     │
  │                │  WO Created         │                     │
  │                │  Total: 1000 pcs    │                     │
  │                │                     │                     │
  │                │  Decision:          │                     │
  │                │  - 600 pcs Internal │                     │
  │                │  - 400 pcs to CMT   │                     │
  │                │                     │                     │
  │                │  Dispatch to CMT    │                     │
  │                │  (Material + Cut)   │                     │
  │                ├─────────────────────►│                     │
  │                │                     │  Sewing +           │
  │                │                     │  Finishing          │
  │                │                     │                     │
  │                │  Internal WO        │                     │
  │                ├─────────────────────────────────────────►│
  │                │                     │                     │
  │                │                     │  Production         │
  │                │                     │  (600 pcs)          │
  │                │                     │                     │
  │                │◄────────────────────┤  CMT Return         │
  │                │  400 pcs Completed  │  (400 pcs)          │
  │                │  + QC Inspection    │                     │
  │                │                     │                     │
  │                │◄────────────────────────────────────────┤│
  │                │  600 pcs Internal   │                     │
  │                │  Completed          │                     │
  │                │                     │                     │
  │                │  Combine & Pack     │                     │
  │                │  Total: 1000 pcs    │                     │
  │◄───────────────┤                     │                     │
  │  Full Delivery │                     │                     │
  │                │                     │                     │
  │                │  Pay Vendor CMT     │                     │
  │                ├─────────────────────►│                     │
  │                │  (400 × vendor rate)│                     │
  │                │                     │                     │
```

---

## 🔄 FLOW 3: DATA INTEGRATION FLOWS

### A. WAREHOUSE ↔ PRODUCTION INTEGRATION

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    WAREHOUSE ↔ PRODUCTION INTEGRATION                           │
└─────────────────────────────────────────────────────────────────────────────────┘

PRODUCTION                              WAREHOUSE
    │                                       │
    │  1. Material Reservation Request      │
    │     (WO created)                      │
    ├───────────────────────────────────────►│
    │                                       │  Check Stock
    │                                       │  ├─ Available? Reserve
    │                                       │  └─ Not enough? Alert
    │◄──────────────────────────────────────┤
    │  Reservation Confirmed                │
    │                                       │
    │  2. Material Issue Request            │
    │     (Production start)                │
    ├───────────────────────────────────────►│
    │                                       │  Pick Material
    │                                       │  Update Stock (-)
    │                                       │  Generate GIN
    │◄──────────────────────────────────────┤
    │  Material Issued                      │
    │                                       │
    │  [PRODUCTION PROCESS]                 │
    │                                       │
    │  3. Material Return (Unused)          │
    ├───────────────────────────────────────►│
    │                                       │  QC Return Material
    │                                       │  Update Stock (+)
    │                                       │
    │  4. FG Transfer                       │
    │     (Production completed)            │
    ├───────────────────────────────────────►│
    │                                       │  Receive FG
    │                                       │  Update FG Stock (+)
    │                                       │  Store in FG Location
    │                                       │
```

### B. MAKLON ↔ FINANCE INTEGRATION

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      MAKLON ↔ FINANCE INTEGRATION                               │
└─────────────────────────────────────────────────────────────────────────────────┘

MAKLON MODULE                          FINANCE MODULE
    │                                       │
    │  1. PO Confirmed                      │
    │     - Client: PT ABC                  │
    │     - Total Value: Rp 15,000,000      │
    ├───────────────────────────────────────►│
    │                                       │  No GL posting yet
    │                                       │  (until delivery)
    │                                       │
    │  2. Dispatch Event                    │
    │     - Qty delivered: 1000 pcs         │
    │     - CMT Rate: Rp 15,000             │
    │     - Total: Rp 15,000,000            │
    ├───────────────────────────────────────►│
    │                                       │  Auto Generate Invoice:
    │                                       │  ┌─────────────────────┐
    │                                       │  │ AR Invoice #INV001  │
    │                                       │  │ Amount: 15,000,000  │
    │                                       │  │ Tax: 1,650,000      │
    │                                       │  │ Total: 16,650,000   │
    │                                       │  └─────────────────────┘
    │                                       │
    │                                       │  Post to GL:
    │                                       │  DR: Account Receivable  16,650,000
    │                                       │  CR: CMT Revenue         15,000,000
    │                                       │  CR: VAT Payable          1,650,000
    │                                       │
    │  3. Payment Received                  │
    │     - Bank Transfer                   │
    │     - Amount: Rp 16,650,000           │
    ├───────────────────────────────────────►│
    │                                       │  Post to GL:
    │                                       │  DR: Bank                16,650,000
    │                                       │  CR: Account Receivable  16,650,000
    │                                       │
    │                                       │  Update AR Aging
    │                                       │  Mark Invoice: PAID
    │◄──────────────────────────────────────┤
    │  PO Status: INVOICED & PAID           │
    │                                       │
```

### C. PRODUCTION ↔ HR INTEGRATION

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       PRODUCTION ↔ HR INTEGRATION                               │
└─────────────────────────────────────────────────────────────────────────────────┘

PRODUCTION                                HR MODULE
    │                                       │
    │  1. Line Assignment Needed            │
    │     - Line: Line A                    │
    │     - Required: 15 operators          │
    │     - Shift: Morning (07:00-15:00)    │
    ├───────────────────────────────────────►│
    │                                       │  Query Operators:
    │                                       │  - Available?
    │                                       │  - Shift match?
    │                                       │  - Skill match?
    │◄──────────────────────────────────────┤
    │  Operator List with Skills            │
    │                                       │
    │  2. Production Output Recorded        │
    │     - Operator ID: EMP001             │
    │     - Output: 85 pcs                  │
    │     - Quality: 2 defects              │
    │     - Hours: 8 hrs                    │
    ├───────────────────────────────────────►│
    │                                       │  Update Performance:
    │                                       │  - Productivity score
    │                                       │  - Quality score
    │                                       │  - Hours worked
    │                                       │
    │                                       │  Payroll Calculation:
    │                                       │  - Piece rate: 85 × Rp 500
    │                                       │  - Quality bonus
    │                                       │
    │  3. Overtime Request                  │
    │     - Line: Line A                    │
    │     - Duration: 2 hours               │
    │     - Reason: Rush order              │
    ├───────────────────────────────────────►│
    │                                       │  Approval Workflow
    │◄──────────────────────────────────────┤
    │  Overtime Approved                    │
    │  + Overtime rate                      │
    │                                       │
```

---

## 📱 EXTERNAL PORTAL FLOWS

### A. CLIENT PORTAL (MAKLON CUSTOMER)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          CLIENT PORTAL FLOW                                     │
└─────────────────────────────────────────────────────────────────────────────────┘

CLIENT (Web Browser)              DA BACKEND                  EMAIL/SMS
    │                                 │                           │
    │  1. Login                       │                           │
    ├─────────────────────────────────►│                           │
    │                                 │  Authenticate             │
    │◄────────────────────────────────┤                           │
    │  Dashboard                      │                           │
    │  - My POs                       │                           │
    │  - Production Status            │                           │
    │  - Invoices                     │                           │
    │                                 │                           │
    │  2. View PO Details             │                           │
    │     (PO #12345)                 │                           │
    ├─────────────────────────────────►│                           │
    │◄────────────────────────────────┤                           │
    │  PO 360° View:                  │                           │
    │  - Items breakdown              │                           │
    │  - Production progress: 65%     │                           │
    │  - Estimated completion: 5 days │                           │
    │  - Photos (if any)              │                           │
    │                                 │                           │
    │  3. Sample Approval             │                           │
    │     ✓ Approve / ✗ Revise       │                           │
    ├─────────────────────────────────►│                           │
    │                                 │  Update Sample Status     │
    │                                 ├───────────────────────────►│
    │                                 │  Notify DA: Sample Approved
    │                                 │                           │
    │  4. Download Invoice            │                           │
    │     (Invoice #INV001)           │                           │
    ├─────────────────────────────────►│                           │
    │◄────────────────────────────────┤                           │
    │  PDF Invoice                    │                           │
    │                                 │                           │
    │  5. Message / Support           │                           │
    │     "Need to change deadline"   │                           │
    ├─────────────────────────────────►│                           │
    │                                 │  Create Support Ticket    │
    │                                 ├───────────────────────────►│
    │                                 │  Notify Account Manager   │
    │                                 │                           │
```

### B. VENDOR CMT PORTAL

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        VENDOR CMT PORTAL FLOW                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

VENDOR (Mobile/Web)               DA BACKEND                  DA PRODUCTION
    │                                 │                           │
    │  1. Login (Vendor ID)           │                           │
    ├─────────────────────────────────►│                           │
    │◄────────────────────────────────┤                           │
    │  Vendor Dashboard               │                           │
    │  - Active WOs                   │                           │
    │  - Pending Deliveries           │                           │
    │  - Payment Status               │                           │
    │                                 │                           │
    │  2. View WO Assignment          │                           │
    │     (WO #5678)                  │                           │
    ├─────────────────────────────────►│                           │
    │◄────────────────────────────────┤                           │
    │  WO Details:                    │                           │
    │  - Artikel: ABC-001             │                           │
    │  - Qty: 500 pcs                 │                           │
    │  - Rate: Rp 12,000/pcs          │                           │
    │  - Deadline: 10 days            │                           │
    │  - Tech Pack (download)         │                           │
    │                                 │                           │
    │  3. Request Component           │                           │
    │     "Need 20 pcs zipper"        │                           │
    ├─────────────────────────────────►│                           │
    │                                 │  Create Component Request │
    │                                 ├───────────────────────────►│
    │                                 │  Approval workflow        │
    │◄────────────────────────────────┤                           │
    │  Request Approved               │                           │
    │  Estimated dispatch: Tomorrow   │                           │
    │                                 │                           │
    │  4. Upload Progress             │                           │
    │     - Cutting: 100% ✓           │                           │
    │     - Sewing: 60%               │                           │
    │     - Photo evidence            │                           │
    ├─────────────────────────────────►│                           │
    │                                 │  Update WO Progress       │
    │                                 ├───────────────────────────►│
    │                                 │  Real-time dashboard      │
    │                                 │                           │
    │  5. Report Completion           │                           │
    │     + Upload QC photos          │                           │
    ├─────────────────────────────────►│                           │
    │                                 │  Trigger DA Inspection    │
    │◄────────────────────────────────┤                           │
    │  Awaiting DA pickup             │                           │
    │                                 │                           │
```

---

## 🎯 DECISION FLOW

### A. CAPACITY ALLOCATION DECISION

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     CAPACITY ALLOCATION DECISION TREE                           │
└─────────────────────────────────────────────────────────────────────────────────┘

                            New Order Received
                                    │
                                    ▼
                        ┌─────────────────────┐
                        │  Check Available    │
                        │  Capacity           │
                        └──────────┬──────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                 YES│                             │NO
                    ▼                             ▼
        ┌───────────────────┐         ┌──────────────────────┐
        │ Internal or       │         │ Options:             │
        │ Maklon Order?     │         │ 1. Reject            │
        └────────┬──────────┘         │ 2. Extend lead time  │
                 │                     │ 3. Sub-contract CMT  │
      ┌──────────┴────────┐           │ 4. Add OT shift      │
      │                   │           └──────────────────────┘
   INTERNAL           MAKLON
      │                   │
      ▼                   ▼
┌──────────┐     ┌──────────────┐
│ Priority │     │ CMT Rate     │
│ HIGH     │     │ Evaluation   │
└──────────┘     └──────┬───────┘
      │                 │
      │           ┌─────┴─────┐
      │       GOOD│           │LOW
      │           ▼           ▼
      │    ┌──────────┐  ┌────────┐
      │    │ Accept   │  │ Reject │
      │    │ Maklon   │  │ or     │
      │    │ Order    │  │ Re-    │
      │    └──────────┘  │ quote  │
      │                  └────────┘
      │
      └────────────┬──────────────────┐
                   │                  │
         ┌─────────▼──────┐  ┌────────▼────────┐
         │ Produce        │  │ Sub-contract    │
         │ Internally     │  │ to CMT Vendor   │
         └────────────────┘  └─────────────────┘
```

### B. QUALITY DECISION FLOW

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         QC INSPECTION DECISION TREE                             │
└─────────────────────────────────────────────────────────────────────────────────┘

                        Garment at QC Station
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Visual Inspection    │
                    │  (Major/Minor/Critical│
                    │   Defects)            │
                    └───────────┬───────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
           CRITICAL          MAJOR           MINOR
            DEFECT          DEFECT          DEFECT
                │               │               │
                ▼               ▼               ▼
        ┌───────────┐   ┌──────────────┐  ┌──────────────┐
        │  REJECT   │   │  Can repair? │  │  Repairable? │
        │  (Scrap)  │   └──────┬───────┘  └──────┬───────┘
        └───────────┘          │                  │
                          ┌────┴────┐        ┌────┴────┐
                       YES│         │NO    YES│         │NO
                          ▼         ▼         ▼         ▼
                    ┌─────────┐ ┌──────┐ ┌──────┐ ┌──────┐
                    │ REWORK  │ │REJECT│ │ PASS │ │REJECT│
                    │ (Max 2x)│ │      │ │ with │ │      │
                    └─────────┘ └──────┘ │ note │ └──────┘
                          │                └──────┘
                          │                   │
                          └───────┬───────────┘
                                  │
                                  ▼
                          ┌──────────────┐
                          │  Log Defect  │
                          │  in System   │
                          └──────┬───────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │ Update:        │
                        │ - Pareto chart │
                        │ - FPY metric   │
                        │ - Operator KPI │
                        └────────────────┘
```

---

## 🔐 AUTHENTICATION & AUTHORIZATION FLOW

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      USER AUTHENTICATION & PORTAL ACCESS                        │
└─────────────────────────────────────────────────────────────────────────────────┘

USER                       AUTH SERVICE                PORTAL SELECTION
  │                            │                            │
  │  1. Login (Email/Pass)     │                            │
  ├────────────────────────────►│                            │
  │                            │  Verify Credentials        │
  │                            │  ├─ LDAP / DB Auth         │
  │                            │  └─ Generate JWT Token     │
  │◄───────────────────────────┤                            │
  │  JWT Token + User Profile  │                            │
  │                            │                            │
  │  2. Request Portal Access  │                            │
  ├─────────────────────────────────────────────────────────►│
  │                            │                            │  Check Role:
  │                            │                            │  - Production Manager
  │                            │                            │  - Maklon Sales
  │                            │                            │  - QC Inspector
  │                            │                            │  - etc.
  │◄────────────────────────────────────────────────────────┤
  │  Allowed Portals:          │                            │
  │  ✓ Production              │                            │
  │  ✓ Maklon                  │                            │
  │  ✗ Finance (No access)     │                            │
  │                            │                            │
  │  3. Select Portal          │                            │
  ├─────────────────────────────────────────────────────────►│
  │                            │                            │  Load Portal
  │◄────────────────────────────────────────────────────────┤  with Role-
  │  Portal Interface          │                            │  based Menu
  │  (Filtered by Permission)  │                            │
  │                            │                            │
```

---

**Document Created by**: Neo AI Agent  
**Last Updated**: 2 Juni 2026  
**Version**: 1.0  
**Related Documents**: BUSINESS_PROCESS_PRODUKSI_MAKLON.md

