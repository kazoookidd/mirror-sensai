import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { shares } from "../../api/shares.js";
import { SharedPage } from "./SharedPage.jsx";

vi.mock("../../api/shares.js", () => ({ shares: { open: vi.fn() } }));
vi.mock("../auth/ThemeToggle.jsx", () => ({ ThemeToggle: () => null }));

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };

function open(token) {
  return render(
    <MemoryRouter initialEntries={[`/share/${token}`]} future={FUTURE}>
      <Routes><Route path="/share/:token" element={<SharedPage />} /></Routes>
    </MemoryRouter>,
  );
}

describe("SharedPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the shared chat read only", async () => {
    shares.open.mockResolvedValue({
      title: "Paid leave", created_at: "2026-10-28 10:00:00", expires_at: "2026-11-04 10:00:00",
      messages: [{ role: "user", content: "How many days?" }, { role: "assistant", content: "**25** days." }],
    });
    open("abc");
    expect(await screen.findByRole("heading", { name: "Paid leave" })).toBeTruthy();
    expect(shares.open).toHaveBeenCalledWith("abc");
    expect(screen.getByText("How many days?")).toBeTruthy();
    expect(screen.getByText("25").tagName).toBe("STRONG");
    expect(screen.getByText(/link expires on Nov 4, 2026/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Copy|Edit|Regenerate/ })).toBeNull();
  });

  it("explains why a link does not open", async () => {
    shares.open.mockRejectedValue(new Error("This link has expired."));
    open("old");
    expect(await screen.findByText("This link has expired.")).toBeTruthy();
    expect(screen.getByText("Shared chat unavailable")).toBeTruthy();
  });
});
