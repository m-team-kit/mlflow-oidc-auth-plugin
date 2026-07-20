import { fetchAllUserQuotas } from "../services/user-service";
import { useApi } from "./use-api";
import type { UserQuota } from "../../shared/types/user";

export function useAllUserQuotas() {
  const {
    data: quotas,
    isLoading,
    error,
    refetch: refresh,
  } = useApi<UserQuota[]>(fetchAllUserQuotas);

  return { quotas, isLoading, error, refresh };
}