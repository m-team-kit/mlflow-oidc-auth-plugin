import { useCallback } from "react";
import { fetchUserQuota } from "../services/user-service";
import type { UserQuota } from "../../shared/types/user";
import { useApi } from "./use-api";

export function useUserQuota(username: string | null) {
  const fetcher = useCallback(
    (signal?: AbortSignal) => {
      if (!username) return Promise.resolve(null as unknown as UserQuota);
      return fetchUserQuota(username, signal);
    },
    [username],
  );

  const { data, isLoading, error, refetch } = useApi<UserQuota>(fetcher);
  return { quota: data, isLoading, error, refetch };
}
