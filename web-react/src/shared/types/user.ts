import type { components } from "../../core/api/schema";

export type UserSummary = {
  username: string;
  display_name: string;
};

export type Group = {
  id: number;
  group_name: string;
};

export type CurrentUser = {
  display_name: string;
  groups: Group[];
  id: number;
  is_admin: boolean;
  is_service_account: boolean;
  password_expiration: string | null;
  username: string;
};

// Generated from the FastAPI OpenAPI spec (see `yarn gen:api`). The backend is
// the single source of truth for this shape — do not hand-edit fields here.
export type UserQuota = components["schemas"]["QuotaResponse"];

export interface UserContextType {
  currentUser: CurrentUser | null;
  setCurrentUser: (user: CurrentUser | null) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  error: Error | null;
  setError: (error: Error | null) => void;
}
