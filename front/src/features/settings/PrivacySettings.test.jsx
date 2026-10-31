import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useApp } from "../../context/AppContext.jsx";
import { PrivacySettings } from "./PrivacySettings.jsx";

vi.mock("../../context/AppContext.jsx", () => ({ useApp: vi.fn() }));
vi.mock("../../api/settings.js", () => ({ settings: { set: vi.fn(), get: vi.fn() } }));

const VALUES = { guardrails: true, guardrails_output: "redact" };

function renderAs(role) {
  useApp.mockReturnValue({ user: { user_id: "u", account_role: role } });
  render(<PrivacySettings values={VALUES} onSaved={vi.fn()} />);
}

describe("PrivacySettings [EV2]", () => {
  afterEach(cleanup);

  it("lets HR change the guardrails", () => {
    renderAs("hr");
    expect(screen.getByRole("switch", { name: "Content guardrails" }).disabled).toBe(false);
    expect(screen.getByRole("radio", { name: "Refuse" }).disabled).toBe(false);
    expect(screen.queryByText(/Set by HR/)).toBeNull();
  });

  it("shows the guardrails to an employee without letting them turn them off", () => {
    renderAs("employee");
    expect(screen.getByRole("switch", { name: "Content guardrails" }).disabled).toBe(true);
    expect(screen.getByRole("radio", { name: "Refuse" }).disabled).toBe(true);
    expect(screen.getByText("Set by HR for every employee.")).toBeTruthy();
  });
});
