import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { UserDetailsCard } from "./user-details-card";
import { RuntimeConfigProvider } from "../../../shared/context/runtime-config-provider";
import type { CurrentUser } from "../../../shared/types/user";
import type { RuntimeConfig } from "../../../shared/services/runtime-config";

const mockConfig: RuntimeConfig = {
  basePath: "",
  uiPath: "/oidc/ui",
  provider: "Test",
  authenticated: true,
  gen_ai_gateway_enabled: false,
  workspaces_enabled: false,
};

describe("UserDetailsCard", () => {
  const mockUser: CurrentUser = {
    id: 1,
    username: "testuser",
    display_name: "Test User",
    is_admin: true,
    is_service_account: false,
    groups: [
      { id: 1, group_name: "group1" },
      { id: 2, group_name: "group2" },
    ],
    password_expiration: null,
  };

  it("renders user details and groups", () => {
    const { getByText } = render(
      <RuntimeConfigProvider config={mockConfig}>
        <UserDetailsCard currentUser={mockUser} />
      </RuntimeConfigProvider>,
    );

    expect(getByText("Test User")).toBeDefined();
    expect(getByText("testuser")).toBeDefined();
    expect(getByText("group1")).toBeDefined();
    expect(getByText("group2")).toBeDefined();
  });

  it("renders 'N/A' and no group message when data is missing", () => {
    const minimalUser: CurrentUser = {
      id: 2,
      username: "min",
      display_name: "",
      is_admin: false,
      is_service_account: false,
      groups: [],
      password_expiration: null,
    };
    const { getByText, queryByText } = render(
      <RuntimeConfigProvider config={mockConfig}>
        <UserDetailsCard currentUser={minimalUser} />
      </RuntimeConfigProvider>,
    );

    expect(getByText("N/A")).toBeDefined();
    expect(getByText(/not a member of any groups/i)).toBeDefined();
    expect(queryByText(/administrator privileges/i)).toBeNull();
  });
});
