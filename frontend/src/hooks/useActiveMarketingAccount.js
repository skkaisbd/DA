/**
 * useActiveMarketingAccount
 * Persistent global "active account" context untuk Portal Marketing.
 * Disimpan di localStorage — persists antar navigasi modul.
 */
import { useState, useCallback } from 'react';

const STORAGE_KEY = 'mkt_active_account';

export function useActiveMarketingAccount() {
  const [activeAccount, setActiveAccountState] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const setActiveAccount = useCallback((account) => {
    if (account) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(account));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    setActiveAccountState(account);
  }, []);

  const clearActiveAccount = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setActiveAccountState(null);
  }, []);

  return { activeAccount, setActiveAccount, clearActiveAccount };
}
