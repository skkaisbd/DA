/**
 * NoStoreScopeNotice — panel MENETAP untuk staf yang **belum dipegangi toko**.
 *
 * KENAPA KOMPONEN INI ADA (sesi #10)
 * ----------------------------------
 * F6 menutup kebocoran: staf berlingkup toko yang belum di-assign toko apa pun
 * sekarang melihat angka NOL di seluruh layar marketing. Tetapi "nol tanpa
 * penjelasan" adalah cacat kedua yang sama mahalnya: staf baru menyimpulkan
 * **aplikasinya rusak** (atau lebih buruk: "tokonya tidak berjualan") dan mulai
 * mencari data di tempat lain. Yang dibutuhkan hanyalah satu kalimat yang
 * menyebut SEBAB dan JALAN KELUARNYA — dan kalimat itu harus MENETAP di layar,
 * bukan toast 5 detik.
 *
 * Komponen ini tidak menampilkan apa pun untuk pemakai yang memang melihat semua
 * toko (owner/admin/SPV/manager), dan tidak menampilkan apa pun bila pemakai
 * berlingkup memang sudah punya toko.
 */
import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { currentRole } from '../portalAccess';

const API = process.env.REACT_APP_BACKEND_URL;

// Sama dengan `core.marketing_account_scope.SCOPED_ROLES` (backend = SSOT-nya).
const SCOPED_ROLES = ['staff_marketing', 'pic_toko', 'host_live', 'cs_staff'];

export default function NoStoreScopeNotice({ token, what = 'Angka di layar ini' }) {
  const scoped = SCOPED_ROLES.includes(currentRole());
  const [count, setCount] = useState(null);   // null = belum tahu

  useEffect(() => {
    if (!scoped) return;
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${API}/api/marketing/accounts?status=active`, {
          headers: { Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` },
        });
        const j = res.ok ? await res.json() : [];
        const list = Array.isArray(j) ? j : (j.accounts || j.data || []);
        if (alive) setCount(list.length);
      } catch {
        if (alive) setCount(null);
      }
    })();
    return () => { alive = false; };
  }, [scoped, token]);

  if (!scoped || count === null || count > 0) return null;

  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-50 dark:bg-amber-500/10 p-3 flex gap-2.5"
      data-testid="marketing-no-scope-notice">
      <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
      <div className="text-xs text-amber-900 dark:text-amber-200 leading-relaxed">
        <p className="font-semibold">Belum ada toko yang di-assign kepada Anda.</p>
        <p className="mt-0.5">
          {what} akan tetap <b>0</b> sampai <b>SPV Marketing</b> meng-assign toko Anda
          (Manajemen Akun → tab <b>Assign Staf</b>). Ini bukan berarti tokonya tidak
          berjualan — Anda memang hanya boleh melihat toko yang menjadi tanggung
          jawab Anda.
        </p>
      </div>
    </div>
  );
}
