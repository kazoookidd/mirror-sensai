import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http.js";
import { leaves } from "../../api/leaves.js";
import { sectionsFor } from "../../layout/sections.js";
import { LeaveRequestsPage, period } from "./LeaveRequestsPage.jsx";

vi.mock("../../api/leaves.js", () => ({ leaves: { all: vi.fn(), decide: vi.fn() } }));
vi.mock("../../layout/AppShell.jsx", () => ({ AppShell: ({ children }) => <div>{children}</div> }));

const DATA = {
  types: { paid_leave: "Paid leave", bereavement: "Bereavement" },
  statuses: { pending: "Pending", approved: "Approved", refused: "Refused", cancelled: "Cancelled" },
  decisions: ["pending", "approved", "refused"],
  requests: [
    { id: 2, user_id: "emma", email: "emma@example.com", leave_type: "bereavement", type_label: "Bereavement",
      start_date: "2026-11-03", end_date: "2026-11-06", reason: "deuil", status: "pending", status_label: "Pending", created_at: "2026-10-29 12:26:19" },
    { id: 1, user_id: "paul", email: "paul@example.com", leave_type: "paid_leave", type_label: "Paid leave",
      start_date: "2026-08-03", end_date: "2026-08-03", reason: "", status: "cancelled", status_label: "Cancelled", created_at: "2026-07-01 08:00:00" },
  ],
};

const table = () => screen.getByRole("table", { name: "Leave requests" });
const shown = () => within(table()).getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[0].textContent);

describe("LeaveRequestsPage [M1]", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("lists every employee's requests with readable types and statuses", async () => {
    leaves.all.mockResolvedValue(DATA);
    render(<LeaveRequestsPage />);
    expect(await screen.findAllByText("emma@example.com")).toBeTruthy();
    expect(shown()).toEqual(["emmaemma@example.com", "paulpaul@example.com"]);
    const emma = within(table()).getAllByRole("row")[1];
    expect(within(emma).getByText("Bereavement")).toBeTruthy();
    expect(within(emma).getByText("Pending")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("2 of 2");
  });

  it("filters by employee, reason or email", async () => {
    leaves.all.mockResolvedValue(DATA);
    render(<LeaveRequestsPage />);
    await screen.findAllByText("emma@example.com");
    fireEvent.change(screen.getByLabelText("Search the leave requests"), { target: { value: "deuil" } });
    expect(shown()).toEqual(["emmaemma@example.com"]);
    fireEvent.change(screen.getByLabelText("Search the leave requests"), { target: { value: "nobody" } });
    expect(screen.getByText("No request matches these filters.")).toBeTruthy();
  });

  it("explains that only HR accounts can see the requests", async () => {
    leaves.all.mockRejectedValue(new ApiError(403, "Only HR accounts..."));
    render(<LeaveRequestsPage />);
    expect((await screen.findByRole("alert")).textContent).toContain("Only HR accounts");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says when there is no request yet", async () => {
    leaves.all.mockResolvedValue({ ...DATA, requests: [] });
    render(<LeaveRequestsPage />);
    expect(await screen.findByText("No leave requests yet")).toBeTruthy();
  });

  it("lets HR approve a request, and shows who decided", async () => {
    leaves.all.mockResolvedValue(DATA);
    leaves.decide.mockResolvedValue({ request: { ...DATA.requests[0], status: "approved", status_label: "Approved",
      decided_by: "marc" } });
    render(<LeaveRequestsPage />);
    const emma = within(await screen.findByRole("table", { name: "Leave requests" })).getAllByRole("row")[1];
    fireEvent.click(within(emma).getByRole("button", { name: "Status of request #2" }));
    const approved = await screen.findByRole("option", { name: "Approved" });
    // The table clips its content (overflow: hidden): the list must be drawn outside of it.
    expect(within(table()).queryByRole("option")).toBeNull();
    fireEvent.click(approved);
    expect(leaves.decide).toHaveBeenCalledWith(2, "approved");
    expect(await within(emma).findByText("by marc")).toBeTruthy();
    expect(within(emma).getByText("Approved")).toBeTruthy();
  });

  it("keeps a request the employee cancelled out of HR's hands", async () => {
    leaves.all.mockResolvedValue(DATA);
    render(<LeaveRequestsPage />);
    const paul = within(await screen.findByRole("table", { name: "Leave requests" })).getAllByRole("row")[2];
    expect(within(paul).queryByRole("button", { name: /Status of request/ })).toBeNull();
    expect(within(paul).getByText("Cancelled")).toBeTruthy();
  });

  it("says why a decision was refused", async () => {
    leaves.all.mockResolvedValue(DATA);
    leaves.decide.mockRejectedValue(new ApiError(409, "leave request #2 was cancelled by the employee"));
    render(<LeaveRequestsPage />);
    const emma = within(await screen.findByRole("table", { name: "Leave requests" })).getAllByRole("row")[1];
    fireEvent.click(within(emma).getByRole("button", { name: "Status of request #2" }));
    fireEvent.click(await screen.findByRole("option", { name: "Refused" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Request #2: leave request #2 was cancelled");
  });

  it("shows a one-day leave as one date", () => {
    expect(period(DATA.requests[1])).toBe("Aug 3, 2026");
    expect(period(DATA.requests[0])).toBe("Nov 3, 2026 to Nov 6, 2026");
  });
});

describe("sectionsFor", () => {
  it("adds the leave requests for HR accounts only", () => {
    expect(sectionsFor({ account_role: "hr" }).map((section) => section.id)).toContain("leaves");
    expect(sectionsFor({ account_role: "employee" }).map((section) => section.id)).not.toContain("leaves");
    expect(sectionsFor(null).map((section) => section.id)).not.toContain("leaves");
  });
});
