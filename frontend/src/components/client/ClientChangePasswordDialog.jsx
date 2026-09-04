import { useState, useEffect } from 'react';
import { Loader2, KeyRound, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { clientApi } from './clientApi';

export default function ClientChangePasswordDialog({ open, forced, token, onClose, onSuccess }) {
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setOldPwd('');
      setNewPwd('');
      setConfirmPwd('');
    }
  }, [open]);

  if (!open) return null;

  const submit = async (e) => {
    e.preventDefault();
    if (newPwd.length < 6) {
      toast.error('Password baru minimal 6 karakter');
      return;
    }
    if (newPwd !== confirmPwd) {
      toast.error('Konfirmasi password tidak cocok');
      return;
    }
    setSubmitting(true);
    try {
      await clientApi.request('/auth/change-password', {
        method: 'POST',
        token,
        body: { old_password: oldPwd, new_password: newPwd },
      });
      onSuccess();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      data-testid="client-change-password-dialog"
    >
      <div
        className="absolute inset-0 bg-black/55 backdrop-blur-sm"
        onClick={forced ? undefined : onClose}
      />
      <form
        onSubmit={submit}
        className="relative w-full max-w-md rounded-2xl border border-foreground/10 bg-[hsl(var(--background))] p-6 shadow-xl"
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] flex items-center justify-center">
              <KeyRound size={18} />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                {forced ? 'Ganti Password (Wajib)' : 'Ganti Password'}
              </h3>
              <p className="text-xs text-foreground/55 mt-0.5">
                {forced
                  ? 'Untuk keamanan, silakan ganti password sebelum melanjutkan.'
                  : 'Pilih password baru yang kuat dan unik.'}
              </p>
            </div>
          </div>
          {!forced && (
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-foreground/5"
            >
              <X size={16} />
            </button>
          )}
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs uppercase tracking-wider text-foreground/50">
              Password Saat Ini
            </label>
            <input
              type="password"
              required
              value={oldPwd}
              onChange={(e) => setOldPwd(e.target.value)}
              className="w-full mt-1.5 rounded-xl border border-foreground/10 bg-foreground/[0.04] px-3 py-2 text-sm focus:outline-none focus:border-[hsl(var(--primary))]/60"
              data-testid="client-pwd-old"
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-foreground/50">
              Password Baru
            </label>
            <input
              type="password"
              required
              minLength={6}
              value={newPwd}
              onChange={(e) => setNewPwd(e.target.value)}
              className="w-full mt-1.5 rounded-xl border border-foreground/10 bg-foreground/[0.04] px-3 py-2 text-sm focus:outline-none focus:border-[hsl(var(--primary))]/60"
              data-testid="client-pwd-new"
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-foreground/50">
              Konfirmasi Password Baru
            </label>
            <input
              type="password"
              required
              value={confirmPwd}
              onChange={(e) => setConfirmPwd(e.target.value)}
              className="w-full mt-1.5 rounded-xl border border-foreground/10 bg-foreground/[0.04] px-3 py-2 text-sm focus:outline-none focus:border-[hsl(var(--primary))]/60"
              data-testid="client-pwd-confirm"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          {!forced && (
            <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
              Batal
            </Button>
          )}
          <Button type="submit" disabled={submitting} data-testid="client-pwd-submit">
            {submitting ? <Loader2 size={14} className="animate-spin mr-1.5" /> : null}
            Simpan
          </Button>
        </div>
      </form>
    </div>
  );
}
