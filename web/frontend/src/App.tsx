import { useCallback, useEffect, useRef, useState } from "react";
import { createJob, getArtifacts, getJob, streamUrl } from "./api/client";
import PipelineTracker from "./components/PipelineTracker";
import Console from "./components/Console";
import UploadForm from "./components/UploadForm";
import ArtifactList from "./components/ArtifactList";
import AnalyticsDashboard from "./components/AnalyticsDashboard";
import type { ArtifactInfo, JobDetail, LogEvent, RunOptions } from "./types";

function App() {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyticsTick, setAnalyticsTick] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);

  const refreshJob = useCallback(async (jobId: string) => {
    try {
      const detail = await getJob(jobId);
      setJob(detail);
      setAnalyticsTick((t) => t + 1);
      if (detail.status === "completed" || detail.status === "failed") {
        setArtifacts(await getArtifacts(jobId));
      }
    } catch {
      // transient — the next event will trigger another refresh
    }
  }, []);

  useEffect(() => {
    return () => socketRef.current?.close();
  }, []);

  // Fallback poll: the WebSocket carries live updates, but if it drops or
  // never delivers a message (proxy hiccup, network blip), this keeps the
  // UI from getting stuck showing a stale snapshot.
  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const interval = setInterval(() => void refreshJob(job.id), 4000);
    return () => clearInterval(interval);
  }, [job, refreshJob]);

  async function handleSubmit(file: File, config: File | null, options: RunOptions) {
    setSubmitting(true);
    setError(null);
    setLogs([]);
    setArtifacts([]);
    socketRef.current?.close();

    try {
      const created = await createJob(file, config, options);
      setJob(created);

      const ws = new WebSocket(streamUrl(created.id));
      socketRef.current = ws;

      ws.onmessage = (evt) => {
        const event: LogEvent = JSON.parse(evt.data);
        setLogs((prev) => [...prev, event]);
        if (event.type !== "log") {
          void refreshJob(created.id);
        }
      };
      ws.onclose = () => {
        void refreshJob(created.id);
        setSubmitting(false);
      };
      ws.onerror = () => setSubmitting(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight">
          Poly<span style={{ color: "var(--color-accent)" }}>Morph</span>
        </h1>
        <p className="text-sm text-white/50">Binary transformation pipeline — web console</p>
      </header>

      <section
        className="rounded-2xl border border-white/10 p-6"
        style={{ background: "var(--color-panel)" }}
      >
        <UploadForm disabled={submitting} onSubmit={handleSubmit} />
        {error && <p className="mt-3 text-sm text-[var(--color-fail)]">{error}</p>}
      </section>

      {job && (
        <section
          className="rounded-2xl border border-white/10 p-6 flex flex-col gap-4"
          style={{ background: "var(--color-panel)" }}
        >
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white/80">
              Job {job.id} <span className="text-white/40">— {job.input_name}</span>
            </h2>
            <StatusBadge status={job.status} />
          </div>

          <PipelineTracker stages={job.stages} />
          <Console logs={logs} />
          {job.error && <p className="text-sm text-[var(--color-fail)]">{job.error}</p>}
        </section>
      )}

      {job && <AnalyticsDashboard jobId={job.id} refreshKey={analyticsTick} />}

      {job && <ArtifactList jobId={job.id} artifacts={artifacts} />}
    </div>
  );
}

function StatusBadge({ status }: { status: JobDetail["status"] }) {
  const colors: Record<JobDetail["status"], string> = {
    pending: "var(--color-idle)",
    running: "var(--color-accent)",
    completed: "var(--color-ok)",
    failed: "var(--color-fail)",
  };
  return (
    <span
      className="rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide"
      style={{ color: colors[status], border: `1px solid ${colors[status]}` }}
    >
      {status}
    </span>
  );
}

export default App;
