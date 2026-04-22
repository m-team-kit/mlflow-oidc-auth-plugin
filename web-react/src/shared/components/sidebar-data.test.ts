import { describe, it, expect } from "vitest";
import { getSidebarData } from "./sidebar-data";

describe("sidebar-data", () => {
  it("returns base links for non-admin without Users or Service Accounts", () => {
    const data = getSidebarData(false, false);
    // Groups, Experiments, Prompts, Models = 4
    expect(data).toHaveLength(4);
    const labels = data.map((item) => item.label);
    expect(labels).not.toContain("Users");
    expect(labels).not.toContain("Service Accounts");
    expect(labels).not.toContain("Trash");
  });

  it("returns extra links for admin including Users and Service Accounts", () => {
    const data = getSidebarData(true, false);
    // 4 base + Users + Service Accounts + Trash + Webhooks = 8
    expect(data).toHaveLength(8);
    const labels = data.map((item) => item.label);
    expect(labels).toContain("Users");
    expect(labels).toContain("Service Accounts");
    expect(labels).toContain("Trash");
    expect(labels).toContain("Webhooks");
  });

  it("returns AI Gateway links when enabled", () => {
    const data = getSidebarData(false, true);
    // 4 base + 3 AI = 7
    expect(data).toHaveLength(7);
    const labels = data.map((item) => item.label);
    expect(labels).toContain("AI Endpoints");
    expect(labels).toContain("AI Secrets");
    expect(labels).toContain("AI Models");
  });

  it("marks the first AI link and first admin link with dividerBefore", () => {
    const data = getSidebarData(true, true);
    const aiEndpoints = data.find((d) => d.label === "AI Endpoints");
    const users = data.find((d) => d.label === "Users");
    expect(aiEndpoints?.dividerBefore).toBe(true);
    expect(users?.dividerBefore).toBe(true);
  });
});