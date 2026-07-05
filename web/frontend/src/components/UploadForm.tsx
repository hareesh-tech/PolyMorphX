import { useState } from "react";
import type { RunOptions } from "../types";

interface Props {
  disabled: boolean;
  onSubmit: (file: File, config: File | null, options: RunOptions) => void;
}

const DEFAULT_OPTIONS: RunOptions = {
  cfg_enable_subset: true,
  divide_transform: false,
  verbose: false,
  quiet: false,
};

export default function UploadForm({ disabled, onSubmit }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [config, setConfig] = useState<File | null>(null);
  const [options, setOptions] = useState<RunOptions>(DEFAULT_OPTIONS);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    onSubmit(file, config, options);
  }

  function numberField(key: "count" | "cfg_count" | "cfg_subset_pct" | "cfg_seed", raw: string) {
    setOptions((prev) => ({ ...prev, [key]: raw === "" ? undefined : Number(raw) }));
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-white/70">
          Input binary (.exe / .dll)
          <input
            type="file"
            accept=".exe,.dll"
            required
            disabled={disabled}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-white/90 file:mr-3 file:rounded-md file:border-0 file:bg-[var(--color-accent)] file:px-3 file:py-1.5 file:text-black file:font-semibold"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm text-white/70">
          Config override (optional)
          <input
            type="file"
            accept=".json"
            disabled={disabled}
            onChange={(e) => setConfig(e.target.files?.[0] ?? null)}
            className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-white/90 file:mr-3 file:rounded-md file:border-0 file:bg-white/20 file:px-3 file:py-1.5 file:text-white"
          />
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <NumberInput label="Instruction count" disabled={disabled} onChange={(v) => numberField("count", v)} />
        <NumberInput label="CFG swap count" disabled={disabled} onChange={(v) => numberField("cfg_count", v)} />
        <NumberInput label="CFG subset % (0-1)" step="0.05" disabled={disabled} onChange={(v) => numberField("cfg_subset_pct", v)} />
        <NumberInput label="CFG seed" disabled={disabled} onChange={(v) => numberField("cfg_seed", v)} />
      </div>

      <div className="flex flex-wrap gap-3">
        <Toggle
          label="Enable CFG subset selection"
          checked={options.cfg_enable_subset}
          disabled={disabled}
          onChange={(v) => setOptions((p) => ({ ...p, cfg_enable_subset: v }))}
        />
        <Toggle
          label="Divide & transform"
          checked={options.divide_transform}
          disabled={disabled}
          onChange={(v) => setOptions((p) => ({ ...p, divide_transform: v }))}
        />
        <Toggle
          label="Verbose logging"
          checked={options.verbose}
          disabled={disabled}
          onChange={(v) => setOptions((p) => ({ ...p, verbose: v }))}
        />
        <Toggle
          label="Quiet mode"
          checked={options.quiet}
          disabled={disabled}
          onChange={(v) => setOptions((p) => ({ ...p, quiet: v }))}
        />
      </div>

      <button
        type="submit"
        disabled={disabled || !file}
        className="self-start rounded-lg px-5 py-2.5 font-semibold text-black transition disabled:cursor-not-allowed disabled:opacity-40"
        style={{ background: "var(--color-accent)" }}
      >
        {disabled ? "Running…" : "Launch Transformation"}
      </button>
    </form>
  );
}

function NumberInput({
  label,
  step,
  disabled,
  onChange,
}: {
  label: string;
  step?: string;
  disabled: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-white/60">
      {label}
      <input
        type="number"
        step={step ?? "1"}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-white/15 bg-white/5 px-2 py-1.5 text-white/90"
      />
    </label>
  );
}

function Toggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-[var(--color-accent)]"
      />
      {label}
    </label>
  );
}
