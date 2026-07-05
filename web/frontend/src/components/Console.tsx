import { useEffect, useRef } from "react";
import type { LogEvent } from "../types";

function lineColor(event: LogEvent): string {
  if (event.type === "job_failed") return "#ff6b6b";
  if (event.type === "job_completed") return "#3ddc84";
  if (event.type === "stage_started") return "#00b4d8";
  if (event.message.startsWith("ERROR")) return "#ff8f8f";
  if (event.message.startsWith("WARNING")) return "#f5c86a";
  return "#8fdc9a";
}

export default function Console({ logs }: { logs: LogEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [logs.length]);

  return (
    <div
      className="rounded-xl border border-white/10 p-4 h-[360px] overflow-y-auto font-mono text-[12.5px] leading-relaxed"
      style={{ background: "#0f1215" }}
    >
      {logs.length === 0 && <p className="text-white/30">Console output will appear here once a job starts…</p>}
      {logs.map((event, i) => (
        <div key={i} style={{ color: lineColor(event) }} className="whitespace-pre-wrap break-all">
          {event.message}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
