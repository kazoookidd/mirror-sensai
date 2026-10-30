import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { attachments } from "../../api/attachments.js";
import { documents } from "../../api/documents.js";
import { MyFilesPage } from "./MyFilesPage.jsx";

vi.mock("../../api/attachments.js", () => ({ attachments: { mine: vi.fn(), remove: vi.fn() } }));
vi.mock("../../api/documents.js", () => ({ documents: { list: vi.fn() } }));
vi.mock("../../layout/AppShell.jsx", () => ({ AppShell: ({ children }) => <div>{children}</div> }));

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };
const BASE = { embed_model: "bge-m3", documents: [{ source: "loi_teletravail.md", status: "indexed", size: 2048, modified: 1798538400 }] };

const renderPage = () => render(<MemoryRouter future={FUTURE}><MyFilesPage /></MemoryRouter>);
const section = (name) => screen.getByRole("heading", { name }).closest("section");

describe("MyFilesPage [R1]", () => {
  beforeEach(() => { vi.clearAllMocks(); documents.list.mockResolvedValue(BASE); });
  afterEach(cleanup);

  it("lists the files joined to my chats, each leading to its chat, then the HR documents", async () => {
    attachments.mine.mockResolvedValue({ attachments: [
      { id: 2, source: "contrat.pdf", size: 4096, created_at: "2026-10-29 10:00:00", conversation_id: 7, conversation_title: "Mon préavis" },
    ] });
    renderPage();
    expect(await screen.findByText("contrat.pdf")).toBeTruthy();
    const link = within(section("Joined to my chats")).getByRole("link", { name: /Mon préavis/ });
    expect(link.getAttribute("href")).toBe("/chat/7");
    expect(await within(section("HR documents")).findByText("loi_teletravail.md")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Import/ })).toBeNull();
  });

  it("deletes a joined file after a confirmation, and keeps it when cancelled or when the server fails", async () => {
    attachments.mine.mockResolvedValue({ attachments: [
      { id: 2, source: "contrat.pdf", size: 4096, created_at: "2026-10-29 10:00:00", conversation_id: 7, conversation_title: "Mon préavis" },
      { id: 3, source: "courrier.md", size: 512, created_at: "2026-10-29 09:00:00", conversation_id: 8, conversation_title: "Mutuelle" },
    ] });
    const confirm = vi.spyOn(window, "confirm");
    renderPage();
    const button = await screen.findByRole("button", { name: "Delete contrat.pdf" });

    confirm.mockReturnValueOnce(false);
    fireEvent.click(button);
    expect(attachments.remove).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    attachments.remove.mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(button);
    expect((await screen.findByRole("alert")).textContent).toContain("Could not delete contrat.pdf");
    expect(screen.getByText("contrat.pdf")).toBeTruthy();

    confirm.mockReturnValueOnce(true);
    attachments.remove.mockResolvedValueOnce({ deleted: 2 });
    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByText("contrat.pdf")).toBeNull());
    expect(attachments.remove).toHaveBeenLastCalledWith(2);
    expect(screen.getByText("courrier.md")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    confirm.mockRestore();
  });

  it("explains how to join a file when there is none yet", async () => {
    attachments.mine.mockResolvedValue({ attachments: [] });
    renderPage();
    expect(await screen.findByText(/No file yet/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /New chat/ }).getAttribute("href")).toBe("/chat");
  });
});
