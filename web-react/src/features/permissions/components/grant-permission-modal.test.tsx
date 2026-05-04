import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { GrantPermissionModal } from "./grant-permission-modal";

describe("GrantPermissionModal", () => {
  it("renders correctly", () => {
    render(
      <GrantPermissionModal
        isOpen={true}
        onClose={() => {}}
        onSave={vi.fn()}
        title="Grant Perms"
        label="User"
        options={["user1", "user2"]}
        type="experiments"
      />,
    );
    expect(screen.getByText("Grant Perms")).toBeInTheDocument();
    expect(screen.getByLabelText(/User/i)).toBeInTheDocument();
  });

  it("filters options based on search input", () => {
    render(
      <GrantPermissionModal
        isOpen={true}
        onClose={() => {}}
        onSave={vi.fn()}
        title="Grant Perms"
        label="User"
        options={["alice", "bob", "charlie"]}
        type="experiments"
      />,
    );

    const searchInput = screen.getByLabelText(/User/i);
    fireEvent.change(searchInput, { target: { value: "ali" } });

    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.queryByText("bob")).not.toBeInTheDocument();
    expect(screen.queryByText("charlie")).not.toBeInTheDocument();
  });

  it("calls onSave with selected values", async () => {
    const handleSave = vi.fn();
    render(
      <GrantPermissionModal
        isOpen={true}
        onClose={() => {}}
        onSave={handleSave}
        title="Grant Perms"
        label="User"
        options={["user1"]}
        type="experiments"
      />,
    );

    fireEvent.change(screen.getByLabelText(/User/i), { target: { value: "use" } });
    fireEvent.click(screen.getByText("user1"));

    const permSelect = screen.getByLabelText(/Permissions/i);
    fireEvent.change(permSelect, { target: { value: "EDIT" } });

    const saveBtn = screen.getByText("Save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(handleSave).toHaveBeenCalledWith("user1", "EDIT");
    });
  });

  it("Save button is disabled until a user is selected", () => {
    render(
      <GrantPermissionModal
        isOpen={true}
        onClose={() => {}}
        onSave={vi.fn()}
        title="Grant Perms"
        label="User"
        options={["user1"]}
        type="experiments"
      />,
    );

    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/User/i), { target: { value: "use" } });
    fireEvent.click(screen.getByText("user1"));
    expect(screen.getByRole("button", { name: "Save" })).not.toBeDisabled();
  });

  it("shows no results message when search yields no matches", () => {
    render(
      <GrantPermissionModal
        isOpen={true}
        onClose={() => {}}
        onSave={vi.fn()}
        title="Grant Perms"
        label="User"
        options={["user1"]}
        type="experiments"
      />,
    );

    const searchInput = screen.getByLabelText(/User/i);
    fireEvent.change(searchInput, { target: { value: "zzz" } });

    expect(screen.getByText(/no users found/i)).toBeInTheDocument();
  });
});