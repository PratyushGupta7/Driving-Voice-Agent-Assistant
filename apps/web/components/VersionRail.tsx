import type { VersionEntry } from "@/lib/types";

export function VersionRail({ entries, current }: { entries: VersionEntry[]; current: number }) {
  if (!entries.length) {
    return <p className="text-xs text-[#9a9388]">No mission versions yet.</p>;
  }
  return (
    <ol className="space-y-2">
      {entries.map((entry) => (
        <li key={`${entry.version}-${entry.epoch}`} className="flex items-start gap-2 text-xs">
          <span
            className={`mt-0.5 font-mono ${
              entry.version === current ? "text-[#e8a14a]" : "text-[#9a9388]"
            }`}
          >
            v{entry.version}
          </span>
          <span className={entry.version === current ? "text-[#f4efe6]" : "text-[#9a9388]"}>
            {entry.summary}
          </span>
        </li>
      ))}
    </ol>
  );
}
