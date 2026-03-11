import type { CurrentUser, UserQuota } from "../../../shared/types/user";
import { useUserQuota } from "../../../core/hooks/use-user-quota";

interface UserDetailsCardProps {
  currentUser: CurrentUser;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function QuotaBar({ quota }: { quota: UserQuota }) {
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
            <span className="ml-2 text-red-500 font-semibold">quota exceeded</span>
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

export const UserDetailsCard: React.FC<UserDetailsCardProps> = ({
  currentUser,
}) => {
  const { quota } = useUserQuota(currentUser.username);

  const rowClasses =
    "flex flex-row items-center min-h-(--table-row-height) px-1 hover:bg-table-row-hover dark:hover:bg-table-row-hover transition-colors duration-150 border-b border-btn-secondary-border dark:border-btn-secondary-border-dark";
  const labelClasses =
    "w-1/3 font-semibold text-text-primary dark:text-text-primary-dark";
  const valueClasses =
    "w-2/3 text-ui-text dark:text-ui-text-dark font-mono break-all";

  return (
    <div className="flex flex-col text-sm">
      <div className="divide-y divide-btn-secondary-border dark:divide-btn-secondary-border-dark">
        {[
          { label: "Display Name", value: currentUser.display_name },
          { label: "Username", value: currentUser.username },
        ].map(({ label, value }) => (
          <div key={label} className={rowClasses}>
            <div className={labelClasses}>{label}</div>
            <div className={valueClasses}>{value || "N/A"}</div>
          </div>
        ))}

        <div className={rowClasses}>
          <div className={labelClasses}>Groups</div>
          <div className="w-2/3">
            {currentUser.groups && currentUser.groups.length > 0 ? (
              <div className="flex flex-wrap gap-2 py-0.5">
                {currentUser.groups.map((group) => (
                  <span
                    key={group.id}
                    className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-btn-secondary-bg dark:bg-btn-secondary-bg-dark text-text-primary dark:text-text-primary-dark border border-btn-secondary-border dark:border-btn-secondary-border-dark"
                  >
                    {group.group_name}
                  </span>
                ))}
              </div>
            ) : (
              <p className="italic text-text-primary dark:text-text-primary-dark opacity-60">
                This user is not a member of any groups.
              </p>
            )}
          </div>
        </div>

        {quota && (
          <div className={rowClasses}>
            <div className={labelClasses}>Storage</div>
            <div className="w-2/3 py-1">
              <QuotaBar quota={quota} />
            </div>
          </div>
        )}

        {currentUser.is_admin && (
          <div className="p-1 mt-2 min-h-(--table-row-height) flex items-center">
            <p className="text-logo text-base font-semibold">
              You have administrator privileges. Additional management options
              are available to you.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
