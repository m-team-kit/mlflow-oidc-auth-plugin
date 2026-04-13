import { fetchAllUsers } from "../services/user-service";
import { useApi } from "./use-api";
import type { UserSummary } from "../../shared/types/user";

export function useAllUsers() {
  const {
    data: allUsers,
    isLoading,
    error,
    refetch: refresh,
  } = useApi<UserSummary[]>(fetchAllUsers);

  return { allUsers, isLoading, error, refresh };
}
