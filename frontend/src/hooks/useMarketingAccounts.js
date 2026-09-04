/**
 * Shared hook untuk fetch marketing platform accounts.
 * Digunakan oleh semua modul marketing yang butuh dropdown akun.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_ICONS_MAP = {
  shopee: '🛍️',
  tiktok: '🎵',
  tiktokshop: '🎵',
  tokopedia: '🟢',
  instagram: '📷',
  lazada: '🔵',
  blibli: '🔷',
};

export function getPlatformIcon(platform) {
  if (!platform) return '🛒';
  const key = String(platform).toLowerCase();
  return PLATFORM_ICONS_MAP[key] || '🛒';
}

/**
 * useMarketingAccounts hook
 * @param {string} token - auth token
 * @param {object} options - { status: 'active'|'all', autoFetch: boolean }
 * @returns {{ accounts, loading, error, refetch, byId }}
 */
export function useMarketingAccounts(token, options = {}) {
  const { status = 'active', autoFetch = true } = options;
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const authH = useMemo(
    () => ({ Authorization: `Bearer ${token || localStorage.getItem('erp_token')}` }),
    [token]
  );

  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (status && status !== 'all') params.status = status;

      const res = await axios.get(`${API}/api/marketing/accounts`, { headers: authH, params });
      // Backend may return { accounts: [...] } or array directly
      const data = res.data;
      let list = [];
      if (Array.isArray(data)) {
        list = data;
      } else if (Array.isArray(data?.accounts)) {
        list = data.accounts;
      } else if (Array.isArray(data?.data)) {
        list = data.data;
      }
      // Normalize: ensure we have id, name, platform, account_name fields
      list = list.map(a => ({
        id: a.id || a._id,
        name: a.account_name || a.name || a.username || '(no name)',
        account_name: a.account_name || a.name || a.username || '(no name)',
        platform: a.platform || 'unknown',
        username: a.username,
        group: a.group,
        status: a.status,
        health_score: a.health_score,
        ...a,
      }));
      setAccounts(list);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [authH, status]);

  useEffect(() => {
    if (autoFetch) {
      fetchAccounts();
    }
  }, [fetchAccounts, autoFetch]);

  const byId = useMemo(() => {
    const map = {};
    accounts.forEach(a => { map[a.id] = a; });
    return map;
  }, [accounts]);

  return { accounts, loading, error, refetch: fetchAccounts, byId };
}

/**
 * AccountSelector — Reusable shadcn Select dropdown component.
 * Renders consistent option labels: [icon] account_name (platform)
 */
export function formatAccountLabel(acc) {
  if (!acc) return '— Pilih akun —';
  const icon = getPlatformIcon(acc.platform);
  return `${icon} ${acc.account_name || acc.name} (${acc.platform})`;
}
