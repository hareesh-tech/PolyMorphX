export type JobStatus = "pending" | "running" | "completed" | "failed";
export type StageStatus = "pending" | "running" | "completed" | "failed";

export interface StageInfo {
  name: string;
  status: StageStatus;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface JobSummary {
  id: string;
  status: JobStatus;
  input_name: string;
  created_at: string;
}

export interface JobDetail extends JobSummary {
  stages: StageInfo[];
  error: string | null;
}

export interface LogEvent {
  type: "log" | "stage_started" | "job_completed" | "job_failed";
  message: string;
  stage: string | null;
}

export interface ArtifactInfo {
  name: string;
  size_bytes: number;
}

export interface RunOptions {
  count?: number;
  cfg_count?: number;
  cfg_enable_subset: boolean;
  cfg_subset_pct?: number;
  cfg_seed?: number;
  divide_transform: boolean;
  verbose: boolean;
  quiet: boolean;
}

export interface PlanAnalytics {
  total_instructions: number;
  available: number;
  protected: number;
  protected_reasons: Record<string, number>;
  safety_score_histogram: { bucket: string; count: number }[];
}

export interface TransformAnalytics {
  requested: number;
  applied: number;
  success_rate: number;
  type_distribution: Record<string, number>;
  address_map: { address: number; type: string }[];
}

export interface CfgAnalytics {
  total_swaps: number;
  seed: number | null;
  subset_enabled: boolean | null;
  padding_swaps: number;
  code_swaps: number;
  pairs: { a: number; b: number; size: number; type: string }[];
}

export interface StageDuration {
  stage: string;
  seconds: number;
}

export interface Analytics {
  plan?: PlanAnalytics;
  transform?: TransformAnalytics;
  cfg?: CfgAnalytics;
  stage_durations?: StageDuration[];
  binary?: { original_size: number };
}
