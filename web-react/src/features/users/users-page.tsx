import { SearchInput } from "../../shared/components/search-input";
import { useAllUsers } from "../../core/hooks/use-all-users";
import { EntityListTable } from "../../shared/components/entity-list-table";
import { useSearch } from "../../core/hooks/use-search";
import PageContainer from "../../shared/components/page/page-container";
import PageStatus from "../../shared/components/page/page-status";
import { RowActionButton } from "../../shared/components/row-action-button";
import type { ColumnConfig } from "../../shared/types/table";

export default function UsersPage() {
  const {
    searchTerm,
    submittedTerm,
    handleInputChange,
    handleSearchSubmit,
    handleClearSearch,
  } = useSearch();

  const { isLoading, error, refresh, allUsers } = useAllUsers();

  const usersList = allUsers || [];

  const term = submittedTerm.toLowerCase();
  const filteredUsers = usersList.filter(
    (u) =>
      u.username.toLowerCase().includes(term) ||
      (u.display_name || "").toLowerCase().includes(term),
  );

  const tableData = filteredUsers.map((u) => ({
    id: u.username,
    username: u.username,
    display_name: u.display_name,
  }));

  const renderPermissionsButton = (username: string) => (
    <div className="invisible group-hover:visible">
      <RowActionButton
        entityId={username}
        suffix="/experiments"
        route="/users"
        buttonText="Manage permissions"
      />
    </div>
  );

  const columnsWithAction: ColumnConfig<{
    id: string;
    username: string;
    display_name: string;
  }>[] = [
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
        <span className="truncate block" title={display_name || undefined}>
          {display_name || "—"}
        </span>
      ),
    },
    {
      header: "Permissions",
      render: ({ username }) => renderPermissionsButton(username),
      className: "flex-shrink-0",
    },
  ];

  return (
    <PageContainer title="Users">
      <PageStatus
        isLoading={isLoading}
        loadingText="Loading users list..."
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
              placeholder="Search users..."
            />
          </div>
          <EntityListTable
            data={tableData}
            searchTerm={submittedTerm}
            columns={columnsWithAction}
          />
        </>
      )}
    </PageContainer>
  );
}
