"""
LiveHost Management — SOP PDF Generator
Generates a printable Standard Operating Procedure document for LiveHost operations.

Author: CV. Dewi Aditya Development Team
Date: 2026-05-21
"""
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    HRFlowable,
    PageBreak,
    ListFlowable,
    ListItem,
)
from reportlab.lib.enums import TA_LEFT
from utils.waktu import now_wib


# ─── Branding (consistent with portal teal accent) ──────────────────────────
BRAND_TEAL = colors.HexColor('#0d9488')
BRAND_TEAL_LIGHT = colors.HexColor('#ccfbf1')
TEXT_DARK = colors.HexColor('#1f2937')
TEXT_MUTED = colors.HexColor('#6b7280')
BG_LIGHT = colors.HexColor('#f9fafb')
BORDER_LIGHT = colors.HexColor('#e5e7eb')


def _styles():
    base = getSampleStyleSheet()
    return {
        'cover_title': ParagraphStyle(
            'cover_title', parent=base['Title'],
            fontName='Helvetica-Bold', fontSize=22, leading=28,
            textColor=BRAND_TEAL, alignment=TA_LEFT, spaceAfter=4,
        ),
        'cover_subtitle': ParagraphStyle(
            'cover_subtitle', parent=base['Normal'],
            fontName='Helvetica', fontSize=11, leading=14,
            textColor=TEXT_MUTED, alignment=TA_LEFT, spaceAfter=20,
        ),
        'h1': ParagraphStyle(
            'h1', parent=base['Heading1'],
            fontName='Helvetica-Bold', fontSize=15, leading=20,
            textColor=TEXT_DARK, spaceBefore=12, spaceAfter=8,
        ),
        'h2': ParagraphStyle(
            'h2', parent=base['Heading2'],
            fontName='Helvetica-Bold', fontSize=12, leading=16,
            textColor=BRAND_TEAL, spaceBefore=8, spaceAfter=4,
        ),
        'h3': ParagraphStyle(
            'h3', parent=base['Heading3'],
            fontName='Helvetica-Bold', fontSize=10.5, leading=14,
            textColor=TEXT_DARK, spaceBefore=6, spaceAfter=3,
        ),
        'body': ParagraphStyle(
            'body', parent=base['Normal'],
            fontName='Helvetica', fontSize=10, leading=14,
            textColor=TEXT_DARK, spaceAfter=4, alignment=TA_LEFT,
        ),
        'bullet': ParagraphStyle(
            'bullet', parent=base['Normal'],
            fontName='Helvetica', fontSize=9.5, leading=13,
            textColor=TEXT_DARK, leftIndent=10, bulletIndent=0,
        ),
        'caption': ParagraphStyle(
            'caption', parent=base['Normal'],
            fontName='Helvetica-Oblique', fontSize=9, leading=12,
            textColor=TEXT_MUTED, spaceAfter=4,
        ),
        'note': ParagraphStyle(
            'note', parent=base['Normal'],
            fontName='Helvetica', fontSize=9.5, leading=13,
            textColor=TEXT_DARK, leftIndent=8,
        ),
    }


def _bullets(items, S):
    """Build a bulleted list flowable."""
    return ListFlowable(
        [ListItem(Paragraph(t, S['bullet']), leftIndent=12, value='•') for t in items],
        bulletType='bullet', bulletFontSize=9, leftIndent=8, spaceAfter=4,
    )


def _kv_table(rows, S):
    """Two-column key-value table."""
    data = [[Paragraph(f"<b>{k}</b>", S['note']), Paragraph(v, S['note'])] for k, v in rows]
    t = Table(data, colWidths=[45 * mm, None])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), BG_LIGHT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, BORDER_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _section_header(idx, title, S):
    """Section header with a colored side-bar."""
    cell = Table(
        [[Paragraph(f"<b>{idx}. {title}</b>", ParagraphStyle(
            'sec', parent=S['h1'], textColor=colors.white,
            fontSize=12, leading=15, leftIndent=4))]],
        colWidths=[None],
    )
    cell.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_TEAL),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return cell


def _info_box(title, body, S, color=BRAND_TEAL_LIGHT):
    """Highlighted info/warning box."""
    inner = [Paragraph(f"<b>{title}</b>", S['h3']), Paragraph(body, S['body'])]
    t = Table([[inner]], colWidths=[None])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color),
        ('BOX', (0, 0), (-1, -1), 0.7, BRAND_TEAL),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return t


def _step_table(rows, S):
    """Numbered step-by-step table with role / action."""
    headers = ['No.', 'Peran', 'Aksi', 'Catatan']
    data = [[Paragraph(f"<b>{h}</b>", ParagraphStyle('th', parent=S['note'],
            fontName='Helvetica-Bold', textColor=colors.white)) for h in headers]]
    for i, (role, action, note) in enumerate(rows, 1):
        data.append([
            Paragraph(str(i), S['note']),
            Paragraph(role, S['note']),
            Paragraph(action, S['note']),
            Paragraph(note or '—', S['note']),
        ])
    t = Table(data, colWidths=[12 * mm, 30 * mm, None, 45 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_TEAL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.6, BORDER_LIGHT),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, BORDER_LIGHT),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, BG_LIGHT]),
    ]))
    return t


def build_livehost_sop_pdf(company_name: str = 'CV. DEWI ADITYA OFFICIAL') -> bytes:
    """
    Build a complete SOP PDF for LiveHost Management operations.
    Returns: PDF bytes.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title='SOP LiveHost Management — DA25 ERP',
        author=company_name,
    )
    S = _styles()
    flow = []

    # ═══ COVER ═══════════════════════════════════════════════════════════
    flow += [
        Spacer(1, 8 * mm),
        Paragraph(company_name, S['caption']),
        Spacer(1, 4 * mm),
        Paragraph('Standard Operating Procedure', S['cover_subtitle']),
        Paragraph('LiveHost Management', S['cover_title']),
        Paragraph(
            'Pedoman operasional untuk admin, supervisor, dan host live streaming '
            'dalam menggunakan modul LiveHost di DA25 ERP.',
            S['body']
        ),
        Spacer(1, 6 * mm),
        HRFlowable(width="100%", thickness=1, color=BRAND_TEAL, spaceBefore=4, spaceAfter=4),
        Spacer(1, 3 * mm),
        _kv_table([
            ('Dokumen', 'SOP-LIVEHOST-001'),
            ('Versi', '1.0'),
            ('Berlaku Mulai', now_wib().strftime('%d %B %Y')),
            ('Disusun Oleh', 'Tim Marketing & Operasional'),
            ('Modul Terkait', 'Marketing › LiveHost Management & LiveHost Portal'),
            ('Audiens', 'Admin Marketing, Supervisor LiveHost, Host'),
        ], S),
        Spacer(1, 6 * mm),
        _info_box(
            'Tujuan SOP',
            'Memastikan setiap proses live streaming — mulai dari penjadwalan, briefing, '
            'eksekusi, hingga rekonsiliasi pembayaran — berjalan konsisten, terdokumentasi, '
            'dan terhubung dengan modul Finance/Payroll.',
            S
        ),
        PageBreak(),
    ]

    # ═══ 1. PERAN & TANGGUNG JAWAB ═══════════════════════════════════════
    flow += [
        _section_header(1, 'Peran & Tanggung Jawab', S),
        Spacer(1, 4 * mm),
        Paragraph(
            'Modul LiveHost melibatkan tiga peran utama dengan akses dan tanggung jawab berbeda:',
            S['body']
        ),
        Spacer(1, 2 * mm),
        _kv_table([
            (
                'Admin / Manager',
                'Mengelola data host, membuat shift, meng-assign script & training, '
                'merekap performa, melakukan kalkulasi & sync payment ke Finance.'
            ),
            (
                'Supervisor LiveHost',
                'Memantau eksekusi live, memvalidasi performa shift (viewers, revenue, orders), '
                'menyetujui rekap pembayaran sebelum sync.'
            ),
            (
                'Host (LiveHost)',
                'Login ke LiveHost Portal (/livehost), clock-in/out, membaca script, '
                'menyelesaikan training yang di-assign, melihat notifikasi shift terbaru.'
            ),
        ], S),
        Spacer(1, 6 * mm),
    ]

    # ═══ 2. ONBOARDING HOST BARU ═════════════════════════════════════════
    flow += [
        _section_header(2, 'Onboarding Host Baru', S),
        Spacer(1, 3 * mm),
        Paragraph('Langkah-langkah onboarding host live streaming baru:', S['body']),
        Spacer(1, 2 * mm),
        _step_table([
            ('Admin', 'Buka <b>Portal Marketing → KOL &amp; Creator → LiveHost Management</b>',
             'Pastikan akses superadmin/marketing'),
            ('Admin', 'Klik <b>Tambah LiveHost</b>, isi: nama, email, password awal, phone, '
             'employment type (full-time/part-time/contract), hourly rate', 'Email harus unik'),
            ('Admin', 'Set <b>shift preferences</b>, <b>language skills</b>, <b>product expertise</b>',
             'Membantu auto-suggest assignment'),
            ('Admin', 'Assign 1+ platform account (Shopee/TikTokShop/Tokopedia)',
             'Account harus aktif'),
            ('Admin', 'Assign training wajib (Product Knowledge, Live Etiquette, dll)',
             'Host akan dapat notifikasi'),
            ('Host', 'Login ke <b>/livehost</b> dengan email + password awal',
             'Ganti password setelah login pertama'),
            ('Host', 'Lengkapi profile, baca welcome script, selesaikan training awal',
             'Status host = active'),
        ], S),
        Spacer(1, 4 * mm),
        _info_box(
            'Wajib Diketahui',
            'Host yang training wajibnya belum selesai TIDAK bisa di-assign shift produksi. '
            'Sistem akan memberi warning saat assignment.',
            S, color=colors.HexColor('#fef3c7')
        ),
        PageBreak(),
    ]

    # ═══ 3. PENJADWALAN SHIFT ════════════════════════════════════════════
    flow += [
        _section_header(3, 'Penjadwalan Shift', S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Jenis Shift:</b>', S['h3']),
        _bullets([
            '<b>Morning</b> — biasanya 06:00 – 12:00',
            '<b>Afternoon</b> — biasanya 12:00 – 17:00',
            '<b>Evening</b> — biasanya 17:00 – 22:00',
            '<b>Night</b> — biasanya 22:00 – 06:00',
        ], S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Proses Penjadwalan:</b>', S['h3']),
        _step_table([
            ('Admin', 'Buka tab <b>Shift Management</b>', '—'),
            ('Admin', 'Pilih host, account, tanggal, jenis shift, jam mulai &amp; jam selesai',
             'Sistem cek konflik otomatis'),
            ('Admin', 'Tambahkan catatan khusus bila ada (promo, produk fokus, dll)', '—'),
            ('Admin', 'Klik <b>Buat Shift</b>', 'Host langsung dapat SSE notifikasi'),
            ('Host', 'Lihat shift di tab <b>Shift</b> di portal /livehost',
             'Status: Scheduled'),
        ], S),
        Spacer(1, 4 * mm),
        _info_box(
            'Aturan Bentrok',
            'Sistem menolak shift jika host sudah memiliki shift lain pada tanggal & rentang waktu '
            'yang overlap. Pesan error akan muncul dengan detail shift yang konflik.',
            S
        ),
        Spacer(1, 4 * mm),
        Paragraph('<b>Visualisasi:</b> Gunakan tab <b>Calendar View</b> untuk melihat seluruh shift '
                  'dalam tampilan kalender mingguan/bulanan, sorting per host atau per account.', S['body']),
        PageBreak(),
    ]

    # ═══ 4. EKSEKUSI HARIAN (HOST) ══════════════════════════════════════
    flow += [
        _section_header(4, 'Eksekusi Harian — Sisi Host', S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Persiapan (T-30 menit):</b>', S['h3']),
        _bullets([
            'Login ke <b>/livehost</b> via HP atau tablet.',
            'Buka tab <b>Shift</b> &gt; cek shift hari ini (badge "Hari Ini").',
            'Buka tab <b>Script</b> &gt; baca script kategori "opening" + script produk hari ini.',
            'Cek perlengkapan: ring light, mic, kamera, sample produk.',
        ], S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Saat Shift Dimulai (T-0):</b>', S['h3']),
        _step_table([
            ('Host', 'Klik tombol <b>Clock In</b> di kartu shift hari ini',
             'Timestamp otomatis tercatat'),
            ('Host', 'Mulai siaran sesuai script', '—'),
            ('Host', 'Pantau interaksi viewer, gunakan script "promotion" &amp; "closing" sesuai timing',
             'Tidak harus baca persis'),
            ('Host', 'Catat kendala yang muncul (jika ada) untuk laporan akhir', '—'),
        ], S),
        Spacer(1, 4 * mm),
        _info_box(
            'Status Kehadiran Otomatis',
            '• <b>On Time</b> — clock in &lt; 15 menit dari jadwal<br/>'
            '• <b>Terlambat</b> — clock in &gt; 15 menit dari jadwal (berdampak pada penalty)<br/>'
            '• <b>Tidak Hadir</b> — tidak clock in sampai shift berakhir',
            S, color=colors.HexColor('#fee2e2')
        ),
        Spacer(1, 4 * mm),
        Paragraph('<b>Saat Shift Berakhir:</b>', S['h3']),
        _step_table([
            ('Host', 'Klik tombol <b>Clock Out</b>',
             'Durasi aktual otomatis dihitung'),
            ('Host', 'Konfirmasi performa: viewers, peak viewers, revenue, orders',
             '(jika diminta oleh admin)'),
            ('Host', 'Logout atau lanjut ke shift berikutnya', '—'),
        ], S),
        PageBreak(),
    ]

    # ═══ 5. SCRIPT & TRAINING ════════════════════════════════════════════
    flow += [
        _section_header(5, 'Script Library & Training', S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Script Library:</b>', S['h3']),
        _bullets([
            '<b>Global Script</b> (account_id = null) bisa dipakai semua host.',
            '<b>Account-specific Script</b> hanya tampil untuk host yang di-assign account tersebut.',
            'Kategori standar: <i>opening, product_intro, promotion, closing, custom</i>.',
            'Host bisa filter script per kategori di portal.',
        ], S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Training Modules:</b>', S['h3']),
        _bullets([
            '<b>Content type</b>: video, pdf, text, quiz.',
            '<b>Duration</b>, <b>passing score</b>, dan <b>expiry months</b> diatur per training.',
            'Training <i>wajib</i> harus diselesaikan sebelum shift produksi pertama.',
            'Host bisa self-mark "Tandai Selesai" untuk training non-quiz. '
            'Untuk training quiz, admin yang merekam score lewat tab Training.',
        ], S),
        Spacer(1, 4 * mm),
        _info_box(
            'Expiry & Recertification',
            'Training dengan <b>expiry_months</b> akan otomatis kadaluarsa setelah periode tersebut. '
            'Admin akan mendapat notifikasi 30 hari sebelum expiry untuk reassign training.',
            S
        ),
        Spacer(1, 6 * mm),
    ]

    # ═══ 6. PERFORMANCE & EVALUASI ═══════════════════════════════════════
    flow += [
        _section_header(6, 'Performance & Evaluasi', S),
        Spacer(1, 3 * mm),
        Paragraph(
            'Setiap shift yang sudah selesai (clock-out) dicatat metriknya untuk evaluasi:',
            S['body']
        ),
        _bullets([
            '<b>Viewers</b> &amp; <b>peak viewers</b> — engagement audience',
            '<b>Revenue</b> dari shift tersebut (Rp)',
            '<b>Orders</b> — jumlah transaksi yang masuk',
            '<b>Items promoted</b> — produk yang dipromosikan',
            '<b>Script adherence score</b> (opsional) — penilaian kepatuhan terhadap script',
            '<b>Challenges faced</b> — kendala yang dicatat host',
        ], S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Analytics Tab (Admin):</b>', S['h3']),
        _bullets([
            'Host Performance — total shifts, hours, revenue, AOV per host.',
            'Shift Analysis — best performing shift type/day/hour.',
            'Top performer leaderboard bulanan.',
        ], S),
        PageBreak(),
    ]

    # ═══ 7. PAYMENT & SYNC KE FINANCE ════════════════════════════════════
    flow += [
        _section_header(7, 'Payment & Sync ke Finance', S),
        Spacer(1, 3 * mm),
        Paragraph('<b>Formula Standar:</b>', S['h3']),
        _kv_table([
            ('Base Pay', '<b>jam_aktual × hourly_rate</b>'),
            ('Bonus', 'Konfigurable per shift (revenue target, viewer target, dll)'),
            ('Penalty', 'Late / no-show / mismatch script (jika diaktifkan)'),
            ('Total Pay', '<b>Base Pay + Bonus − Penalty</b>'),
        ], S),
        Spacer(1, 4 * mm),
        Paragraph('<b>Proses Sync ke Finance (per akhir bulan):</b>', S['h3']),
        _step_table([
            ('Admin', 'Buka tab <b>Payment</b>, pilih bulan periode',
             'Default: bulan berjalan'),
            ('Admin', 'Klik <b>Calculate Payments</b> &mdash; sistem akan menjumlahkan '
             'semua shift status "completed" per host', 'Preview muncul'),
            ('Supervisor', 'Review &amp; setujui rekap', 'Pastikan tidak ada anomali'),
            ('Admin', 'Klik <b>Sync to Finance</b>', 'Status shift &rarr; <i>synced_to_finance</i>'),
            ('Sistem', 'Auto-create entry di koleksi <b>payroll_entries</b> dengan '
             '<i>status = pending_approval</i> &amp; <i>source_module = marketing_livehost</i>',
             'Finance review &amp; approve di Portal Keuangan'),
            ('Host', 'Dapat notifikasi <b>"Pembayaran Disinkronisasi ke Finance"</b> via SSE',
             'Real-time'),
        ], S),
        Spacer(1, 4 * mm),
        _info_box(
            'Penting — Idempoten',
            'Sync hanya berlaku untuk shift yang belum pernah di-sync (payment_status != '
            'synced_to_finance). Jika ada kesalahan, koreksi entry di Portal Keuangan, jangan '
            're-sync shift yang sama.',
            S, color=colors.HexColor('#fee2e2')
        ),
        PageBreak(),
    ]

    # ═══ 8. REAL-TIME NOTIFICATIONS ══════════════════════════════════════
    flow += [
        _section_header(8, 'Real-Time Notifications (SSE)', S),
        Spacer(1, 3 * mm),
        Paragraph(
            'Portal LiveHost menggunakan <b>Server-Sent Events</b> untuk push notifikasi '
            'real-time tanpa polling. Koneksi dibuka otomatis saat host login.',
            S['body']
        ),
        Spacer(1, 3 * mm),
        Paragraph('<b>Event yang Memicu Notifikasi:</b>', S['h3']),
        _kv_table([
            ('shift_assigned', 'Admin membuat shift baru untuk host.'),
            ('training_assigned', 'Admin meng-assign training baru.'),
            ('payment_synced', 'Admin sync payment bulan tersebut ke Finance.'),
        ], S),
        Spacer(1, 4 * mm),
        Paragraph('<b>Endpoint:</b>', S['h3']),
        _bullets([
            'SSE Stream: <font face="Courier">GET /api/marketing/livehost/portal/notifications/stream?token=&lt;jwt&gt;</font>',
            'Polling Fallback: <font face="Courier">GET /api/marketing/livehost/portal/notifications</font>',
            'Mark Read: <font face="Courier">POST /api/marketing/livehost/portal/notifications/{id}/read</font>',
            'Mark All Read: <font face="Courier">POST /api/marketing/livehost/portal/notifications/mark-all-read</font>',
        ], S),
        Spacer(1, 6 * mm),
    ]

    # ═══ 9. TROUBLESHOOTING ══════════════════════════════════════════════
    flow += [
        _section_header(9, 'Troubleshooting', S),
        Spacer(1, 3 * mm),
        _kv_table([
            ('Login gagal (Email atau password salah)',
             'Pastikan password awal benar. Setelah 5 percobaan gagal, akun dikunci 15 menit.'),
            ('Clock In gagal — "Shift sudah di-clock in"',
             'Refresh portal. Mungkin sudah ter-clock-in di device lain.'),
            ('Tidak menerima notifikasi real-time',
             'Cek koneksi internet. Refresh halaman akan re-establish SSE connection.'),
            ('Shift tidak muncul di portal host',
             'Cek di admin: status host harus "active" &amp; shift date dalam bulan berjalan.'),
            ('Sync to Finance gagal',
             'Pastikan ada shift dengan status "completed" di bulan tersebut. Cek log backend.'),
            ('Training "Tandai Selesai" tidak bisa diklik',
             'Training quiz harus dikerjakan, tidak bisa self-complete. Hubungi admin.'),
        ], S),
        Spacer(1, 6 * mm),
    ]

    # ═══ 10. APPENDIX ════════════════════════════════════════════════════
    flow += [
        _section_header(10, 'Appendix — Quick Reference', S),
        Spacer(1, 3 * mm),
        Paragraph('<b>URL Akses:</b>', S['h3']),
        _kv_table([
            ('Admin Module', 'Portal Marketing → KOL &amp; Creator → LiveHost Management'),
            ('Host Portal (standalone)', '/livehost'),
            ('API base path', '/api/marketing/livehost'),
        ], S),
        Spacer(1, 4 * mm),
        Paragraph('<b>Status Shift:</b>', S['h3']),
        _kv_table([
            ('scheduled', 'Sudah dijadwalkan, belum dimulai.'),
            ('on_time', 'Host clock in tepat waktu (&lt; 15 menit).'),
            ('late', 'Host clock in terlambat (≥ 15 menit).'),
            ('no_show', 'Host tidak clock in sampai shift selesai.'),
            ('completed', 'Shift selesai (sudah clock out).'),
        ], S),
        Spacer(1, 4 * mm),
        Paragraph('<b>Status Payment:</b>', S['h3']),
        _kv_table([
            ('pending', 'Belum dihitung.'),
            ('calculated', 'Sudah dihitung, belum di-sync.'),
            ('synced_to_finance', 'Sudah dikirim ke Finance (payroll_entries).'),
        ], S),
        Spacer(1, 8 * mm),
        HRFlowable(width="100%", thickness=0.6, color=BORDER_LIGHT),
        Spacer(1, 3 * mm),
        Paragraph(
            f'<i>Dokumen ini di-generate otomatis oleh sistem DA25 ERP pada '
            f'{now_wib().strftime("%d %B %Y %H:%M")} WIB.</i>',
            S['caption']
        ),
        Paragraph(f'© {now_wib().year} {company_name}. All rights reserved.', S['caption']),
    ]

    doc.build(flow)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
