/**
 * StaffEntryBadge — penanda **"diinput staf DA"** (keputusan owner 3a).
 *
 * KENAPA ADA: tagihan CMT dihitung dari progress produksi. Sebagian vendor CMT
 * tidak memakai sistem, jadi angkanya DIKETIK STAF DA lewat Portal CMT Override.
 * Owner memutuskan fakta itu harus KELIHATAN di layar monitoring & invoice —
 * supaya kalau nanti ada selisih tagihan, jelas angka itu datang dari vendor
 * sendiri atau dari staf. Kalau hanya tersimpan di database, tidak ada gunanya
 * saat orang sedang menatap angka di layar.
 *
 * Satu komponen dipakai bersama semua layar supaya bentuk & artinya tidak
 * bercabang (pelajaran repo: dua penampil = dua arti yang cepat menyimpang).
 *
 * source: 'staff' | 'vendor' | 'mixed' | 'none'
 *   staff  → seluruh angka diketik staf DA        (amber, paling menonjol)
 *   mixed  → sebagian staf, sebagian vendor       (amber bergaris — perlu dicek)
 *   vendor → vendor mengisi sendiri               (tidak ditampilkan, kecuali showVendor)
 *   none   → belum ada setoran                    (tidak ditampilkan)
 */
import { UserCog, Users } from 'lucide-react';

export default function StaffEntryBadge({
  source,
  by,               // string | string[] — nama staf yang mengetik
  qty,              // opsional: jumlah pcs yang diketik staf
  showVendor = false,
  compact = false,
  testId,
}) {
  const names = Array.isArray(by) ? by.filter(Boolean) : (by ? [by] : []);
  const who = names.length ? names.join(', ') : '';

  if (source === 'vendor' || !source || source === 'none') {
    if (!showVendor || source !== 'vendor') return null;
    return (
      <span
        data-testid={testId || 'entry-badge-vendor'}
        title="Vendor mengisi sendiri lewat portalnya"
        className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700"
      >
        <Users className="h-3 w-3" />
        {compact ? 'vendor' : 'diisi vendor'}
      </span>
    );
  }

  const mixed = source === 'mixed';
  const label = compact
    ? (mixed ? 'sebagian staf' : 'staf DA')
    : (mixed ? 'sebagian diinput staf DA' : 'diinput staf DA');
  const tip = [
    mixed
      ? 'Sebagian angka diketik staf DA atas nama vendor, sebagian diisi vendor sendiri.'
      : 'Angka ini diketik staf DA atas nama vendor (vendor tidak memakai sistem).',
    who ? `Diinput oleh: ${who}` : '',
    qty ? `${Number(qty).toLocaleString('id-ID')} pcs berasal dari input staf` : '',
  ].filter(Boolean).join('\n');

  return (
    <span
      data-testid={testId || (mixed ? 'entry-badge-mixed' : 'entry-badge-staff')}
      title={tip}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        mixed
          ? 'border border-dashed border-amber-400 bg-amber-50 text-amber-800'
          : 'border border-amber-300 bg-amber-100 text-amber-800'
      }`}
    >
      <UserCog className="h-3 w-3 flex-shrink-0" />
      <span className="whitespace-nowrap">{label}</span>
      {!compact && qty ? (
        <span className="font-mono">· {Number(qty).toLocaleString('id-ID')} pcs</span>
      ) : null}
    </span>
  );
}
