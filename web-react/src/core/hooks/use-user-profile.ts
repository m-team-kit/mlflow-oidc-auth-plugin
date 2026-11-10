import { useCallback } from "react";
import { fetchUserProfile } from "../services/user-service";
import type { CurrentUser } from "../../shared/types/user";
import { useApi } from "./use-api";

/** One user's profile (admin-only endpoint). Pass null to skip the request. */
export function useUserProfile(username: string | null) {
  const fetcher = useCallback(
    (signal?: AbortSignal) => {
      if (!username) return Promise.resolve(null as unknown as CurrentUser);
      return fetchUserProfile(username, signal);
    },
    [username],
  );

  const { data, isLoading, error, refetch } = useApi<CurrentUser>(fetcher);
  return { profile: data, isLoading, error, refetch };
}
