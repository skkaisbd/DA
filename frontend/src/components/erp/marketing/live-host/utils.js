/**
 * Shared utilities for LiveHost Management Module sub-components.
 * Pure functions only — no React imports.
 */

export const API = process.env.REACT_APP_BACKEND_URL;

export const fmt = (n) => new Intl.NumberFormat('id-ID').format(n || 0);
export const fmtRp = (n) => `Rp ${fmt(n)}`;

/**
 * Build common Authorization header. Accepts the token (or falls back to localStorage).
 * Returns plain object suitable for spread into fetch headers.
 */
export const buildAuthHeader = (token) => ({
  Authorization: `Bearer ${token || (typeof localStorage !== 'undefined' ? localStorage.getItem('erp_token') : '')}`,
});
