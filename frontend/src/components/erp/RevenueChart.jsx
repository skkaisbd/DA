import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const fmtCompact = (n) => {
  if (!n) return '0';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}M`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}jt`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}rb`;
  return n.toLocaleString('id-ID');
};

const fmtFull = (n) => `Rp ${Number(n || 0).toLocaleString('id-ID')}`;
const fmtDateShort = (d) => {
  if (!d) return '';
  const date = new Date(d);
  return date.toLocaleDateString('id-ID', { day: '2-digit', month: 'short' });
};

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="rounded-lg bg-[var(--card-surface)] border border-[var(--glass-border)] p-3 shadow-lg">
      <div className="text-xs text-muted-foreground mb-2">
        {new Date(label).toLocaleDateString('id-ID', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}
      </div>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center justify-between gap-3 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
            {p.name}
          </span>
          <span className="font-semibold">{fmtFull(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

/**
 * RevenueChart — line chart untuk trend revenue total vs live.
 * Data shape: [{ date: 'YYYY-MM-DD', total: number, live: number }, ...]
 */
export function RevenueChart({ data = [], height = 280 }) {
  if (!data || data.length === 0) {
    return (
      <div
        className="h-72 flex items-center justify-center text-sm text-muted-foreground rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)]"
        data-testid="revenue-chart-empty"
      >
        Belum ada data revenue untuk periode ini
      </div>
    );
  }

  return (
    <div data-testid="revenue-chart" style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
            tickFormatter={fmtDateShort}
          />
          <YAxis
            tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
            tickFormatter={fmtCompact}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
          <Line
            type="monotone"
            dataKey="total"
            name="Total Revenue"
            stroke="#60a5fa"
            strokeWidth={2.5}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
          <Line
            type="monotone"
            dataKey="live"
            name="Live Revenue"
            stroke="#f472b6"
            strokeWidth={2.5}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
            strokeDasharray="5 3"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
