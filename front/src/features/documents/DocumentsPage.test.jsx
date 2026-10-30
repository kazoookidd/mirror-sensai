import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/http.js";
import { documents } from "../../api/documents.js";
import { DocumentsPage } from "./DocumentsPage.jsx";

vi.mock("../../api/documents.js", () => ({ documents: { list: vi.fn(), upload: vi.fn(), rename: vi.fn(), remove: vi.fn() } }));
vi.mock("../../layout/AppShell.jsx", () => ({ AppShell: ({ children }) => <div>{children}</div> }));

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };
const doc = (source) => ({ source, status: "indexed", chunks: 2, size: 2048, modified: 1798538400 });
const table = () => screen.getByRole("table", { name: "Imported documents" });

async function openMenu(source, option) {
  const rows = await screen.findByRole("table", { name: "Imported documents" });
  fireEvent.click(within(rows).getByRole("button", { name: `Options for ${source}` }));
  fireEvent.click(screen.getByRole("option", { name: option }));
}

describe("DocumentsPage menu [R1]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    documents.list.mockResolvedValue({ embed_model: "bge-m3", documents: [doc("accord.md"), doc("charte.md")] });
  });
  afterEach(cleanup);

  it("renames a document in place", async () => {
    render(<MemoryRouter future={FUTURE}><DocumentsPage /></MemoryRouter>);
    documents.rename.mockResolvedValue({ document: doc("accord 2026.md") });
    await openMenu("accord.md", "Rename");
    const field = within(table()).getByRole("textbox", { name: "New title" });
    fireEvent.change(field, { target: { value: "accord 2026.md" } });
    fireEvent.keyDown(field, { key: "Enter" });
    await waitFor(() => expect(documents.rename).toHaveBeenCalledWith("accord.md", "accord 2026.md"));
    expect(documents.list).toHaveBeenCalledTimes(2);
  });

  it("deletes a document after a confirmation and shows why when the server refuses", async () => {
    const confirm = vi.spyOn(window, "confirm");
    render(<MemoryRouter future={FUTURE}><DocumentsPage /></MemoryRouter>);
    confirm.mockReturnValueOnce(false);
    await openMenu("charte.md", "Delete");
    expect(documents.remove).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    documents.remove.mockRejectedValueOnce(new ApiError(403, "Only HR accounts can change the knowledge base."));
    await openMenu("charte.md", "Delete");
    expect(await screen.findByText("Only HR accounts can change the knowledge base.")).toBeTruthy();
    expect(documents.remove).toHaveBeenCalledWith("charte.md");
    confirm.mockRestore();
  });
});
