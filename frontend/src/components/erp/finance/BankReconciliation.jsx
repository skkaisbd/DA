import { useState } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import { SessionList } from './bankrecon/SessionList';
import { SessionDetail } from './bankrecon/SessionDetail';

// Rekonsiliasi Bank (H-05/H-06): mutasi rekening koran ↔ baris jurnal GL akun bank per rekening kas/bank.
export default function BankReconciliation({ headers }) {
  const [activeSession, setActiveSession] = useState(null);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5" data-testid="bank-recon-module">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center">
          <ArrowLeftRight className="w-5 h-5 text-blue-700" />
        </div>
        <div>
          <h2 className="text-lg font-bold">Rekonsiliasi Bank</h2>
          <p className="text-xs text-muted-foreground">
            Mutasi rekening koran ↔ jurnal GL akun bank · auto-match ±Rp 1.000 & ±3 hari · cek mutasi kas internal vs GL
          </p>
        </div>
      </div>

      {activeSession ? (
        <SessionDetail sessionId={activeSession.id} headers={headers} onBack={() => setActiveSession(null)} />
      ) : (
        <SessionList headers={headers} onOpen={setActiveSession} />
      )}
    </div>
  );
}
