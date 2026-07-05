import type { Analytics, ArtifactInfo, JobDetail, JobSummary, RunOptions } from "../types";

const BASE = "/api";

export async function createJob(file: File, config: File | null, options: RunOptions): Promise<JobDetail> {
  const form = new FormData();
  form.append("file", file);
  if (config) form.append("config", config);
  if (options.count !== undefined) form.append("count", String(options.count));
  if (options.cfg_count !== undefined) form.append("cfg_count", String(options.cfg_count));
  form.append("cfg_enable_subset", String(options.cfg_enable_subset));
  if (options.cfg_subset_pct !== undefined) form.append("cfg_subset_pct", String(options.cfg_subset_pct));
  if (options.cfg_seed !== undefined) form.append("cfg_seed", String(options.cfg_seed));
  form.append("divide_transform", String(options.divide_transform));
  form.append("verbose", String(options.verbose));
  form.append("quiet", String(options.quiet));

  const res = await fetch(`${BASE}/jobs`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listJobs(): Promise<JobSummary[]> {
  const res = await fetch(`${BASE}/jobs`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getJob(id: string): Promise<JobDetail> {
  const res = await fetch(`${BASE}/jobs/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getArtifacts(id: string): Promise<ArtifactInfo[]> {
  const res = await fetch(`${BASE}/jobs/${id}/artifacts`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getAnalytics(id: string): Promise<Analytics> {
  const res = await fetch(`${BASE}/jobs/${id}/analytics`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function artifactUrl(id: string, name: string): string {
  return `${BASE}/jobs/${id}/artifacts/${encodeURIComponent(name)}`;
}

export function streamUrl(id: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${BASE}/jobs/${id}/stream`;
}
