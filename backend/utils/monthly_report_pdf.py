"""
Laporan Bulanan Marketing — PDF Generator
==========================================
Menghasilkan PDF laporan bulanan per akun: target vs aktual, task stats, dll.
Menggunakan ReportLab (sudah tersedia di sistem).
"""
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from utils.waktu import now_wib

# ─── Palet warna ─────────────────────────────────────────────────────────────
BRAND      = colors.HexColor('#7c3aed')   # violet — portal marketing
BRAND_LIGHT= colors.HexColor('#ede9fe')
ON_TRACK   = colors.HexColor('#d1fae5')   # emerald-100
WARNING    = colors.HexColor('#fef3c7')   # amber-100
BEHIND     = colors.HexColor('#fee2e2')   # red-100
TEXT_DARK  = colors.HexColor('#111827')
TEXT_MUTED = colors.HexColor('#6b7280')
BORDER     = colors.HexColor('#e5e7eb')
WHITE      = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm

MONTH_NAMES = [
    '', 'Januari','Februari','Maret','April','Mei','Juni',
    'Juli','Agustus','September','Oktober','November','Desember'
]
PLATFORM_LABELS = {
    'shopee': 'Shopee',
    'tiktokshop': 'TikTok',
    'tokopedia': 'Tokopedia',
}

def _fmt_rp(n):
    n = n or 0
    if n >= 1e9:
        return f"Rp {n/1e9:.1f}M"
    if n >= 1e6:
        return f"Rp {n/1e6:.1f}jt"
    if n >= 1e3:
        return f"Rp {n/1e3:.0f}rb"
    return f"Rp {n:,.0f}"

def _fmt_num(n):
    return f"{int(n or 0):,}".replace(',', '.')

def _pct_color(pct):
    if pct is None:
        return None
    if pct >= 90:
        return ON_TRACK
    if pct >= 70:
        return WARNING
    return BEHIND

def _pct_text(pct):
    if pct is None:
        return '—'
    return f"{pct:.1f}%"

def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'rpt_title', parent=base['Title'],
            fontName='Helvetica-Bold', fontSize=18, leading=22,
            textColor=BRAND, alignment=TA_LEFT, spaceAfter=2,
        ),
        'subtitle': ParagraphStyle(
            'rpt_sub', parent=base['Normal'],
            fontName='Helvetica', fontSize=9, leading=12,
            textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=8,
        ),
        'section': ParagraphStyle(
            'rpt_sec', parent=base['Normal'],
            fontName='Helvetica-Bold', fontSize=10, leading=13,
            textColor=BRAND, spaceAfter=4, spaceBefore=6,
        ),
        'body': ParagraphStyle(
            'rpt_body', parent=base['Normal'],
            fontName='Helvetica', fontSize=8, leading=11,
            textColor=TEXT_DARK,
        ),
        'footer': ParagraphStyle(
            'rpt_footer', parent=base['Normal'],
            fontName='Helvetica', fontSize=7, leading=9,
            textColor=TEXT_MUTED, alignment=TA_CENTER,
        ),
    }


def build_monthly_report_pdf(report_data: dict, company_name: str = 'CV. Dewi Aditya') -> bytes:
    """
    Generate PDF Laporan Bulanan Marketing.
    report_data: output dari endpoint /api/marketing/reports/monthly
    Returns: PDF bytes
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="Laporan Bulanan Marketing",
    )
    S = _styles()
    elements = []

    period = report_data.get('period', {})
    year   = period.get('year', now_wib().year)
    month  = period.get('month', now_wib().month)
    period_label = f"{MONTH_NAMES[month]} {year}"
    summary = report_data.get('summary', {})
    accounts = report_data.get('accounts', [])
    generated_at = now_wib().strftime('%d %B %Y, %H:%M')

    # ── HEADER ────────────────────────────────────────────────────────────────
    elements.append(Paragraph("LAPORAN BULANAN MARKETING", S['title']))
    elements.append(Paragraph(
        f"{company_name}  ·  Periode: {period_label}  ·  Digenerate: {generated_at}",
        S['subtitle']
    ))
    elements.append(HRFlowable(width='100%', thickness=1.5, color=BRAND, spaceAfter=8))

    # ── RINGKASAN KPI ─────────────────────────────────────────────────────────
    elements.append(Paragraph("Ringkasan Periode", S['section']))

    rev_pct  = summary.get('rev_pct')
    rev_act  = summary.get('rev_actual', 0)
    rev_tgt  = summary.get('rev_target', 0)
    ord_act  = summary.get('ord_actual', 0)
    task_cpl = summary.get('task_completion')
    inp_rate = summary.get('avg_sales_input_rate')

    kpi_data = [
        ['Metrik', 'Aktual', 'Target', 'Pencapaian'],
        ['Total Revenue', _fmt_rp(rev_act), _fmt_rp(rev_tgt) if rev_tgt else '—', _pct_text(rev_pct)],
        ['Total Orders',  _fmt_num(ord_act), _fmt_num(summary.get('ord_target', 0)) or '—', '—'],
        ['Task Completion', f"{task_cpl:.1f}%" if task_cpl else '—', '—', '—'],
        ['Sales Input Rate', f"{inp_rate:.1f}%" if inp_rate else '—', '—', '—'],
        ['Jumlah Akun', str(summary.get('total_accounts', 0)), '—', '—'],
    ]

    kpi_col_w = [(PAGE_W - 2*MARGIN) * w for w in (0.35, 0.22, 0.22, 0.21)]
    kpi_tbl = Table(kpi_data, colWidths=kpi_col_w, repeatRows=1)
    kpi_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  BRAND),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,0),  8),
        ('FONTNAME',    (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',    (0,1), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9fafb')]),
        ('GRID',        (0,0), (-1,-1), 0.5, BORDER),
        ('ALIGN',       (1,0), (-1,-1), 'RIGHT'),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))

    # Warna row revenue berdasarkan pencapaian
    rev_row_color = _pct_color(rev_pct)
    if rev_row_color:
        kpi_tbl.setStyle(TableStyle([('BACKGROUND', (0,1), (-1,1), rev_row_color)]))

    elements.append(kpi_tbl)
    elements.append(Spacer(1, 8*mm))

    # ── DETAIL PER AKUN ───────────────────────────────────────────────────────
    elements.append(Paragraph("Detail per Akun", S['section']))

    col_labels = [
        'Akun', 'Platform',
        'Revenue Aktual', 'Revenue Target', 'Rev %',
        'Orders Aktual', 'Orders Target', 'Ord %',
        'Input Days', 'Input Rate', 'Health'
    ]
    detail_data = [col_labels]

    for row in accounts:
        ach  = row.get('achievement', {})
        act  = row.get('actual', {})
        tgt  = row.get('target', {})
        row.get('task_stats', {})
        rev_pct_acc = ach.get('revenue_pct')
        ord_pct_acc = ach.get('orders_pct')
        detail_data.append([
            row.get('account_name', '')[:22],
            PLATFORM_LABELS.get(row.get('platform',''), row.get('platform','')),
            _fmt_rp(act.get('revenue', 0)),
            _fmt_rp(tgt.get('revenue')) if tgt.get('revenue') else '—',
            _pct_text(rev_pct_acc),
            _fmt_num(act.get('orders', 0)),
            _fmt_num(tgt.get('orders')) if tgt.get('orders') else '—',
            _pct_text(ord_pct_acc),
            str(act.get('sales_days', 0)),
            f"{act.get('input_rate', 0):.0f}%",
            str(row.get('health_score', '—')),
        ])

    col_pcts = [0.14, 0.07, 0.10, 0.10, 0.07, 0.08, 0.08, 0.07, 0.07, 0.07, 0.06]
    col_ws = [(PAGE_W - 2*MARGIN) * p for p in col_pcts]

    detail_tbl = Table(detail_data, colWidths=col_ws, repeatRows=1)
    tbl_style = [
        ('BACKGROUND',  (0,0), (-1,0),  BRAND),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,0),  7),
        ('FONTNAME',    (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',    (0,1), (-1,-1), 7),
        ('GRID',        (0,0), (-1,-1), 0.5, BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('ALIGN',       (2,0), (-1,-1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, colors.HexColor('#f9fafb')]),
    ]

    # Warnai kolom Rev% dan Ord% berdasarkan pencapaian
    for i, row in enumerate(accounts, start=1):
        ach = row.get('achievement', {})
        rev_c = _pct_color(ach.get('revenue_pct'))
        ord_c = _pct_color(ach.get('orders_pct'))
        if rev_c:
            tbl_style.append(('BACKGROUND', (4, i), (4, i), rev_c))
        if ord_c:
            tbl_style.append(('BACKGROUND', (7, i), (7, i), ord_c))

    detail_tbl.setStyle(TableStyle(tbl_style))
    elements.append(detail_tbl)

    # ── LEGENDA ───────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(
        "🟢 On Track ≥90%  ·  🟡 Warning 70–89%  ·  🔴 Behind <70%",
        S['footer']
    ))
    elements.append(Spacer(1, 2*mm))
    elements.append(HRFlowable(width='100%', thickness=0.5, color=BORDER))
    elements.append(Spacer(1, 1*mm))
    elements.append(Paragraph(
        f"Dokumen ini dibuat otomatis oleh Sistem ERP {company_name} — {generated_at}",
        S['footer']
    ))

    doc.build(elements)
    return buf.getvalue()



def build_creator_target_pdf(summary_data: dict, company_name: str = 'CV. Dewi Aditya') -> bytes:
    """
    Generate PDF Target KOL/Creator Bulanan.
    summary_data: output dari endpoint /api/marketing/targets/creator/monthly-summary
    Returns: PDF bytes
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="Target KOL/Creator Bulanan",
    )
    S = _styles()
    elements = []

    period   = summary_data.get('period', {})
    y, m     = period.get('year', now_wib().year), period.get('month', now_wib().month)
    summary  = summary_data.get('summary', {})
    creators = summary_data.get('creators', [])
    gen_at   = now_wib().strftime('%d %B %Y, %H:%M')

    # ── HEADER ──────────────────────────────────────────────────────────────
    elements.append(Paragraph("TARGET KOL / CREATOR BULANAN", S['title']))
    elements.append(Paragraph(
        f"{company_name}  ·  Periode: {MONTH_NAMES[m]} {y}  ·  Digenerate: {gen_at}",
        S['subtitle']
    ))
    elements.append(HRFlowable(width='100%', thickness=1.5, color=BRAND, spaceAfter=8))

    # ── RINGKASAN ────────────────────────────────────────────────────────────
    elements.append(Paragraph("Ringkasan Periode", S['section']))

    rev_pct = summary.get('rev_pct')
    kpi_data = [
        ['Metrik', 'Aktual', 'Target', 'Pencapaian'],
        ['Total Creator', str(summary.get('total_creators', 0)), '—', '—'],
        ['Total Revenue', _fmt_rp(summary.get('rev_actual', 0)),
         _fmt_rp(summary.get('rev_target', 0)) if summary.get('rev_target') else '—',
         _pct_text(rev_pct)],
        ['Total Sessions',
         _fmt_num(sum(r.get('actual', {}).get('sessions', 0) for r in creators)), '—', '—'],
        ['Total Viewers',
         _fmt_num(sum(r.get('actual', {}).get('viewers', 0) for r in creators)), '—', '—'],
    ]

    col_w = [(PAGE_W - 2*MARGIN) * w for w in (0.35, 0.22, 0.22, 0.21)]
    kpi_tbl = Table(kpi_data, colWidths=col_w, repeatRows=1)
    kpi_tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0),  BRAND),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,-1), 8),
        ('FONTNAME',    (0,1), (-1,-1), 'Helvetica'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, colors.HexColor('#f9fafb')]),
        ('GRID',        (0,0), (-1,-1), 0.5, BORDER),
        ('ALIGN',       (1,0), (-1,-1), 'RIGHT'),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
    ]))
    if rev_pct is not None:
        rc = _pct_color(rev_pct)
        if rc:
            kpi_tbl.setStyle(TableStyle([('BACKGROUND', (0,2), (-1,2), rc)]))
    elements.append(kpi_tbl)
    elements.append(Spacer(1, 8*mm))

    # ── DETAIL PER CREATOR ───────────────────────────────────────────────────
    elements.append(Paragraph("Detail per KOL/Creator", S['section']))

    col_labels = [
        'Creator', 'Code',
        'Rev Aktual', 'Rev Target', 'Rev %',
        'Sesi', 'Sesi Target', 'Sesi %',
        'Viewers', 'View Target',
    ]
    detail_data = [col_labels]

    for row in creators:
        ach = row.get('achievement', {})
        act = row.get('actual', {})
        tgt = row.get('target', {})
        detail_data.append([
            row.get('creator_name', '')[:20],
            row.get('creator_code', ''),
            _fmt_rp(act.get('revenue', 0)),
            _fmt_rp(tgt.get('revenue'))  if tgt.get('revenue')  else '—',
            _pct_text(ach.get('revenue_pct')),
            str(act.get('sessions', 0)),
            str(tgt.get('sessions'))     if tgt.get('sessions')  else '—',
            _pct_text(ach.get('sessions_pct')),
            _fmt_num(act.get('viewers', 0)),
            _fmt_num(tgt.get('viewers')) if tgt.get('viewers')   else '—',
        ])

    col_pcts = [0.14, 0.08, 0.11, 0.11, 0.07, 0.06, 0.08, 0.07, 0.10, 0.10]
    col_ws   = [(PAGE_W - 2*MARGIN) * p for p in col_pcts]

    det_tbl = Table(detail_data, colWidths=col_ws, repeatRows=1)
    tbl_style = [
        ('BACKGROUND',  (0,0), (-1,0),  BRAND),
        ('TEXTCOLOR',   (0,0), (-1,0),  WHITE),
        ('FONTNAME',    (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,-1), 7),
        ('FONTNAME',    (0,1), (-1,-1), 'Helvetica'),
        ('GRID',        (0,0), (-1,-1), 0.5, BORDER),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',  (0,0), (-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('ALIGN',       (2,0), (-1,-1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [WHITE, colors.HexColor('#f9fafb')]),
    ]
    # Warnai kolom Rev% dan Sesi%
    for i, row in enumerate(creators, start=1):
        ach = row.get('achievement', {})
        rc = _pct_color(ach.get('revenue_pct'))
        sc = _pct_color(ach.get('sessions_pct'))
        if rc:
            tbl_style.append(('BACKGROUND', (4, i), (4, i), rc))
        if sc:
            tbl_style.append(('BACKGROUND', (7, i), (7, i), sc))

    det_tbl.setStyle(TableStyle(tbl_style))
    elements.append(det_tbl)

    # ── LEGENDA + FOOTER ─────────────────────────────────────────────────────
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(
        "🟢 On Track ≥90%  ·  🟡 Warning 70–89%  ·  🔴 Behind <70%  ·  — = Belum set target",
        S['footer']
    ))
    elements.append(Spacer(1, 2*mm))
    elements.append(HRFlowable(width='100%', thickness=0.5, color=BORDER))
    elements.append(Spacer(1, 1*mm))
    elements.append(Paragraph(
        f"Dokumen ini dibuat otomatis oleh Sistem ERP {company_name} — {gen_at}",
        S['footer']
    ))

    doc.build(elements)
    return buf.getvalue()
