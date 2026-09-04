"""
Invoice PDF builder for CV. Dewi Aditya Maklon billing.
Uses ReportLab (already in requirements). Returns bytes.

SESI #19 — DITULIS ULANG memakai TEMPLATE PDF pemilik (`core/pdf_template.py`).
Yang terukur pada versi lama:
  · kop hanya nama+tagline+alamat, TANPA logo, telepon, atau NPWP — padahal invoice
    adalah dokumen tagihan yang keluar ke klien;
  · margin 18 mm sementara seluruh dokumen lain 12 mm, dan lebar kolom tabel
    milimeter tetap (10+80+22+30+28 = 170 mm dari 174 mm) ⇒ tabel tidak pernah
    penuh halaman dan uraian panjang terpotong;
  · tidak ada blok tanda tangan sama sekali (tidak bisa diatur).
Blok total/bill-to tetap khas invoice; yang diseragamkan adalah kop, tabel, tanda
tangan, dan footer.
"""
# ruff: noqa: E741
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

DOC_KEY = 'invoice-maklon'


def _fmt_idr(n):
    try:
        v = float(n or 0)
    except (ValueError, TypeError):
        v = 0
    return f"Rp {v:,.0f}".replace(',', '.')


def _fmt_date(d):
    if not d:
        return '-'
    s = str(d)[:10]
    try:
        dt = datetime.strptime(s, '%Y-%m-%d')
        bln = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agt', 'Sep', 'Okt', 'Nov', 'Des']
        return f"{dt.day} {bln[dt.month - 1]} {dt.year}"
    except ValueError:
        return s


def build_invoice_pdf(*, invoice: dict, client: dict, company: dict | None = None,
                      template: dict | None = None, profile: dict | None = None) -> bytes:
    """PDF invoice. `template` = template PDF efektif; `profile` = profil perusahaan.

    Keduanya OPSIONAL: bila tidak dikirim (pemanggil lama / skrip), kop dibangun dari
    `company` seperti sebelumnya sehingga tidak ada pemanggil yang pecah.
    """
    from core.pdf_template import (apply_columns, column_weights, footer_flowables,
                                   header_flowables, signature_flowables)
    from data.pdf_doc_registry import columns_of, weights_of
    from routes.operations_pdf_helpers import (CONTENT_W_PORTRAIT, _build_pdf,
                                               _pdf_data_table)

    company = company or {}
    template = template or {}
    profile = profile or {
        'company_name': company.get('company_name') or 'CV. DEWI ADITYA OFFICIAL',
        'address': company.get('company_address') or 'Sragen, Jawa Tengah',
        'phone': company.get('company_phone') or company.get('phone') or '',
        'email': company.get('company_email') or company.get('email') or '',
        'website': company.get('company_website') or '',
        'npwp': company.get('npwp') or '',
        'tagline': company.get('company_tagline') or '',
        'pdf_footer_text': company.get('pdf_footer_text') or '',
    }

    styles = getSampleStyleSheet()
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=9, leading=12,
                          textColor=colors.HexColor('#1f2937'))
    body_muted = ParagraphStyle('muted', parent=styles['Normal'], fontSize=8.5, leading=11,
                                textColor=colors.HexColor('#64748b'))
    body_right = ParagraphStyle('right', parent=body, alignment=2)

    avail = CONTENT_W_PORTRAIT
    elems = header_flowables(template.get('header'), profile, 'INVOICE',
                             avail=avail)

    # ── meta invoice + tagihan kepada ─────────────────────────────────────────
    meta_lines = [
        ['No. Invoice', invoice.get('invoice_number') or '-'],
        ['Tgl Terbit', _fmt_date(invoice.get('issue_date'))],
        ['Jatuh Tempo', _fmt_date(invoice.get('due_date'))],
        ['Term', (invoice.get('payment_terms') or 'net_30').replace('_', ' ').upper()],
        ['Status', (invoice.get('status') or '-').upper()],
    ]
    meta_tbl_data = [[Paragraph(f"<font color='#64748b'>{k}</font>", body),
                      Paragraph(f"<b>{v}</b>", body)] for k, v in meta_lines]

    bill_to = (
        "<b>Tagihan Kepada:</b><br/>"
        f"{client.get('name', '-')}<br/>"
        "<font size=8 color='#64748b'>"
        f"{client.get('pic_name') or ''}<br/>"
        f"{client.get('pic_phone') or ''}<br/>"
        f"{client.get('pic_email') or ''}<br/>"
        f"{client.get('address') or client.get('city') or ''}"
        "</font>"
    )
    cust_tbl = Table([[Paragraph(bill_to, body),
                       Table(meta_tbl_data, colWidths=[avail * 0.17, avail * 0.23])]],
                     colWidths=[avail * 0.58, avail * 0.42])
    cust_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    elems.append(cust_tbl)
    elems.append(Spacer(1, 5 * mm))

    # ── baris invoice: kolom mengikuti template (tampil/urutan/lebar) ─────────
    all_cols = columns_of(DOC_KEY)
    all_keys = [c['key'] for c in all_cols]
    all_headers = [c['label'] for c in all_cols]
    rows = []
    for i, l in enumerate(invoice.get('lines') or [], start=1):
        rows.append([
            str(i), l.get('description') or '-', l.get('sku') or '',
            f"{l.get('qty', 0)}", l.get('unit') or '',
            _fmt_idr(l.get('unit_price')), _fmt_idr(l.get('line_total')),
        ])
    tpl_cols = template.get('columns') or []
    headers, rows2, keys = apply_columns(tpl_cols, all_keys, all_headers, rows)
    if rows2:
        elems.append(_pdf_data_table(
            headers, rows2,
            weights=column_weights(tpl_cols, keys, weights_of(DOC_KEY)),
            right_cols=[i for i, k in enumerate(keys) if k in ('qty', 'price', 'amount')],
            style=template.get('table')))
    else:
        # Tabel kosong berbaris judul saja terlihat seperti dokumen rusak; katakan
        # apa adanya supaya jelas ini data yang belum ada, bukan cetakan yang gagal.
        elems.append(Paragraph(
            "<i>Invoice ini belum memiliki baris rincian.</i>", body_muted))
    elems.append(Spacer(1, 4 * mm))

    # ── total ────────────────────────────────────────────────────────────────
    totals = [['Subtotal', _fmt_idr(invoice.get('subtotal'))]]
    if (invoice.get('discount_amount') or 0) > 0:
        totals.append(['Diskon', '-' + _fmt_idr(invoice.get('discount_amount'))])
    totals.append([f"PPN ({invoice.get('tax_pct') or 0}%)", _fmt_idr(invoice.get('tax_amount'))])
    totals.append(['<b>Total</b>', '<b>' + _fmt_idr(invoice.get('total_amount')) + '</b>'])
    totals.append(['Sudah Dibayar', _fmt_idr(invoice.get('paid_amount'))])
    totals.append(['<b>Saldo Tagihan</b>',
                   '<b>' + _fmt_idr(invoice.get('balance_amount')) + '</b>'])
    totals_data = [[Paragraph(k, body_right), Paragraph(v, body_right)] for k, v in totals]
    totals_tbl = Table(totals_data, colWidths=[avail * 0.22, avail * 0.20])
    totals_tbl.setStyle(TableStyle([
        ('LINEABOVE', (0, -3), (-1, -3), 0.6, colors.HexColor('#94a3b8')),
        ('LINEABOVE', (0, -1), (-1, -1), 0.6, colors.HexColor('#94a3b8')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    wrap = Table([['', totals_tbl]], colWidths=[avail * 0.56, avail * 0.44])
    wrap.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                              ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
    elems.append(wrap)

    if invoice.get('notes'):
        elems.append(Spacer(1, 4 * mm))
        elems.append(Paragraph(f"<b>Catatan:</b> {invoice.get('notes')}", body_muted))

    elems.extend(signature_flowables(template.get('signatures'), {
        'client_name': client.get('name', ''),
        'invoice_number': invoice.get('invoice_number', ''),
    }, avail=avail))

    elems.append(Spacer(1, 3 * mm))
    elems.append(HRFlowable(width='100%', thickness=0.4, color=colors.HexColor('#cbd5e1')))
    elems.append(Paragraph(
        "Pembayaran ditujukan ke rekening yang sudah disepakati. Setelah transfer mohon "
        "konfirmasi ke Finance melalui WhatsApp atau email. Terima kasih.", body_muted))
    elems.extend(footer_flowables(template.get('footer'), profile))

    buf = _build_pdf(BytesIO(), elems)
    return buf.getvalue()
