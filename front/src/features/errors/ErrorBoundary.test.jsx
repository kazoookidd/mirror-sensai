import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary.jsx";

function Broken({ crash }) {
  if (crash) throw new Error("render failed");
  return <p>Chat page</p>;
}

function page(path, crash) {
  return <ErrorBoundary resetKey={path}><Broken crash={crash} /></ErrorBoundary>;
}

describe("ErrorBoundary", () => {
  it("shows the error screen instead of a blank page, then recovers on the next page", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const view = render(page("/chat", true));
    expect(screen.getByRole("alert").textContent).toContain("Something went wrong");
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    view.rerender(page("/history", false));
    expect(screen.getByText("Chat page")).toBeTruthy();
  });
});
