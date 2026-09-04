/**
 * ActiveAccountBar
 * Sticky context bar yang tampil di atas modul marketing untuk menunjukkan
 * akun mana yang sedang aktif. User bisa ganti akun dari sini.
 * State disimpan via useActiveMarketingAccount (localStorage).
 */
import { ChevronDown, Store, X, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { AccountBadge, getPlatformConfig } from './AccountBadge';

/**
 * @param {object[]} accounts        - daftar semua akun platform
 * @param {object|null} activeAccount - akun yang sedang aktif (atau null)
 * @param {function} onAccountChange - dipanggil dengan object akun baru atau null
 * @param {string} [hint]            - teks keterangan singkat
 */
export function ActiveAccountBar({ accounts = [], activeAccount, onAccountChange, hint }) {
  const cfg = activeAccount ? getPlatformConfig(activeAccount.platform) : null;

  const activeAccounts = accounts.filter(a => a.status === 'active' || !a.status);

  return (
    <div
      data-testid="active-account-bar"
      className={`rounded-xl border px-4 py-2.5 flex items-center justify-between gap-3 transition-colors
        ${cfg
          ? `${cfg.bg} ${cfg.border}`
          : 'bg-muted/20 border-border/60'
        }`}
    >
      {/* Left: current active account */}
      <div className="flex items-center gap-2.5 min-w-0 flex-1">
        <Store size={15} className={cfg ? cfg.text : 'text-muted-foreground'} />
        <span className="text-xs text-muted-foreground hidden sm:block shrink-0">
          {hint || 'Akun aktif:'}
        </span>

        {activeAccount ? (
          <AccountBadge account={activeAccount} size="sm" />
        ) : (
          <span className="text-xs text-muted-foreground italic">
            Belum dipilih — pilih akun untuk fokus data & input
          </span>
        )}
      </div>

      {/* Right: dropdown switcher */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs gap-1 shrink-0"
            data-testid="switch-account-btn"
          >
            Ganti Akun <ChevronDown size={11} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          {activeAccounts.length === 0 && (
            <DropdownMenuItem disabled className="text-xs text-muted-foreground">
              Belum ada akun aktif
            </DropdownMenuItem>
          )}
          {activeAccounts.map(acc => {
            const c = getPlatformConfig(acc.platform);
            const isSelected = activeAccount?.id === acc.id;
            return (
              <DropdownMenuItem
                key={acc.id}
                onClick={() => onAccountChange(acc)}
                className="flex items-center gap-2 cursor-pointer"
                data-testid={`switch-to-${acc.id}`}
              >
                <span className="text-base shrink-0">{c.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className={`text-xs font-medium truncate ${isSelected ? c.text : ''}`}>
                    {acc.account_name}
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {c.label} · {acc.account_code}
                  </div>
                </div>
                {isSelected && <Check size={13} className={`shrink-0 ${c.text}`} />}
              </DropdownMenuItem>
            );
          })}

          {activeAccount && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onAccountChange(null)}
                className="text-xs text-muted-foreground cursor-pointer"
                data-testid="clear-active-account"
              >
                <X size={12} className="mr-2" /> Lihat semua akun
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
