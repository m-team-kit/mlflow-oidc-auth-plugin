import { fetchAllServiceAccounts } from "../services/user-service";
import { useApi } from "./use-api";
import type { UserSummary } from "../../shared/types/user";

export function useAllServiceAccounts() {
  const {
    data: allServiceAccounts,
    isLoading,
    error,
    refetch: refresh,
  } = useApi<UserSummary[]>(fetchAllServiceAccounts);

  return { allServiceAccounts, isLoading, error, refresh };
}
