/**
 * CMTOverrideRecapPanel — pembungkus **tab Harian | Mingguan** di dalam pintu
 * "Input Vendor CMT".
 *
 * ═══════════════════════════════════════════════════════════════════════════
 * KENAPA INDUKNYA YANG MEMEGANG TANGGAL
 * ═══════════════════════════════════════════════════════════════════════════
 * Permintaan owner: dari tab Mingguan, **klik satu kotak hari → langsung lihat
 * Rekap Harian tanggal itu**. Kalau masing-masing tab menyimpan tanggalnya
 * sendiri (seperti sebelum ini), klik kotak hari tidak punya cara memindahkan
 * tab Harian — paling jauh hanya bisa membuka tab Harian pada "hari ini", yang
 * justru menyembunyikan hari yang sedang diselidiki.
 *
 * Karena itu `day` hidup DI SINI dan diturunkan ke kedua tab:
 *   * tab Harian  → `day` = tanggal yang ditampilkan;
 *   * tab Mingguan → `day` = hari TERAKHIR jendela 7 hari bergulir.
 *
 * Konsekuensi yang disengaja: setelah menyelidiki satu hari lalu kembali ke tab
 * Mingguan, jendelanya = 7 hari yang BERAKHIR di hari itu. Itu memang pertanyaan
 * lanjutannya ("pekan sampai hari itu bagaimana?"), dan tombol "7 hari terakhir"
 * selalu tersedia untuk kembali ke hari ini.
 *
 * Tab Harian tetap tab PERTAMA (keputusan owner 4a sesi sebelumnya): yang dibuka
 * staf tiap pagi adalah "siapa yang belum diisi HARI INI".
 */
import { useCallback, useState } from 'react';
import { CalendarDays, CalendarRange } from 'lucide-react';
import CMTOverrideDailyRecap from './CMTOverrideDailyRecap';
import CMTOverrideWeeklyRecap from './CMTOverrideWeeklyRecap';
import { dayLabel, isoToday, shiftDay } from './recapDates';

const TABS = [
  {
    id: 'harian',
    label: 'Harian',
    Icon: CalendarDays,
    hint: 'Siapa yang belum diisi pada satu tanggal',
  },
  {
    id: 'mingguan',
    label: 'Mingguan',
    Icon: CalendarRange,
    hint: 'Siapa yang sering bolong dalam 7 hari terakhir',
  },
];

export default function CMTOverrideRecapPanel({ onOpenVendor, canFill = true }) {
  const [tab, setTab] = useState('harian');
  const [day, setDay] = useState(isoToday);

  // Klik kotak hari di tab Mingguan → pindah ke tab Harian PADA TANGGAL ITU.
  const openDay = useCallback((iso) => {
    if (!iso) return;
    setDay(iso);
    setTab('harian');
  }, []);

  const isToday = day === isoToday();

  return (
    <div className="space-y-3" data-testid="cmt-recap-panel-wrap">
      {/* ── Pemilih tab ─────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-border bg-card p-2 shadow-sm"
        data-testid="cmt-recap-tabs">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-1 flex-wrap gap-1.5" role="tablist"
            aria-label="Pilih tampilan rekap">
            {TABS.map(({ id, label, Icon, hint }) => {
              const active = tab === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  title={hint}
                  onClick={() => setTab(id)}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] ${
                    active
                      ? 'border-blue-600 bg-blue-600 text-white shadow-sm'
                      : 'border-border bg-background text-foreground hover:bg-muted'
                  }`}
                  data-testid={`cmt-recap-tab-${id}`}
                  data-active={active ? 'true' : 'false'}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  <span className="flex flex-col leading-tight">
                    <span className="text-sm font-semibold">{label}</span>
                    <span className={`text-[10px] ${active ? 'text-white/80' : 'text-muted-foreground'}`}>
                      {hint}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          {/* Tanggal yang sedang dipakai KEDUA tab — supaya jelas bahwa keduanya
              berbagi satu tanggal, bukan dua tanggal yang kebetulan mirip. */}
          <div className="flex items-center gap-2 px-1 text-right">
            <div className="text-[11px] leading-tight text-muted-foreground">
              <p className="font-semibold text-foreground" data-testid="cmt-recap-shared-day">
                {tab === 'mingguan' ? '7 hari s/d ' : ''}{dayLabel(day)}
              </p>
              <p>{isToday ? 'hari ini (WIB)' : 'tanggal lain — klik "Hari ini" untuk kembali'}</p>
            </div>
            {!isToday && (
              <button type="button" onClick={() => setDay(isoToday())}
                className="rounded-md border border-blue-300 bg-blue-50 px-2 py-1 text-[11px] font-bold text-blue-700 hover:bg-blue-100"
                data-testid="cmt-recap-panel-today">
                Hari ini
              </button>
            )}
          </div>
        </div>
      </div>

      {tab === 'harian' ? (
        <CMTOverrideDailyRecap
          day={day}
          onDayChange={setDay}
          onOpenVendor={onOpenVendor}
          canFill={canFill}
        />
      ) : (
        <CMTOverrideWeeklyRecap
          endDay={day}
          onEndDayChange={setDay}
          onOpenDay={openDay}
          onOpenVendor={onOpenVendor}
          canFill={canFill}
          shiftDay={shiftDay}
        />
      )}
    </div>
  );
}
