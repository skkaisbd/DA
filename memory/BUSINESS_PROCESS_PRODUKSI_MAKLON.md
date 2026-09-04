# 📋 BUSINESS PROCESS - PORTAL PRODUKSI & MAKLON
## CV. Dewi Aditya ERP System

---

## 🎯 RINGKASAN EKSEKUTIF

CV. Dewi Aditya adalah perusahaan garmen yang menjalankan **dua model bisnis utama**:

1. **Produksi Internal (Portal Produksi)** - Produksi produk brand sendiri (Rahaza)
2. **Maklon (Toll Manufacturing)** - Produksi untuk klien eksternal dengan sistem CMT (Cut, Make, Trim)

Kedua portal ini terintegrasi penuh dengan sistem Warehouse, Finance, HR, dan module lainnya dalam satu ekosistem ERP yang komprehensif.

---

## 🏭 PORTAL PRODUKSI (INTERNAL PRODUCTION)

### 📌 OVERVIEW
Portal Produksi mengelola seluruh siklus produksi garmen untuk brand internal perusahaan (Rahaza), mulai dari perencanaan hingga pengiriman ke customer.

### 🔄 ALUR BISNIS PROSES PRODUKSI

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ALUR BISNIS PRODUKSI INTERNAL                        │
└─────────────────────────────────────────────────────────────────────────┘

1. PERENCANAAN
   ├─ Production Order (PO) dibuat dari Sales Order
   ├─ BOM (Bill of Materials) sudah didefinisikan di Product Master
   └─ Material Reservation untuk memastikan stok tersedia

2. PENJADWALAN & PERSIAPAN
   ├─ Work Order (WO) dibuat dari PO
   ├─ Capacity Planning - Alokasi Line & Operator
   ├─ Material Issue - Gudang mengeluarkan material ke produksi
   └─ Production Wizard - Quick setup untuk batch production

3. EKSEKUSI PRODUKSI (4 TAHAP UTAMA)
   │
   ├─ TAHAP 1: CUTTING
   │  ├─ Cutting Hub - Planning & Execution
   │  ├─ Marker & Lay Planning
   │  ├─ Fabric Cutting (Potong Kain)
   │  └─ Bundle Creation - Bundel untuk tracking per batch
   │
   ├─ TAHAP 2: SEWING / CMT (Cut, Make, Trim)
   │  ├─ Assign ke Line Produksi (Line Assignment)
   │  ├─ Operator melakukan jahit sesuai SOP
   │  ├─ Input real-time progress (Shift Handover)
   │  ├─ Rework Management jika ada cacat
   │  └─ Live Monitoring - Real-time dashboard
   │
   ├─ TAHAP 3: FINISHING
   │  ├─ Steam / Iron
   │  ├─ Trimming (potong benang)
   │  ├─ Label & Tag attachment
   │  └─ Final inspection minor defects
   │
   └─ TAHAP 4: QC & PACKING
      ├─ QC Final (100% atau AQL Sampling)
      ├─ Defect Recording (Pareto Analysis)
      ├─ Packing sesuai buyer requirement
      └─ FG (Finished Goods) masuk ke Warehouse

4. QUALITY CONTROL & MONITORING
   ├─ Andon Board - Real-time issue alerts
   ├─ Pareto Analysis - Defect trending
   ├─ First Pass Yield (FPY) tracking
   ├─ AQL Sampling Calculator
   └─ Downtime Logging

5. ALTERNATIVE FLOW: CMT EXTERNAL
   ├─ Jika kapasitas internal tidak cukup
   ├─ Material + Cutting dikirim ke Vendor CMT
   ├─ Vendor CMT melakukan jahit & finishing
   ├─ CMT Packing & Opname saat return ke DA
   ├─ Component Request jika ada kekurangan
   └─ Final QC di DA warehouse

6. COMPLETION & DELIVERY
   ├─ FG Stock masuk Warehouse
   ├─ Fulfillment Module - Pick, Pack, Ship
   ├─ Delivery Note (Surat Jalan) dibuat
   ├─ Customer delivery
   └─ Production Order Status = COMPLETED
```

### 📊 MODULE UTAMA PORTAL PRODUKSI

#### A. OPERASIONAL HARIAN

**1. Dashboard Produksi**
   - Live metrics: WO progress, line efficiency, defect rate
   - Daily production summary
   - Critical alerts & bottlenecks

**2. Control Tower**
   - Bird's eye view seluruh lantai produksi
   - Real-time status semua WO
   - Resource utilization

**3. Production Wizard** ⚡
   - Quick setup untuk batch production
   - Automatic WO creation
   - Bulk Material Issue
   - Simplified workflow untuk operator

**4. Input Harian Sederhana** 🆕
   - Simplified daily input untuk non-technical user
   - Quick progress update per line
   - Mobile-friendly interface

**5. Order & Penjadwalan**
   - **Production Orders** - Master production planning
   - **Work Orders** - Executable tasks per line/operator
   - **Bundle Tracking** - Trace garment dari cutting - packing
   - **Material Reservation** - Lock material untuk WO tertentu
   - **Material Returns** - Return unused material ke warehouse

#### B. EKSEKUSI LANTAI PRODUKSI

**6. Cutting Hub** 🔪
   - Cutting Planning (marker, lay, fabric requirement)
   - Cutting Execution & Bundle Generation
   - Fabric wastage tracking
   - Integration dengan Material Issue

**7. Line Assignment & Shift**
   - Assign operator ke line harian
   - Shift handover documentation
   - Operator skill matrix matching
   - Real-time staffing dashboard

**8. Rework Management**
   - Rework board untuk tracking defect items
   - Root cause analysis
   - Re-inspection flow
   - Scrap vs repairable classification

#### C. PROSES 4 TAHAP

**9. Sewing / CMT (Tahap 1)**
   - Input progress per bundle
   - Operator performance tracking
   - Machine downtime logging
   - Output quantity vs target

**10. Finishing (Tahap 2)**
   - Steam, iron, trimming
   - Label & tag attachment
   - Minor defect fixing
   - Presentation quality check

**11. QC Final (Tahap 3)**
   - Inspection protocols (100% or AQL)
   - Defect code recording
   - Pass / Fail / Rework decision
   - FPY (First Pass Yield) calculation

**12. Packing (Tahap 4)**
   - Packing list generation
   - Carton labeling
   - Barcode / QR code printing
   - FG transfer ke warehouse

#### D. CMT EXTERNAL MANAGEMENT

**13. CMT Vendor Management**
   - Vendor master data
   - Capacity & capability tracking
   - Quality scorecard
   - Payment terms

**14. CMT Lifecycle Dashboard**
   - Track DO (Delivery Order) ke CMT
   - WIP at CMT location
   - Expected return date
   - Aging analysis

**15. CMT Progress Tracking**
   - Real-time status dari vendor
   - Quality issues reported
   - Partial delivery management

**16. CMT Packing & Opname**
   - Receiving inspection dari CMT
   - Quantity reconciliation
   - Quality acceptance
   - Payment trigger

**17. Component Request Management**
   - CMT request missing accessories
   - Approval workflow
   - Dispatch tracking
   - Cost reconciliation

#### E. MONITORING & ANALYTICS

**18. Live Monitoring Dashboard**
   - Real-time line output
   - Efficiency % per line
   - Bottleneck identification
   - Predictive alerts

**19. Andon Board** 🚨
   - Real-time issue signaling
   - Quality stop
   - Machine breakdown
   - Material shortage

**20. Pareto Analysis**
   - Top defect types ranking
   - Defect by style / line / operator
   - Trend analysis
   - Corrective action tracking

**21. FPY (First Pass Yield)**
   - Quality efficiency metric
   - Benchmark against target
   - Improvement tracking

**22. Downtime Logging**
   - Machine breakdown duration
   - Root cause categories
   - Maintenance schedule compliance
   - OEE (Overall Equipment Effectiveness)

**23. Backlog & Forecast**
   - Pending orders
   - Production capacity vs demand
   - Lead time estimation
   - Resource bottleneck identification

**24. Capacity Planning**
   - Line capacity simulation
   - Operator requirement forecast
   - Machine utilization optimization

**25. AI Insights & Chatbot** 🤖
   - Production performance insights
   - Natural language queries
   - Anomaly detection
   - Optimization recommendations

**26. Predictive Maintenance** 🤖
   - Machine failure prediction
   - Optimal maintenance scheduling
   - Spare parts planning

#### F. MASTER DATA

**27. Workspace Master**
   - Production line definitions
   - Machine catalog
   - Workstation layout

**28. Production Processes & SOP**
   - Standard operating procedures
   - Process routing definitions
   - Time standards (SAM - Standard Allowed Minutes)

**29. Defect Code Master**
   - Standardized defect taxonomy
   - Severity classification
   - Corrective actions library

**30. Production Calendar**
   - Working days definition
   - Shift schedules
   - Holiday planning
   - Capacity adjustment

**31. DA Product Master (BOM)**
   - Product specifications
   - Bill of Materials (BOM)
   - Technical drawings
   - Size grading rules

**32. Operator & Skill Matrix**
   - Operator profiles
   - Skill certifications
   - Performance history
   - Training records

---

## 🏢 PORTAL MAKLON (TOLL MANUFACTURING / CMT BUSINESS)

### 📌 OVERVIEW
Portal Maklon mengelola bisnis produksi untuk **klien eksternal**. Klien menyediakan design & material, CV. Dewi Aditya melakukan proses cutting + jahit + finishing (CMT), dan menagih berdasarkan harga per piece (CMT rate).

Model bisnis ini berbeda dari produksi internal:
- Material ownership: **KLIEN**
- Revenue model: **Service fee (CMT rate per pcs)**
- Complexity: **Multiple clients, berbeda spec & requirements**

### 🔄 ALUR BISNIS PROSES MAKLON

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ALUR BISNIS MAKLON (TOLL MFG)                        │
└─────────────────────────────────────────────────────────────────────────┘

1. PRE-ORDER (SAMPLING PHASE)
   ├─ Klien request sample produksi
   ├─ Sample Management - Track sample requests
   ├─ RnD creates proto sample
   ├─ Client approval / revision loop
   ├─ Finalize tech pack & specifications
   └─ Costing negotiation (CMT rate per pcs)

2. PO MAKLON (PURCHASE ORDER DARI KLIEN)
   ├─ Klien issue PO Maklon
   ├─ DA Sales input PO ke system
   ├─ PO Details:
   │  ├─ Artikel / Style code
   │  ├─ Color & Size breakdown
   │  ├─ Quantity per seri
   │  ├─ CMT Rate per pcs
   │  ├─ Deadline delivery
   │  └─ Payment terms (NET 30 / NET 45 / DP)
   └─ PO Status: DRAFT → CONFIRMED

3. MATERIAL RECEIVING DARI KLIEN
   ├─ Klien kirim fabric & accessories
   ├─ Warehouse receive & inspect material
   ├─ Material dikaitkan ke PO Maklon
   ├─ Quality check fabric (defect, color shade)
   └─ Store in designated Maklon warehouse area

4. WORK ORDER GENERATION (AUTO)
   ├─ Saat PO Confirmed → Auto create Work Order
   ├─ WO includes:
   │  ├─ Style / Artikel reference
   │  ├─ Quantity per color/size
   │  ├─ Client's material allocation
   │  ├─ Production deadline
   │  └─ CMT instructions
   └─ WO masuk ke Production Planning

5. PRODUCTION EXECUTION
   │
   ├─ Sama seperti produksi internal (4 tahap)
   │  ├─ Cutting (dari fabric klien)
   │  ├─ Sewing / CMT
   │  ├─ Finishing
   │  └─ QC Final
   │
   ├─ Perbedaan:
   │  ├─ Material ownership tetap klien
   │  ├─ Strict quality standard per klien
   │  ├─ Custom packing requirements
   │  └─ Client representative inspection (optional)
   │
   └─ Dapat di-subcontract ke CMT vendor (multi-dispatch)

6. DISPATCH & DELIVERY (MULTI-DISPATCH SUPPORT)
   ├─ Packing sesuai client requirement
   ├─ Multiple dispatch dimungkinkan:
   │  ├─ Dispatch 1: Partial delivery (misal 50%)
   │  ├─ Dispatch 2: Balance delivery (50%)
   │  └─ Flexible, tidak harus sequential
   ├─ Generate Delivery Note per dispatch
   ├─ Client acknowledgement
   └─ Update PO status (partial_delivered / completed)

7. FINANCE & BILLING
   ├─ AR Invoice generation (auto atau manual)
   ├─ Invoice details:
   │  ├─ Quantity delivered × CMT rate
   │  ├─ Additional charges (jika ada)
   │  ├─ Tax (PPN)
   │  └─ Payment terms
   ├─ Advance Payment (DP) tracking
   ├─ Post AR to General Ledger (GL)
   ├─ Payment collection
   └─ PO Status: INVOICED

8. ANALYTICS & REPORTING
   ├─ Maklon Dashboard - KPI summary
   ├─ PO 360° View - Comprehensive PO details
   ├─ Client profitability analysis
   ├─ CMT efficiency metrics
   ├─ On-time delivery rate
   └─ Quality performance per client
```

### 📊 MODULE UTAMA PORTAL MAKLON

#### A. MASTER DATA

**1. Data Klien Maklon**
   - Client master database
   - Contact persons
   - Payment terms default
   - Tax settings
   - Historical volume & performance

**2. Buyer Catalog** 🆕
   - Artikel library per client
   - Default CMT rates
   - Tech pack repository
   - Color & size options
   - BOM for each artikel (optional)
   - Quick reference saat create PO

#### B. ORDER & PRODUKSI

**3. Dashboard Maklon**
   - Summary metrics:
     - Total PO value (IDR)
     - Active POs in production
     - Pending deliveries
     - Revenue this month
   - Recent activities
   - Alerts (late deliveries, material shortage)
   - Quick actions (create PO, dispatch, invoice)

**4. PO Maklon (Purchase Order)**
   - **CREATE PO**
     - Client selection
     - PO date & deadline
     - Payment terms (NET 30/45, DP %)
     - Line items grid:
       - Seri number
       - Artikel (linked to Buyer Catalog)
       - Color & Size
       - Quantity
       - CMT rate per pcs
       - Subtotal (qty × rate)
     - Auto-calculate total PO value
     - Notes / special instructions
   
   - **PO STATUS FLOW**
     ```
     DRAFT → CONFIRMED → IN_PRODUCTION → 
     PARTIAL_DELIVERED → COMPLETED → INVOICED
     ```
   
   - **PO ACTIONS**
     - Edit (jika masih DRAFT)
     - Confirm PO (trigger WO creation)
     - View details & history
     - Cancel PO (jika belum produksi)
     - Multi-dispatch management
     - Generate invoice

**5. PO 360° View** 🆕
   - Comprehensive single-page view per PO:
     - Header info (client, dates, terms)
     - Items breakdown
     - Material received status
     - Work Order linked
     - Production progress (%)
     - Dispatch history (all deliveries)
     - Invoice status
     - Payment received
     - Documents (tech pack, DO, invoice PDF)
     - Activity timeline
     - Quick actions button

**6. Sample Management**
   - Sample request tracking
   - Proto sample → Pre-production sample → TOP sample
   - Client feedback & revision history
   - Approval workflow
   - Link sample to future PO

**7. Tracking Produksi**
   - Real-time progress per PO Maklon
   - Stage completion % (Cutting → Sewing → Finishing → QC → Packing)
   - Bottleneck identification
   - Expected completion date
   - Aging analysis (PO overdue)
   - Visual Gantt chart (optional)

#### C. VENDOR CMT (SUB-KONTRAKTOR)

Portal Maklon mendukung **multi-tier manufacturing** - DA dapat sub-contract sebagian produksi Maklon ke vendor CMT eksternal.

**8. Kelola Vendor CMT**
   - Vendor master data
   - Capacity & specialization
   - Quality rating
   - Payment terms
   - Contact persons

**9. Portal Vendor** (External Portal)
   - Dedicated portal untuk CMT vendor
   - Vendor login → lihat WO assigned
   - Submit progress updates
   - Request component / accessories
   - Upload quality photos
   - View payment status

#### D. KEUANGAN & ANALITIK

**10. Invoice & Billing**
   - Auto-generate AR Invoice dari dispatch
   - Manual invoice creation
   - Invoice details:
     - PO reference
     - Delivered quantity × CMT rate
     - Tax calculation
     - Payment terms
   - Invoice PDF generation
   - Email to client
   - Track payment status
   - Aging report (outstanding invoices)

**11. Advanced Payment (DP)**
   - Record down payment from client
   - Allocate DP to PO
   - Deduct from final invoice
   - DP aging & reconciliation

**12. Maklon Analytics**
   - **Revenue Metrics**
     - Monthly revenue trend
     - Revenue by client
     - Average CMT rate
     - Profit margin analysis
   
   - **Operational Metrics**
     - On-time delivery rate (OTDR)
     - Production cycle time
     - Defect rate per client
     - Rework percentage
   
   - **Client Performance**
     - Top clients by volume
     - Client profitability ranking
     - Payment punctuality score
     - Repeat order rate

**13. Maklon Reports**
   - PO Summary Report
   - Delivery Performance Report
   - Revenue & Profitability Report
   - Material Usage Report
   - Quality Metrics Report
   - Client Scorecard

---

## 🔗 INTEGRASI ANTAR PORTAL

### Portal Produksi ↔ Warehouse
- **Material Issue**: Production request material → Warehouse approve & issue
- **Material Return**: Unused material return ke warehouse
- **FG Receiving**: Finished goods masuk warehouse stock
- **Stock Real-time Sync**: Production planning lihat available stock

### Portal Produksi ↔ Finance
- **Cost Accounting**: COGS calculation per production order
- **Labor Cost**: Operator wages allocation
- **Overhead Allocation**: Factory overhead per WO
- **Variance Analysis**: Standard cost vs actual cost

### Portal Produksi ↔ HR
- **Operator Assignment**: Production ambil data operator dari HR
- **Shift Management**: HR define shift → Production schedule
- **Performance Tracking**: Production output → HR KPI system
- **Payroll Integration**: Piece rate wages calculation

### Portal Maklon ↔ Warehouse
- **Client Material Receiving**: Warehouse catat material ownership klien
- **Material Issue to Production**: Alokasi material klien ke WO Maklon
- **FG Delivery**: Finished goods ke klien (not stored as DA inventory)
- **Material Reconciliation**: Sisa material return ke klien atau disimpan

### Portal Maklon ↔ Finance
- **AR Invoice Auto-generation**: Dispatch trigger invoice creation
- **Revenue Recognition**: Post revenue sesuai delivery
- **GL Posting**: AR → Journal entry to GL
- **Payment Tracking**: Invoice paid → Update AR aging
- **DP Management**: Down payment application

### Portal Maklon ↔ Production
- **WO Generation**: PO Confirmed → Auto create WO di Production
- **Resource Sharing**: Line & operator digunakan bersama (production internal + maklon)
- **Quality Standards**: QC metrics tracked terpisah per client
- **Capacity Allocation**: Maklon compete dengan internal production untuk capacity

### Portal Maklon ↔ Vendor CMT
- **WO Dispatch**: Sebagian WO Maklon dikirim ke CMT vendor
- **Material Dispatch**: DA kirim client material + cutting ke vendor
- **Progress Tracking**: Vendor report progress real-time
- **Quality Gate**: QC inspection saat return dari vendor
- **Payment Settlement**: Vendor payment berdasarkan delivered quantity

---

## 📈 KEY PERFORMANCE INDICATORS (KPIs)

### KPI Portal Produksi
| Metric | Description | Target |
|--------|-------------|--------|
| **OEE** | Overall Equipment Effectiveness | > 85% |
| **FPY** | First Pass Yield (Quality) | > 95% |
| **OTDR** | On-Time Delivery Rate | > 98% |
| **Line Efficiency** | Output vs Target | > 90% |
| **Rework Rate** | % garments requiring rework | < 3% |
| **Cycle Time** | Order to Delivery duration | < 21 days |
| **Capacity Utilization** | Actual output / Max capacity | > 80% |
| **Downtime %** | Machine/Line downtime | < 5% |

### KPI Portal Maklon
| Metric | Description | Target |
|--------|-------------|--------|
| **Revenue/Month** | Total CMT revenue | Growth +10% MoM |
| **Avg CMT Rate** | Average rate per piece | Maximize |
| **OTDR** | On-Time Delivery Rate | > 95% |
| **Client Satisfaction** | Quality score from client | > 4.5/5 |
| **PO Cycle Time** | PO confirm → Full delivery | < 30 days |
| **Invoice Collection** | Days Sales Outstanding (DSO) | < 45 days |
| **Capacity Utilization** | Maklon vs Internal ratio | Optimal mix |
| **Defect Rate** | Client reject rate | < 2% |

---

## 🎓 BUSINESS RULES & POLICIES

### Produksi Internal
1. **Material Reservation**: Mandatory untuk semua WO > 100 pcs
2. **Bundle Tracking**: Wajib untuk traceability audit
3. **QC Sampling**: AQL 2.5 untuk non-critical, 100% untuk critical defect
4. **Rework Limit**: Max 2x rework, setelah itu classified as scrap
5. **Shift Handover**: Wajib dokumentasi per shift change
6. **Downtime Reporting**: Mandatory untuk downtime > 30 menit

### Maklon
1. **PO Minimum**: Minimum order 100 pcs per artikel
2. **DP Requirement**: DP 30% mandatory untuk new client
3. **Material Lead Time**: Client harus kirim material min 7 hari sebelum production start
4. **Payment Terms**: Default NET 30, negotiable hingga NET 60
5. **Quality Standard**: Client standard jika ada, otherwise DA standard
6. **Delivery Tolerance**: ±5% quantity tolerance allowed
7. **Multi-Dispatch**: Minimum dispatch quantity 20% dari total PO
8. **Invoice Timing**: Invoice issued within 3 days after dispatch

---

## 🔐 ACCESS CONTROL & ROLES

### Portal Produksi
- **Production Manager**: Full access semua module
- **Production Supervisor**: Operasional floor + monitoring, tidak bisa edit master data
- **Line Leader**: Input progress, rework, shift handover only
- **QC Inspector**: QC module, defect recording, pass/fail decision
- **Planner**: Order, WO, scheduling, capacity planning
- **Viewer**: Dashboard & reports only (read-only)

### Portal Maklon
- **Maklon Manager**: Full access semua module
- **Sales Maklon**: Create PO, client management, view analytics
- **Production Coordinator**: WO, tracking, dispatch preparation
- **Finance Maklon**: Invoicing, payment tracking, DP management
- **Viewer**: Dashboard & reports only (read-only)

---

## 📱 MOBILE ACCESS & REAL-TIME FEATURES

### Production Floor Mobile App (Planned / Partial)
- **Quick Input**: Scan bundle → input progress
- **Andon Alert**: Operator trigger help request
- **Shift Handover**: Mobile approval & signature
- **Quality Photo**: Upload defect photos from smartphone
- **Live Dashboard**: Monitor progress real-time

### Client Portal (Maklon)
- **Dedicated portal for Maklon clients**
- Client login → view their PO status
- Production progress tracking
- Delivery schedule
- Invoice & payment history
- Sample approval workflow
- Document download (DO, Invoice PDF)

---

## 🚀 FUTURE ENHANCEMENTS

### Produksi
1. **IoT Integration**: Machine sensor data untuk predictive maintenance
2. **AI Quality Vision**: Camera-based defect detection
3. **Digital Twin**: Virtual factory simulation
4. **Advanced Scheduling**: AI-powered production scheduling optimizer
5. **Blockchain Traceability**: Immutable garment journey record

### Maklon
1. **Client Self-Service Portal**: Client create PO directly (with approval)
2. **Real-time Photo Updates**: Production progress photos auto-sent to client
3. **Dynamic Pricing**: AI-suggested CMT rate based on complexity
4. **Contract Management**: Digital contract signing & renewal automation
5. **Client Loyalty Program**: Volume-based incentive tracking

---

## 📚 GLOSSARY

| Term | Definition |
|------|------------|
| **BOM** | Bill of Materials - Daftar material yang dibutuhkan untuk produksi |
| **CMT** | Cut, Make, Trim - Proses potong, jahit, finishing |
| **DO** | Delivery Order - Surat pengiriman barang |
| **FG** | Finished Goods - Barang jadi |
| **FPY** | First Pass Yield - % produk lolos QC pertama kali |
| **GRN** | Goods Received Note - Bukti penerimaan barang |
| **Maklon** | Toll Manufacturing - Produksi untuk pihak ketiga |
| **OEE** | Overall Equipment Effectiveness - Metrik efisiensi mesin |
| **OTDR** | On-Time Delivery Rate - % pengiriman tepat waktu |
| **PO** | Purchase Order - Order pembelian |
| **SAM** | Standard Allowed Minutes - Standar waktu produksi |
| **SKU** | Stock Keeping Unit - Kode unik per produk/varian |
| **SOP** | Standard Operating Procedure - Prosedur kerja standar |
| **WO** | Work Order - Perintah kerja produksi |
| **WIP** | Work In Progress - Barang dalam proses produksi |

---

## 📞 SUPPORT & DOCUMENTATION

Untuk pertanyaan lebih lanjut tentang business process atau system functionality:

- **Production Issues**: Contact Production Manager
- **Maklon Issues**: Contact Maklon Manager
- **System Technical**: Contact IT Support / System Administrator
- **User Training**: Request melalui HR Learning Management module

---

**Dokumen ini dibuat oleh**: Neo AI Agent  
**Tanggal**: 2 Juni 2026  
**Versi**: 1.0  
**Status**: Living Document (akan diupdate sesuai business evolution)

