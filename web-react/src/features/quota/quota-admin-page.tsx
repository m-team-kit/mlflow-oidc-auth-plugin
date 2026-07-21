import { SearchInput } from "../../shared/components/search-input";
import { useAllUserQuotas } from "../../core/hooks/use-all-user-quotas";
import { EntityListTable } from "../../shared/components/entity-list-table";
import { QuotaBar } from "../../shared/components/quota-bar";
import { useSearch } from "../../core/hooks/use-search";
import PageContainer from "../../shared/components/page/page-container";
import PageStatus from "../../shared/components/page/page-status";
import { RowActionButton } from "../../shared/components/row-action-button";
import type { ColumnConfig } from "../../shared/types/table";
import type { UserQuota } from "../../shared/types/user";

type QuotaRow = UserQuota & { id: string; [key: string]: unknown };

export default function QuotaAdminPage() {
  const {
    searchTerm,
    submittedTerm,
    handleInputChange,
    handleSearchSubmit,
    handleClearSearch,
  } = useSearch();

  const { quotas, isLoading, error, refresh } = useAllUserQuotas();

  const term = submittedTerm.toLowerCase();
  const rows: QuotaRow[] = (quotas || [])
    .filter(
      (q) =>
        q.username.toLowerCase().includes(term) ||
        (q.display_name?.toLowerCase().includes(term) ?? false) ||
        (q.email?.toLowerCase().includes(term) ?? false),
    )
    .map((q) => ({ ...q, id: q.username }));

  const columns: ColumnConfig<QuotaRow>[] = [
    {
      header: "Username",
      render: ({ username }) => (
        <span className="truncate block" title={username}>
          {username}
        </span>
      ),
    },
    {
      header: "Display Name",
      render: ({ display_name }) => (
        <span className="truncate block" title={display_name ?? undefined}>
          {display_name || "—"}
        </span>
      ),
    },
    {
      header: "Email",
      render: ({ email }) => (
        <span className="truncate block" title={email ?? undefined}>
          {email || "—"}
        </span>
      ),
    },
    {
      header: "Usage",
      render: (quota) => (
        <div className="w-full py-1">
          <QuotaBar quota={quota} />
        </div>
      ),
    },
    {
      header: "Permissions",
      render: ({ username }) => (
        <div className="invisible group-hover:visible">
          <RowActionButton
            entityId={username}
            suffix="/experiments"
            route="/users"
            buttonText="Manage permissions"
          />
        </div>
      ),
      className: "flex-shrink-0",
    },
  ];

  return (
    <PageContainer title="User Quotas">
      <PageStatus
        isLoading={isLoading}
        loadingText="Loading user quotas..."
        error={error}
        onRetry={refresh}
      />

      {!isLoading && !error && (
        <>
          <div className="mb-2">
            <SearchInput
              value={searchTerm}
              onInputChange={handleInputChange}
              onSubmit={handleSearchSubmit}
              onClear={handleClearSearch}
              placeholder="Search by username, display name, or email..."
            />
          </div>
          <EntityListTable
            data={rows}
            searchTerm={submittedTerm}
            columns={columns}
          />
        </>
      )}
    </PageContainer>
  );
}