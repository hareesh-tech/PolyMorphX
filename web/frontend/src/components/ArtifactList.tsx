import type { ArtifactInfo } from "../types";
import { artifactUrl } from "../api/client";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function ArtifactList({ jobId, artifacts }: { jobId: string; artifacts: ArtifactInfo[] }) {
  if (artifacts.length === 0) return null;

  return (
    <div className="rounded-xl border border-white/10 p-4" style={{ background: "var(--color-panel)" }}>
      <h3 className="mb-3 text-sm font-semibold text-white/80">Artifacts</h3>
      <ul className="flex flex-col gap-2">
        {artifacts.map((artifact) => (
          <li key={artifact.name} className="flex items-center justify-between gap-3 text-sm">
            <span className="truncate text-white/80">{artifact.name}</span>
            <div className="flex items-center gap-3 shrink-0">
              <span className="text-xs text-white/40">{formatSize(artifact.size_bytes)}</span>
              <a
                href={artifactUrl(jobId, artifact.name)}
                download
                className="rounded-md px-2.5 py-1 text-xs font-semibold text-black"
                style={{ background: "var(--color-accent)" }}
              >
                Download
              </a>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
