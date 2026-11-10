import { describe, it, expect } from "vitest";
import { getSidebarData } from "./sidebar-data";

describe("sidebar-data", () => {
  it("returns base links for non-admin without Users or Service Accounts", () => {
    const data = getSidebarData(false, false, false);
    // Groups, Experiments, Prompts, Models, MCP Servers = 5
    expect(data).toHaveLength(5);
    const labels = data.map((item) => item.label);
    expect(labels).toContain("MCP Servers");
    expect(labels).not.toContain("Users");
    expect(labels).not.toContain("Service Accounts");
    expect(labels).not.toContain("Trash");
  });

  it("returns extra links for admin including Users and Service Accounts", () => {
    const data = getSidebarData(true, false, false);
    // 5 base + Users + Service Accounts + User Quotas + Trash + Webhooks + SCIM = 11
    expect(data).toHaveLength(11);
    const labels = data.map((item) => item.label);
    expect(labels).toContain("Users");
    expect(labels).toContain("Service Accounts");
    expect(labels).toContain("User Quotas");
    expect(labels).toContain("Trash");
    expect(labels).toContain("Webhooks");
    expect(labels).toContain("SCIM");
  });

  it("returns AI Gateway links when enabled", () => {
    const data = getSidebarData(false, true, false);
    // 5 base + 3 AI = 8
    expect(data).toHaveLength(8);
    const labels = data.map((item) => item.label);
    expect(labels).toContain("AI Endpoints");
    expect(labels).toContain("AI Secrets");
    expect(labels).toContain("AI Models");
  });

  it("marks the first AI link and first admin link with dividerBefore", () => {
    const data = getSidebarData(true, true, false);
    const aiEndpoints = data.find((d) => d.label === "AI Endpoints");
    const users = data.find((d) => d.label === "Users");
    expect(aiEndpoints?.dividerBefore).toBe(true);
    expect(users?.dividerBefore).toBe(true);
  });

  it("returns Workspaces link when workspaces enabled", () => {
    const data = getSidebarData(false, false, true);
    // 5 base + 1 workspace = 6
    expect(data).toHaveLength(6);
    expect(data.map((item) => item.label)).toContain("Workspaces");
  });

  it("returns all links when everything enabled", () => {
    const data = getSidebarData(true, true, true);
    // 5 base + 3 AI + 1 workspace + 6 admin + Workspace rules = 16
    expect(data).toHaveLength(16);
    expect(data.map((item) => item.label)).toContain("AI Endpoints");
    expect(data.map((item) => item.label)).toContain("Workspaces");
    expect(data.map((item) => item.label)).toContain("User Quotas");
    expect(data.map((item) => item.label)).toContain("Trash");
    expect(data.map((item) => item.label)).toContain("Webhooks");
    expect(data.map((item) => item.label)).toContain("SCIM");
    expect(data.map((item) => item.label)).toContain("Workspace rules");
  });
});
