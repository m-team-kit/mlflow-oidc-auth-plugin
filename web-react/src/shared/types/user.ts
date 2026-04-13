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

export interface UserQuota {
  username: string;
  user_id: number;
  quota_bytes: number | null;
  soft_cap_fraction: number;
  used_bytes: number;
  hard_blocked: boolean;
  email: string | null;
  last_reconciled_at: string | null;
  soft_notified_at: string | null;
}

export interface UserContextType {
  currentUser: CurrentUser | null;
  setCurrentUser: (user: CurrentUser | null) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  error: Error | null;
  setError: (error: Error | null) => void;
}
