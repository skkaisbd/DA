/**
 * rbac.jsx — Role-Based Access Control helpers for CV. Dewi Aditya ERP
 *
 * Satu penjaga UI untuk seluruh aplikasi. Sumber izin (urutan pemeriksaan):
 *   1. `role`/`user.role` termasuk super role  -> selalu lolos
 *   2. izin "*"                                -> selalu lolos
 *   3. `hasPerm(key)` bila disediakan pemanggil
 *   4. `user.permissions` (dikirim `/api/auth/me` & `/api/auth/login`)
 *
 * Kompatibel dua gaya pemakaian:
 *   <RequirePerm perm="hr.view" hasPerm={hasPerm} role={userRole}>...</RequirePerm>
 *   <RequirePerm user={user} keys={['roles.manage']}>...</RequirePerm>
 */
import React from 'react';
import { Shield } from 'lucide-react';

const SUPER_ROLES = ['superadmin', 'super_admin', 'admin', 'owner'];

/** Cek izin tanpa komponen — bisa dipakai di logika biasa. */
export function checkPerm({ user, role, hasPerm, perm, keys }) {
  const effectiveRole = String(role || user?.role || '').toLowerCase();
  if (SUPER_ROLES.includes(effectiveRole)) return true;

  const wanted = [perm, ...(Array.isArray(keys) ? keys : [])].filter(Boolean);
  if (wanted.length === 0) return true; // tidak ada syarat -> tampilkan

  const owned = Array.isArray(user?.permissions) ? user.permissions : [];
  if (owned.includes('*')) return true;
  if (wanted.some((k) => owned.includes(k))) return true;

  if (typeof hasPerm === 'function') {
    return wanted.some((k) => Boolean(hasPerm(k)));
  }

  // Tidak ada informasi izin sama sekali -> permisif (jangan mematikan UI lama).
  return owned.length === 0;
}

/**
 * RequirePerm — render children hanya bila izin dimiliki.
 */
export function RequirePerm({ perm, keys, user, hasPerm, role, children, fallback = null }) {
  if (checkPerm({ user, role, hasPerm, perm, keys })) return <>{children}</>;
  return fallback !== null ? <>{fallback}</> : <PermissionDenied />;
}

/**
 * PermissionDenied — Default "access denied" UI shown inside a module.
 */
export function PermissionDenied({ message = 'Anda tidak memiliki akses ke fitur ini.' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 p-12 text-center" data-testid="permission-denied">
      <div className="rounded-full bg-destructive/10 p-4">
        <Shield className="h-8 w-8 text-destructive" />
      </div>
      <h3 className="text-lg font-semibold text-foreground">Akses Ditolak</h3>
      <p className="max-w-xs text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
