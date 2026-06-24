import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { EntityPermissionsManager } from "./entity-permissions-manager";
import * as usePermissionsManagementModule from "../hooks/use-permissions-management";
import * as useAllUsersModule from "../../../core/hooks/use-all-users";
import * as useAllAccountsModule from "../../../core/hooks/use-all-accounts";
import * as useAllGroupsModule from "../../../core/hooks/use-all-groups";
import * as useSearchModule from "../../../core/hooks/use-search";
import type { EntityPermission } from "../../../shared/types/entity";

vi.mock("../hooks/use-permissions-management");
vi.mock("../../../core/hooks/use-all-users");
vi.mock("../../../core/hooks/use-all-accounts");
vi.mock("../../../core/hooks/use-all-groups");
vi.mock("../../../core/hooks/use-search");

describe("EntityPermissionsManager", () => {
  const mockRefresh = vi.fn();
  const mockHandleEditClick = vi.fn();
  const mockHandleSavePermission = vi.fn();
  const mockHandleRemovePermission = vi.fn();
  const mockHandleModalClose = vi.fn();
  const mockHandleGrantPermission = vi.fn().mockResolvedValue(true);

  const mockPermissions: EntityPermission[] = [
    { name: "user1", permission: "READ", kind: "user" },
    { name: "group1", permission: "EDIT", kind: "group" },
  ];

  const defaultManagement = {
    isModalOpen: false,
    editingItem: null,
    isSaving: false,
    handleEditClick: mockHandleEditClick,
    handleSavePermission: mockHandleSavePermission,
    handleRemovePermission: mockHandleRemovePermission,
    handleModalClose: mockHandleModalClose,
    handleGrantPermission: mockHandleGrantPermission,
  };

  const defaultSearch = {
    searchTerm: "",
    submittedTerm: "",
    handleInputChange: vi.fn(),
    handleSearchSubmit: vi.fn(),
    handleClearSearch: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(
      usePermissionsManagementModule,
      "usePermissionsManagement",
    ).mockReturnValue(defaultManagement);
    vi.spyOn(useAllUsersModule, "useAllUsers").mockReturnValue({
      allUsers: [
        { username: "user1", display_name: "User One" },
        { username: "user2", display_name: "User Two" },
      ],
      isLoading: false,
      error: null,
      refresh: vi.fn(),
    });
    vi.spyOn(useAllAccountsModule, "useAllServiceAccounts").mockReturnValue({
      allServiceAccounts: [{ username: "sa1", display_name: "Service Account 1" }],
      isLoading: false,
      error: null,
      refresh: vi.fn(),
    });
    vi.spyOn(useAllGroupsModule, "useAllGroups").mockReturnValue({
      allGroups: ["group1", "group2"],
      isLoading: false,
      error: null,
      refresh: vi.fn(),
    });
    vi.spyOn(useSearchModule, "useSearch").mockReturnValue(defaultSearch);
  });

  const renderManager = (props = {}) => {
    return render(
      <EntityPermissionsManager
        resourceId="res-1"
        resourceName="Resource 1"
        resourceType="experiments"
        permissions={mockPermissions}
        isLoading={false}
        error={null}
        refresh={mockRefresh}
        {...props}
      />,
    );
  };

  it("renders permission table items", () => {
    renderManager();
    expect(screen.getByText("user1")).toBeDefined();
    expect(screen.getByText("group1")).toBeDefined();
    expect(screen.getByText("READ")).toBeDefined();
    expect(screen.getByText("EDIT")).toBeDefined();
  });

  it("renders loading and error states", () => {
    renderManager({ isLoading: true });
    expect(screen.getByText(/Loading permissions/i)).toBeDefined();

    renderManager({ isLoading: false, error: new Error("Failed") });
    expect(screen.getByText(/Failed/i)).toBeDefined();
  });

  it("handles search", () => {
    renderManager();
    const searchInput = screen.getByPlaceholderText(/Search permissions/i);
    fireEvent.change(searchInput, { target: { value: "test" } });
    fireEvent.submit(searchInput.closest("form")!);
    expect(defaultSearch.handleSearchSubmit).toHaveBeenCalled();
  });

  it("opens edit modal", () => {
    vi.spyOn(
      usePermissionsManagementModule,
      "usePermissionsManagement",
    ).mockReturnValue({
      ...defaultManagement,
      isModalOpen: true,
      editingItem: mockPermissions[0],
    });

    renderManager();
    // The title matches "Edit Experiment res-1 permissions for user1"
    expect(screen.getByText(/Edit Experiment/i)).toBeDefined();
    expect(screen.getByText(/permissions for user1/i)).toBeDefined();
  });

  it("opens grant user modal", async () => {
    renderManager();
    const addButton = screen.getByRole("button", { name: /^\+ Add$/ });
    fireEvent.click(addButton);

    expect(screen.getByText(/Grant user permissions/i)).toBeDefined();

    // user1 is already in permissions, so only user2 is available
    fireEvent.change(screen.getByLabelText(/User/i), { target: { value: "user" } });
    fireEvent.click(screen.getByText("User Two"));

    const saveButton = screen.getByRole("button", { name: "Save" });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockHandleGrantPermission).toHaveBeenCalledWith("user2", "READ");
    });
  });

  it("opens grant service account modal", async () => {
    renderManager();
    const addButton = screen.getByRole("button", {
      name: /\+ Add Service Account/i,
    });
    fireEvent.click(addButton);

    expect(
      screen.getByText(/Grant service account permissions/i),
    ).toBeDefined();

    fireEvent.change(screen.getByLabelText(/Service account/i), { target: { value: "sa1" } });
    fireEvent.click(screen.getByText("Service Account 1"));

    const saveButton = screen.getByRole("button", { name: "Save" });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockHandleGrantPermission).toHaveBeenCalledWith("sa1", "READ");
    });
  });

  it("opens grant group modal", async () => {
    renderManager();
    const addButton = screen.getByRole("button", { name: /\+ Add Group/i });
    fireEvent.click(addButton);

    expect(screen.getByText(/Grant group permissions/i)).toBeDefined();

    // group1 is already in permissions, so only group2 is available
    fireEvent.change(screen.getByLabelText(/Group/i), { target: { value: "group" } });
    fireEvent.click(screen.getByText("group2"));

    const saveButton = screen.getByRole("button", { name: "Save" });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockHandleGrantPermission).toHaveBeenCalledWith(
        "group2",
        "READ",
        "group",
      );
    });
  });

  it("handles remove permission", async () => {
    renderManager();
    const removeButtons = screen.getAllByTitle("Remove permission");
    fireEvent.click(removeButtons[0]);

    await waitFor(() => {
      expect(mockHandleRemovePermission).toHaveBeenCalledWith(
        mockPermissions[0],
      );
    });
  });

  it("filters available users/groups correctly", () => {
    // user1 and group1 are already in mockPermissions
    renderManager();

    // Open user grant modal — type to reveal results; user1 should be absent, user2 present
    fireEvent.click(screen.getByRole("button", { name: /^\+ Add$/ }));
    fireEvent.change(screen.getByLabelText(/User/i), { target: { value: "user" } });
    const userModal = screen.getByRole("dialog");
    expect(userModal.textContent).toContain("User Two (user2)");
    expect(userModal.textContent).not.toContain("User One (user1)");

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));

    // Open group grant modal — type to reveal results; group1 absent, group2 present
    fireEvent.click(screen.getByRole("button", { name: /\+ Add Group/i }));
    fireEvent.change(screen.getByLabelText(/Group/i), { target: { value: "group" } });
    const groupModal = screen.getByRole("dialog");
    expect(groupModal.textContent).toContain("group2");
    expect(groupModal.textContent).not.toContain("group1");
  });
});
