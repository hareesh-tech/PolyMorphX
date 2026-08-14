// Validated categorical palette (dark surface #1b1f24) — see dataviz skill.
// Fixed order; never cycle or regenerate a 9th hue.
export const CATEGORICAL = [
  "#3987e5", // 1 blue
  "#199e70", // 2 aqua
  "#c98500", // 3 yellow
  "#008300", // 4 green
  "#9085e9", // 5 violet
  "#e66767", // 6 red
  "#d55181", // 7 magenta
  "#d95926", // 8 orange
] as const;

export const MUTED = "#4b5560";
export const SEQUENTIAL = ["#cde2fb", "#6da7ec", "#3987e5", "#1c5cab", "#0d366b"];

export const TEXT_PRIMARY = "#e6e9ec";
export const TEXT_SECONDARY = "#9aa4ad";
export const TEXT_MUTED = "#6b7480";
export const GRIDLINE = "#2c333b";

// Stable, deterministic slot assignment so the same category always gets the
// same color across jobs and across charts.
const TRANSFORM_TYPE_ORDER = [
  "ZEROING",
  "MOV_ENCODING_SWAP",
  "TEST_AND_SWAP",
  "ARITHMETIC",
  "CMP_SUB_ZERO",
];

const PROTECTED_REASON_ORDER = [
  "AVAILABLE",
  "NO_ALTERNATIVE",
  "CONTROL_FLOW",
  "Control flow instruction",
  "Branch target",
  "RIP-relative addressing",
  "Stack manipulation",
  "Sensitive instruction",
];

function colorFromOrder(key: string, order: string[]): string {
  const idx = order.indexOf(key);
  if (idx >= 0 && idx < CATEGORICAL.length) return CATEGORICAL[idx];
  // Stable fallback: hash the key into a remaining slot instead of cycling arbitrarily.
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return CATEGORICAL[hash % CATEGORICAL.length];
}

export function transformTypeColor(type: string): string {
  return colorFromOrder(type, TRANSFORM_TYPE_ORDER);
}

export function reasonColor(reason: string): string {
  return colorFromOrder(reason, PROTECTED_REASON_ORDER);
}
