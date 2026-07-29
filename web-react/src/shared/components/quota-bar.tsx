import type { UserQuota } from "../types/user";
import { formatBytes } from "../utils/format-utils";

export function QuotaBar({ quota }: { quota: UserQuota }) {
  if (quota.quota_bytes === null) {
    return (
      <div className="w-full">
        <div className="flex justify-between text-xs mb-1 text-text-primary dark:text-text-primary-dark">
          <span>{formatBytes(quota.used_bytes)} used</span>
          <span className="opacity-60">unlimited</span>
        </div>
        <div className="h-2 rounded-full bg-btn-secondary-bg dark:bg-btn-secondary-bg-dark overflow-hidden">
          <div className="h-full w-0 rounded-full" />
        </div>
      </div>
    );
  }

  const pct = Math.min(quota.used_bytes / quota.quota_bytes, 1);
  const softPct = quota.soft_cap_fraction;
  const isHard = quota.hard_blocked;
  const isSoft = pct >= softPct;

  const barColor = isHard
    ? "bg-red-500"
    : isSoft
      ? "bg-yellow-400"
      : "bg-green-500";

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs mb-1 text-text-primary dark:text-text-primary-dark">
        <span>
          {formatBytes(quota.used_bytes)} / {formatBytes(quota.quota_bytes)}
          {isHard && (
            <span className="ml-2 text-red-500 font-semibold">
              exceeded
            </span>
          )}
        </span>
        <span className="opacity-60">{(pct * 100).toFixed(1)}%</span>
      </div>
      <div className="relative h-2 rounded-full bg-btn-secondary-bg dark:bg-btn-secondary-bg-dark overflow-hidden">
        {/* soft cap marker */}
        <div
          className="absolute top-0 bottom-0 w-px bg-yellow-400 opacity-70 z-10"
          style={{ left: `${softPct * 100}%` }}
        />
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  );
}
