import { useAllExperiments } from "../../core/hooks/use-all-experiments";
import { useSearch } from "../../core/hooks/use-search";
import { SearchInput } from "../../shared/components/search-input";
import { EntityListTable } from "../../shared/components/entity-list-table";
import type { ExperimentListItem } from "../../shared/types/entity";
import type { ColumnConfig } from "../../shared/types/table";
import PageContainer from "../../shared/components/page/page-container";
import PageStatus from "../../shared/components/page/page-status";
import { RowActionButton } from "../../shared/components/row-action-button";
import { formatBytes } from "../../shared/utils/format-utils";

export default function ExperimentsPage() {
  const {
    searchTerm,
    submittedTerm,
    handleInputChange,
    handleSearchSubmit,
    handleClearSearch,
  } = useSearch();

  const { isLoading, error, refresh, allExperiments } = useAllExperiments();

  const experimentsList = allExperiments || [];

  const filteredExperiments = experimentsList.filter((experiment) =>
    experiment.name.toLowerCase().includes(submittedTerm.toLowerCase()),
  );

  const renderPermissionsButton = (experiment: ExperimentListItem) => (
    <div className="invisible group-hover:visible">
      <RowActionButton
        entityId={experiment.id}
        route="/experiments"
        buttonText="Manage permissions"
      />
    </div>
  );

  const columnsWithAction: ColumnConfig<ExperimentListItem>[] = [
    {
      header: "Experiment Name",
      render: (item) => item.name,
    },
    {
      header: "Size",
      render: (item) =>
        item.size_bytes !== null && item.size_bytes !== undefined
          ? formatBytes(item.size_bytes)
          : "—",
      className: "flex-shrink-0 text-right tabular-nums",
    },
    {
      header: "Permissions",
      render: (item) => renderPermissionsButton(item),
      className: "flex-shrink-0",
    },
  ];

  return (
    <PageContainer title="Experiments">
      <PageStatus
        isLoading={isLoading}
        loadingText="Loading experiments list..."
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
              placeholder="Search experiments..."
            />
          </div>

          <EntityListTable
            data={filteredExperiments}
            columns={columnsWithAction}
            searchTerm={submittedTerm}
          />
        </>
      )}
    </PageContainer>
  );
}
