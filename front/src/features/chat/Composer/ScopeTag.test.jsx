import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useApp } from "../../../context/AppContext.jsx";
import { ScopeTag, describeScope } from "./ScopeTag.jsx";

vi.mock("../../../context/AppContext.jsx", () => ({ useApp: vi.fn() }));

describe("ScopeTag [R2]", () => {
  afterEach(cleanup);

  it("says which documents are searched and searches all of them again", () => {
    const chooseScope = vi.fn().mockResolvedValue();
    useApp.mockReturnValue({ documentScope: { sources: ["accord.pdf"], types: ["md"] }, chooseScope });
    render(<ScopeTag />);
    expect(screen.getByText("Searching only in accord.pdf, .md files")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Search every HR document again" }));
    expect(chooseScope).toHaveBeenCalledWith(null);
  });

  it("is hidden while every document is searched", () => {
    useApp.mockReturnValue({ documentScope: null, chooseScope: vi.fn() });
    const { container } = render(<ScopeTag />);
    expect(container.textContent).toBe("");
    expect(describeScope({ sources: ["a.md", "b.md"], types: [] })).toBe("a.md, b.md");
  });
});
