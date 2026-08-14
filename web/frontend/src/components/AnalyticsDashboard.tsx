import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { getAnalytics } from "../api/client";
import { CATEGORICAL, GRIDLINE, MUTED, SEQUENTIAL, TEXT_MUTED, TEXT_SECONDARY, reasonColor, transformTypeColor } from "../palette";
import type { Analytics } from "../types";

const tooltipStyle = {
  background: "#1b1f24",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 8,
  color: "#e6e9ec",
  fontSize: 12,
};

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 p-4" style={{ background: "var(--color-panel)" }}>
      <h3 className="text-sm font-semibold text-white/85">{title}</h3>
      {subtitle && <p className="text-xs mb-2" style={{ color: TEXT_SECONDARY }}>{subtitle}</p>}
      <div className="mt-2">{children}</div>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 px-4 py-3" style={{ background: "var(--color-panel)" }}>
      <div className="text-[11px] uppercase tracking-wide" style={{ color: TEXT_MUTED }}>
        {label}
      </div>
      <div className="text-2xl font-semibold text-white/90">{value}</div>
    </div>
  );
}

function TransformDonut({ distribution }: { distribution: Record<string, number> }) {
  const data = Object.entries(distribution).map(([type, count]) => ({ name: type, value: count }));
  if (data.length === 0) return <EmptyNote text="No instruction substitutions were applied." />;

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.name} fill={transformTypeColor(d.name)} stroke="var(--color-panel)" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
        <Legend
          verticalAlign="bottom"
          height={36}
          formatter={(value) => <span style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{value}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

function PlanCoverageChart({ available, protectedReasons }: { available: number; protectedReasons: Record<string, number> }) {
  const row: Record<string, number | string> = { name: "Instructions", Available: available };
  const keys = ["Available", ...Object.keys(protectedReasons)];
  for (const [reason, count] of Object.entries(protectedReasons)) row[reason] = count;

  return (
    <ResponsiveContainer width="100%" height={140}>
      <BarChart data={[row]} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid horizontal={false} stroke={GRIDLINE} />
        <XAxis type="number" tick={{ fill: TEXT_MUTED, fontSize: 11 }} axisLine={{ stroke: GRIDLINE }} tickLine={false} />
        <YAxis type="category" dataKey="name" hide />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend formatter={(value) => <span style={{ color: TEXT_SECONDARY, fontSize: 11 }}>{value}</span>} />
        {keys.map((key) => (
          <Bar
            key={key}
            dataKey={key}
            stackId="coverage"
            fill={key === "Available" ? CATEGORICAL[0] : reasonColor(key)}
            barSize={24}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function SafetyHistogram({ histogram }: { histogram: { bucket: string; count: number }[] }) {
  if (histogram.length === 0) return <EmptyNote text="No candidate safety scores to show." />;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={histogram} margin={{ left: 0, right: 8 }}>
        <CartesianGrid vertical={false} stroke={GRIDLINE} />
        <XAxis dataKey="bucket" tick={{ fill: TEXT_MUTED, fontSize: 11 }} axisLine={{ stroke: GRIDLINE }} tickLine={false} />
        <YAxis tick={{ fill: TEXT_MUTED, fontSize: 11 }} axisLine={{ stroke: GRIDLINE }} tickLine={false} allowDecimals={false} />
        <Tooltip contentStyle={tooltipStyle} />
        <Bar dataKey="count" fill={SEQUENTIAL[2]} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function AddressScatter({ points }: { points: { address: number; type: string }[] }) {
  if (points.length === 0) return <EmptyNote text="No applied transforms to map." />;
  const types = Array.from(new Set(points.map((p) => p.type)));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <ScatterChart margin={{ left: 0, right: 16, bottom: 8 }}>
        <CartesianGrid stroke={GRIDLINE} />
        <XAxis
          type="number"
          dataKey="address"
          name="Address"
          tickFormatter={(v) => `0x${Number(v).toString(16)}`}
          tick={{ fill: TEXT_MUTED, fontSize: 11 }}
          axisLine={{ stroke: GRIDLINE }}
          tickLine={false}
        />
        <YAxis type="category" dataKey="type" name="Type" width={140} tick={{ fill: TEXT_MUTED, fontSize: 11 }} axisLine={{ stroke: GRIDLINE }} tickLine={false} />
        <ZAxis range={[40, 40]} />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(value, name) => (name === "Address" ? `0x${Number(value).toString(16)}` : String(value))}
        />
        {types.map((type) => (
          <Scatter
            key={type}
            name={type}
            data={points.filter((p) => p.type === type)}
            fill={transformTypeColor(type)}
            isAnimationActive={false}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function CfgSwapScatter({ pairs }: { pairs: { a: number; b: number; size: number; type: string }[] }) {
  if (pairs.length === 0) return <EmptyNote text="No CFG block swaps were performed." />;
  const groups = ["code", "padding"] as const;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ left: 0, right: 16, bottom: 8 }}>
        <CartesianGrid stroke={GRIDLINE} />
        <XAxis
          type="number"
          dataKey="a"
          name="Block A"
          tickFormatter={(v) => `0x${Number(v).toString(16)}`}
          tick={{ fill: TEXT_MUTED, fontSize: 11 }}
          axisLine={{ stroke: GRIDLINE }}
          tickLine={false}
        />
        <YAxis
          type="number"
          dataKey="b"
          name="Block B"
          tickFormatter={(v) => `0x${Number(v).toString(16)}`}
          tick={{ fill: TEXT_MUTED, fontSize: 11 }}
          axisLine={{ stroke: GRIDLINE }}
          tickLine={false}
        />
        <ZAxis dataKey="size" range={[30, 200]} name="Block size" />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(value, name) => (name === "Block A" || name === "Block B" ? `0x${Number(value).toString(16)}` : String(value))}
        />
        <Legend formatter={(value) => <span style={{ color: TEXT_SECONDARY, fontSize: 12 }}>{value}</span>} />
        {groups.map((type, i) => (
          <Scatter
            key={type}
            name={type}
            data={pairs.filter((p) => p.type === type)}
            fill={CATEGORICAL[i]}
            isAnimationActive={false}
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function StageTimeline({ durations }: { durations: { stage: string; seconds: number }[] }) {
  if (durations.length === 0) return <EmptyNote text="Stage timings will appear once a run finishes." />;
  const total = durations.reduce((sum, d) => sum + d.seconds, 0) || 1;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex w-full h-8 rounded-lg overflow-hidden">
        {durations.map((d, i) => (
          <div
            key={d.stage}
            title={`${d.stage}: ${d.seconds.toFixed(2)}s`}
            style={{
              width: `${(d.seconds / total) * 100}%`,
              background: CATEGORICAL[i % CATEGORICAL.length],
              minWidth: d.seconds > 0 ? 2 : 0,
            }}
            className="border-r-2"
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs" style={{ color: TEXT_SECONDARY }}>
        {durations.map((d, i) => (
          <div key={d.stage} className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: CATEGORICAL[i % CATEGORICAL.length] }} />
            {d.stage.replace(/_/g, " ")} — {d.seconds.toFixed(2)}s
          </div>
        ))}
        <div className="font-medium text-white/70">Total — {total.toFixed(2)}s</div>
      </div>
    </div>
  );
}

function EmptyNote({ text }: { text: string }) {
  return (
    <div className="flex h-24 items-center justify-center text-xs" style={{ color: MUTED }}>
      {text}
    </div>
  );
}

export default function AnalyticsDashboard({ jobId, refreshKey }: { jobId: string; refreshKey: number }) {
  const [data, setData] = useState<Analytics | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAnalytics(jobId).then((res) => {
      if (!cancelled) setData(res);
    });
    return () => {
      cancelled = true;
    };
  }, [jobId, refreshKey]);

  if (!data) return null;
  if (!data.plan && !data.transform && !data.cfg && !data.stage_durations) return null;

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-white/80">Analytics</h2>

      {data.transform && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Instructions analyzed" value={String(data.plan?.total_instructions ?? "—")} />
          <StatTile label="Available transforms" value={String(data.plan?.available ?? "—")} />
          <StatTile label="Applied" value={`${data.transform.applied}/${data.transform.requested}`} />
          <StatTile label="Success rate" value={`${(data.transform.success_rate * 100).toFixed(0)}%`} />
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {data.transform && (
          <Panel title="Applied transform types" subtitle="Distribution of substitutions actually applied">
            <TransformDonut distribution={data.transform.type_distribution} />
          </Panel>
        )}

        {data.plan && (
          <Panel title="Instruction plan coverage" subtitle={`${data.plan.total_instructions} instructions analyzed`}>
            <PlanCoverageChart available={data.plan.available} protectedReasons={data.plan.protected_reasons} />
            <div className="mt-3">
              <SafetyHistogram histogram={data.plan.safety_score_histogram} />
            </div>
          </Panel>
        )}

        {data.transform && (
          <Panel title="Transform address map" subtitle="Where in .text each substitution landed">
            <AddressScatter points={data.transform.address_map} />
          </Panel>
        )}

        {data.cfg && (
          <Panel
            title="CFG block swaps"
            subtitle={`${data.cfg.total_swaps} swaps · seed ${data.cfg.seed ?? "—"} · ${data.cfg.code_swaps} code / ${data.cfg.padding_swaps} padding`}
          >
            <CfgSwapScatter pairs={data.cfg.pairs} />
          </Panel>
        )}
      </div>

      {data.stage_durations && (
        <Panel title="Stage timing" subtitle="Wall-clock time spent in each pipeline stage">
          <StageTimeline durations={data.stage_durations} />
        </Panel>
      )}
    </div>
  );
}
