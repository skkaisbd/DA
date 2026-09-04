/**
 * Central API client for Garment ERP
 * Handles authentication, error normalization, and JSON parsing centrally.
 *
 * Usage:
 *   import { apiFetch, apiGet, apiPost, apiPut, apiDelete } from '../lib/api';
 *
 *   const data = await apiGet('/production-pos?page=1');
 *   const result = await apiPost('/production-pos', payload);
 */

const BACKEND = process.env.REACT_APP_BACKEND_URL || '';

// ─── Token helpers ─────────────────────────────────────────────────────────
// The app persists auth under 'erp_token' / 'erp_user' (see App.js).
const TOKEN_KEY = 'erp_token';
const USER_KEY = 'erp_user';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// ─── Portal CMT Override ───────────────────────────────────────────────────
// Staf DA boleh MENGISI portal vendor CMT atas nama vendor yang tidak memakai
// sistem. Supaya 11 komponen `engine/Vendor*.jsx` bisa dipakai ULANG APA ADANYA
// (tanpa menyisipkan `?vendor_id=` ke ±40 pemanggilan API — pekerjaan yang
// gampang terlewat satu-dua dan berakibat staf melihat data SELURUH vendor),
// konteksnya dikirim lewat SATU header dan scoping dikerjakan backend.
// SSOT backend: `backend/core/cmt_override.py`.
//
// WAJIB dipasangkan: set saat layar override dibuka, CLEAR saat ditutup.
// `CMTOverridePortalModule` melakukannya di mount/unmount, dan spanduk mode
// override selalu terlihat supaya tidak ada yang mengisi tanpa sadar.
const CMT_OVERRIDE_HEADER = 'X-CMT-Override-Vendor';
let _cmtOverrideVendorId = null;

export function setCmtOverrideVendor(vendorId) {
  _cmtOverrideVendorId = vendorId || null;
}

export function clearCmtOverrideVendor() {
  _cmtOverrideVendorId = null;
}

export function getCmtOverrideVendor() {
  return _cmtOverrideVendorId;
}

// ─── Core fetch wrapper ────────────────────────────────────────────────────
/**
 * Low-level fetch with auto-injected auth header.
 * Returns the raw Response object so callers can inspect status / stream body.
 */
export async function apiFetch(path, options = {}) {
  const token = getToken();
  const { skipAuthRedirect, ...fetchOpts } = options;
  const isFormData = fetchOpts.body instanceof FormData;

  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(!isFormData && fetchOpts.body ? { 'Content-Type': 'application/json' } : {}),
    ...(_cmtOverrideVendorId ? { [CMT_OVERRIDE_HEADER]: _cmtOverrideVendorId } : {}),
    ...(fetchOpts.headers || {}),
  };

  const url = path.startsWith('http') ? path : `${BACKEND}${path.startsWith('/api') ? '' : '/api'}${path}`;

  const res = await fetch(url, { ...fetchOpts, headers });

  // Auto-logout on 401 — but only if we actually had a token (avoid loops on login page).
  // Also honor opt-out via options.skipAuthRedirect for flows that handle 401 themselves (e.g. Login).
  if (res.status === 401 && token && !skipAuthRedirect) {
    clearToken();
    window.location.reload();
    return res;
  }

  return res;
}

// ─── Convenience wrappers ──────────────────────────────────────────────────
export async function apiGet(path) {
  const res = await apiFetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `GET ${path} failed (${res.status})`);
  }
  return res.json();
}

export async function apiPost(path, body) {
  const isFormData = body instanceof FormData;
  const res = await apiFetch(path, {
    method: 'POST',
    body: isFormData ? body : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `POST ${path} failed (${res.status})`);
  }
  return res.json();
}

export async function apiPut(path, body) {
  const res = await apiFetch(path, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `PUT ${path} failed (${res.status})`);
  }
  return res.json();
}

export async function apiDelete(path) {
  const res = await apiFetch(path, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `DELETE ${path} failed (${res.status})`);
  }
  return res.json().catch(() => ({}));
}

// ─── Blob download (PDF / Excel) ───────────────────────────────────────────
export async function apiDownload(path, filename) {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
