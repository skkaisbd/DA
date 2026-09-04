import { useEffect, useState } from 'react';
import { Mail, Phone, MapPin, Building2, Star, BadgeCheck } from 'lucide-react';
import { clientApi } from './clientApi';

function Field({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-foreground/5 last:border-b-0">
      <div className="w-8 h-8 rounded-lg bg-foreground/5 text-foreground/55 flex items-center justify-center flex-shrink-0">
        <Icon size={15} />
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-foreground/45">{label}</div>
        <div className="text-sm text-foreground mt-0.5">{value || '-'}</div>
      </div>
    </div>
  );
}

export default function ClientProfile({ token, user }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    (async () => {
      setLoading(true);
      try {
        const d = await clientApi.request('/profile', { token });
        if (!cancel) setProfile(d);
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [token]);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse" data-testid="client-profile-loading">
        <div className="h-8 w-40 bg-foreground/10 rounded" />
        <div className="h-64 rounded-2xl bg-foreground/[0.05]" />
      </div>
    );
  }
  if (!profile) {
    return <div className="text-sm text-foreground/50">Profil tidak ditemukan.</div>;
  }

  return (
    <div className="space-y-6" data-testid="client-profile">
      <div>
        <div className="text-xs uppercase tracking-[0.18em] text-foreground/45 mb-1">
          Profil Klien
        </div>
        <h1 className="text-3xl font-bold text-foreground">{profile.name}</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Header card */}
        <div className="lg:col-span-2 rounded-2xl border border-foreground/10 bg-foreground/[0.03] p-6">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 rounded-2xl bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] flex items-center justify-center text-xl font-bold">
              {(profile.name || '?').slice(0, 2).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-mono text-xs text-foreground/55">{profile.code}</div>
              <div className="text-lg font-semibold text-foreground mt-0.5">
                {profile.name}
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                <span className="text-[11px] px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 capitalize">
                  {profile.status || 'active'}
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded-md bg-foreground/10 text-foreground/65 flex items-center gap-1">
                  <Star size={11} fill="currentColor" />
                  {profile.rating || 4.0}
                </span>
                <span className="text-[11px] px-2 py-0.5 rounded-md bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] capitalize">
                  {profile.quality_standard || 'standard'}
                </span>
                {profile.contract_type && (
                  <span className="text-[11px] px-2 py-0.5 rounded-md bg-foreground/10 text-foreground/65">
                    {profile.contract_type === 'monthly_retainer' ? 'Monthly Retainer' : 'Per Order'}
                  </span>
                )}
              </div>
            </div>
          </div>

          {profile.product_specialization?.length > 0 && (
            <div className="mt-5 pt-5 border-t border-foreground/10">
              <div className="text-[11px] uppercase tracking-wider text-foreground/50 mb-2">
                Spesialisasi Produk
              </div>
              <div className="flex flex-wrap gap-1.5">
                {profile.product_specialization.map((s) => (
                  <span
                    key={s}
                    className="text-xs px-2.5 py-1 rounded-md bg-foreground/8 text-foreground/85"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {profile.notes && (
            <div className="mt-5 pt-5 border-t border-foreground/10">
              <div className="text-[11px] uppercase tracking-wider text-foreground/50 mb-1">
                Catatan
              </div>
              <p className="text-sm text-foreground/85">{profile.notes}</p>
            </div>
          )}
        </div>

        {/* Contact card */}
        <div className="rounded-2xl border border-foreground/10 bg-foreground/[0.03] p-2">
          <div className="px-4 pt-4 pb-2">
            <div className="text-xs uppercase tracking-wider text-foreground/50">
              Kontak
            </div>
          </div>
          <div className="px-2">
            <Field icon={BadgeCheck} label="PIC" value={profile.pic_name} />
            <Field icon={Phone} label="Telepon" value={profile.pic_phone} />
            <Field icon={Mail} label="Email" value={profile.pic_email} />
            <Field icon={MapPin} label="Alamat" value={profile.address || profile.city} />
            <Field icon={Building2} label="Akun Login" value={user?.email} />
          </div>
        </div>
      </div>

      {/* Pricing card */}
      <div className="rounded-2xl border border-foreground/10 bg-foreground/[0.03] p-5">
        <div className="text-xs uppercase tracking-wider text-foreground/50 mb-3">
          Komersial
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-foreground/45">
              Standar Harga / pcs
            </div>
            <div className="font-medium text-foreground tabular-nums">
              Rp {Number(profile.standard_rate_per_pcs || 0).toLocaleString('id-ID')}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-foreground/45">
              Term Pembayaran
            </div>
            <div className="font-medium text-foreground uppercase">
              {(profile.payment_terms || 'net_30').replace('_', ' ')}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-foreground/45">
              Kota
            </div>
            <div className="font-medium text-foreground">{profile.city || '-'}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
