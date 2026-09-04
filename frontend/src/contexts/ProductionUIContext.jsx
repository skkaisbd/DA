import { createContext, useContext, useState, useCallback } from 'react';

/**
 * ProductionUIContext — Global state untuk Production Wizard & Quick Input Panel
 * Memungkinkan komponen mana pun membuka wizard/panel dengan prefill data.
 */
const ProductionUIContext = createContext(null);

export const useProductionUI = () => {
  const ctx = useContext(ProductionUIContext);
  if (!ctx) throw new Error('useProductionUI harus digunakan dalam ProductionUIProvider');
  return ctx;
};

export const ProductionUIProvider = ({ children }) => {
  // Production Wizard state
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardInitial, setWizardInitial] = useState(null);

  // Quick Input Panel state
  const [quickInputOpen, setQuickInputOpen] = useState(false);
  const [quickInputPrefill, setQuickInputPrefill] = useState(null);

  const openWizard = useCallback((initialData = null) => {
    setWizardInitial(initialData);
    setWizardOpen(true);
  }, []);

  const closeWizard = useCallback(() => {
    setWizardOpen(false);
    setWizardInitial(null);
  }, []);

  const openQuickInput = useCallback((prefillData = null) => {
    setQuickInputPrefill(prefillData);
    setQuickInputOpen(true);
  }, []);

  const closeQuickInput = useCallback(() => {
    setQuickInputOpen(false);
    setQuickInputPrefill(null);
  }, []);

  const value = {
    // Wizard
    wizardOpen,
    wizardInitial,
    openWizard,
    closeWizard,
    // Quick Input
    quickInputOpen,
    quickInputPrefill,
    openQuickInput,
    closeQuickInput,
  };

  return (
    <ProductionUIContext.Provider value={value}>
      {children}
    </ProductionUIContext.Provider>
  );
};
