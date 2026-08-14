import { motion } from "framer-motion";
import type { StageInfo } from "../types";

const LABELS: Record<string, string> = {
  parser_and_extractor: "Parse & Extract",
  disassembler: "Disassemble",
  transformation_plan: "Plan",
  transformation: "Transform",
  binary_patcher: "Patch",
  cfg_permutator: "CFG Permute",
  signature_randomizer: "Randomize Signature",
};

function label(name: string): string {
  return LABELS[name] ?? name.replace(/_/g, " ");
}

function nodeColor(status: StageInfo["status"]): string {
  switch (status) {
    case "completed":
      return "var(--color-ok)";
    case "running":
      return "var(--color-accent)";
    case "failed":
      return "var(--color-fail)";
    default:
      return "var(--color-idle)";
  }
}

function StageNode({ stage }: { stage: StageInfo }) {
  const color = nodeColor(stage.status);
  return (
    <div className="flex flex-col items-center gap-2 min-w-[68px] max-w-[80px]">
      <div className="relative h-11 w-11 flex items-center justify-center">
        {stage.status === "running" && (
          <motion.span
            className="absolute inset-0 rounded-full"
            style={{ background: color, opacity: 0.35 }}
            animate={{ scale: [1, 1.9, 1], opacity: [0.35, 0, 0.35] }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
        <motion.div
          className="relative h-8 w-8 rounded-full border-2 flex items-center justify-center text-xs font-bold"
          style={{ borderColor: color, background: "var(--color-panel)", color }}
          animate={{ scale: stage.status === "running" ? [1, 1.12, 1] : 1 }}
          transition={{ duration: 1.2, repeat: stage.status === "running" ? Infinity : 0 }}
        >
          {stage.status === "completed" && "✓"}
          {stage.status === "failed" && "✕"}
        </motion.div>
      </div>
      <span
        className="text-[11px] text-center leading-tight"
        style={{ color: stage.status === "pending" ? "#8892a0" : "#e6e9ec" }}
      >
        {label(stage.name)}
      </span>
    </div>
  );
}

export default function PipelineTracker({ stages }: { stages: StageInfo[] }) {
  if (stages.length === 0) return null;

  return (
    <div className="flex items-start overflow-x-auto py-4 px-2">
      {stages.map((stage, i) => (
        <div key={stage.name} className="flex items-start">
          <StageNode stage={stage} />
          {i < stages.length - 1 && (
            <div className="relative top-[22px] w-6 h-[2px] mx-0.5 shrink-0" style={{ background: "var(--color-idle)" }}>
              <motion.div
                className="absolute inset-0"
                style={{ background: "var(--color-ok)", transformOrigin: "left" }}
                initial={{ scaleX: 0 }}
                animate={{ scaleX: stage.status === "completed" ? 1 : 0 }}
                transition={{ duration: 0.4 }}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
