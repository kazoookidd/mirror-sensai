import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { conversations } from "../../api/conversations.js";
import { useConversationActions } from "./useConversationActions.js";

const app = { refreshConversations: vi.fn() };

vi.mock("../../context/AppContext.jsx", () => ({ useApp: () => app }));
vi.mock("../../api/conversations.js", () => ({ conversations: { rename: vi.fn(), remove: vi.fn() } }));

const FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };

function setup(path) {
  const callbacks = { onRenamed: vi.fn(), onDeleted: vi.fn() };
  const wrapper = ({ children }) => <MemoryRouter initialEntries={[path]} future={FUTURE}>{children}</MemoryRouter>;
  const hook = renderHook(() => ({ actions: useConversationActions(callbacks), location: useLocation() }), { wrapper });
  return { ...hook, callbacks };
}

describe("useConversationActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("renames, then refreshes the recent chats", async () => {
    conversations.rename.mockResolvedValue({ ok: true });
    const { result, callbacks } = setup("/history");
    await act(() => result.current.actions.rename({ id: 3, title: "Old" }, "New"));
    expect(conversations.rename).toHaveBeenCalledWith(3, "New");
    expect(app.refreshConversations).toHaveBeenCalled();
    expect(callbacks.onRenamed).toHaveBeenCalledWith({ id: 3, title: "Old" }, "New");
  });

  it("leaves the chat on screen when it was deleted, even through one of its branches", async () => {
    conversations.remove.mockResolvedValue({ ok: true, deleted: [3, 7] });
    const { result } = setup("/chat/7");
    await act(() => result.current.actions.remove({ id: 3, title: "Leave" }));
    expect(result.current.location.pathname).toBe("/chat");
  });

  it("stays on another chat, and deletes nothing when the confirmation is refused", async () => {
    conversations.remove.mockResolvedValue({ ok: true, deleted: [3] });
    const { result, callbacks } = setup("/chat/5");
    await act(() => result.current.actions.remove({ id: 3, title: "Leave" }));
    expect(result.current.location.pathname).toBe("/chat/5");
    expect(callbacks.onDeleted).toHaveBeenCalled();
    window.confirm.mockReturnValue(false);
    await act(() => result.current.actions.remove({ id: 5, title: "Other" }));
    expect(conversations.remove).toHaveBeenCalledTimes(1);
  });
});
