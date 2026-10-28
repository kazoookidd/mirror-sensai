import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { attachments } from "../../api/attachments.js";
import { conversations } from "../../api/conversations.js";
import { chat, commands } from "../../api/chat.js";
import { useChat } from "./useChat.js";

const app = {
  model: "qwen2.5:3b", setModel: vi.fn(), setContext: vi.fn(), refreshConversations: vi.fn(), refreshPersonas: vi.fn(),
};

vi.mock("../../context/AppContext.jsx", () => ({ useApp: () => app }));
vi.mock("../../api/chat.js", () => ({ chat: { send: vi.fn(), stop: vi.fn() }, commands: { run: vi.fn() } }));
vi.mock("../../api/conversations.js", () => ({ conversations: { messages: vi.fn() } }));
vi.mock("../../api/attachments.js", () => ({ attachments: { join: vi.fn() } }));

function streams(...events) {
  chat.send.mockImplementation(async (text, id, onEvent) => events.forEach(([name, data]) => onEvent(name, data)));
}

const DONE = ["done", { ok: true }];

function setup() {
  const onConversation = vi.fn();
  const hook = renderHook(() => useChat({ onConversation }));
  return { ...hook, onConversation };
}

const roles = (messages) => messages.map((message) => message.role);

describe("useChat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("streams an answer and remembers the new conversation", async () => {
    streams(["conversation", { id: 5, title: "Leave" }], ["token", { text: "Hel" }], ["token", { text: "lo" }],
      ["usage", { prompt: 10, completion: 2 }], DONE);
    const { result, onConversation } = setup();
    await act(() => result.current.send("Hi"));
    expect(roles(result.current.messages)).toEqual(["user", "assistant"]);
    expect(result.current.messages[1]).toMatchObject({ text: "Hello", streaming: false, saved: true, position: 1 });
    expect(result.current.messages[0]).toMatchObject({ saved: true, position: 0 });
    expect(result.current.conversation).toEqual({ id: 5, title: "Leave" });
    expect(onConversation).toHaveBeenCalledWith({ id: 5, title: "Leave" });
    expect(app.refreshConversations).toHaveBeenCalled();
    expect(result.current.busy).toBe(false);
  });

  it("sends the next message in the same conversation", async () => {
    streams(["conversation", { id: 5, title: "Leave" }], ["token", { text: "A" }], DONE);
    const { result } = setup();
    await act(() => result.current.send("Hi"));
    await act(() => result.current.send("And then?"));
    expect(chat.send.mock.calls[1][1]).toBe(5);
  });

  it("replaces an empty answer by a failure that keeps the question", async () => {
    streams(["error", { kind: "model" }], ["done", { ok: false }]);
    const { result } = setup();
    await act(() => result.current.send("Hi"));
    expect(roles(result.current.messages)).toEqual(["user", "failure"]);
    expect(result.current.messages[1]).toMatchObject({ kind: "model", text: "Hi" });
  });

  it("reports a network error as 'other', and retry sends the question again", async () => {
    chat.send.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const { result } = setup();
    await act(() => result.current.send("Hi"));
    const failure = result.current.messages[1];
    expect(failure).toMatchObject({ role: "failure", kind: "other" });
    streams(["token", { text: "Back" }], DONE);
    await act(() => result.current.retry(failure));
    expect(roles(result.current.messages)).toEqual(["user", "assistant"]);
    expect(chat.send.mock.calls[1][0]).toBe("Hi");
  });

  it("runs a slash command on the backend and follows the model it reports", async () => {
    commands.run.mockResolvedValue({ output: "Model switched to 'mistral'.", model: "mistral" });
    const { result } = setup();
    await act(() => result.current.runCommand("/model mistral"));
    expect(result.current.messages[0]).toMatchObject({ role: "command", output: "Model switched to 'mistral'.", pending: false });
    expect(app.setModel).toHaveBeenCalledWith("mistral");
    expect(app.refreshPersonas).toHaveBeenCalled();
  });

  it("shows local command output without calling the backend, and backend errors in the result", async () => {
    commands.run.mockRejectedValue(new Error("An answer is already being generated."));
    const { result } = setup();
    await act(() => result.current.runCommand("/help", "/help  Show the commands"));
    await act(() => result.current.runCommand("/models"));
    expect(commands.run).toHaveBeenCalledTimes(1);
    expect(result.current.messages[0].output).toBe("/help  Show the commands");
    expect(result.current.messages[1]).toMatchObject({ error: "An answer is already being generated.", pending: false });
  });

  it("editing a saved question streams the new answer in a branch, then opens it", async () => {
    conversations.messages.mockResolvedValue({
      conversation: { id: 3, title: "Leave" }, versions: [],
      messages: [{ role: "user", content: "Q1" }, { role: "assistant", content: "A1" },
        { role: "user", content: "Q2" }, { role: "assistant", content: "A2" }],
    });
    const { result, onConversation } = setup();
    await act(() => result.current.load(3));
    conversations.messages.mockResolvedValue({ versions: [{ index: 2, current: 2, conversations: [3, 9] }] });
    streams(["conversation", { id: 9, title: "Leave", branch: true }], ["token", { text: "A2 bis" }], DONE);
    await act(() => result.current.edit(result.current.messages[2], "Q2 bis"));
    expect(chat.send.mock.calls[0][0]).toBe("Q2 bis");
    expect(chat.send.mock.calls[0][3]).toBe(2);
    expect(result.current.messages.map((message) => message.text)).toEqual(["Q1", "A1", "Q2 bis", "A2 bis"]);
    expect(result.current.conversation).toMatchObject({ id: 9 });
    expect(onConversation).toHaveBeenCalledWith({ id: 9, title: "Leave", branch: true });
    expect(result.current.versions).toEqual([{ index: 2, current: 2, conversations: [3, 9] }]);
  });

  it("regenerating an answer asks the same question again from its position", async () => {
    conversations.messages.mockResolvedValue({
      conversation: { id: 3, title: "Leave" }, versions: [],
      messages: [{ role: "user", content: "Q1" }, { role: "assistant", content: "A1" }],
    });
    const { result } = setup();
    await act(() => result.current.load(3));
    streams(["conversation", { id: 10, title: "Leave", branch: true }], ["token", { text: "A1 again" }], DONE);
    await act(() => result.current.regenerate(result.current.messages[1]));
    expect(chat.send.mock.calls[0][0]).toBe("Q1");
    expect(chat.send.mock.calls[0][3]).toBe(0);
    expect(result.current.messages.map((message) => message.text)).toEqual(["Q1", "A1 again"]);
  });

  it("keeps a stopped answer and labels it", async () => {
    streams(["conversation", { id: 5, title: "Leave" }], ["token", { text: "Five we" }], ["stopped", {}], DONE);
    chat.stop.mockResolvedValue({ stopping: true });
    const { result } = setup();
    await act(() => result.current.send("Hi"));
    await act(() => result.current.stop());
    expect(chat.stop).toHaveBeenCalled();
    expect(result.current.messages[1]).toMatchObject({ text: "Five we", stopped: true, saved: true });
  });

  it("a stop before any text is shown as stopped, not as an error", async () => {
    streams(["conversation", { id: 5, title: "Leave" }], ["stopped", {}], ["done", { ok: false }]);
    const { result } = setup();
    await act(() => result.current.send("Hi"));
    expect(result.current.messages.map((message) => message.role)).toEqual(["user", "assistant"]);
    expect(result.current.messages[1]).toMatchObject({ text: "", stopped: true });
  });

  it("a failed branch keeps where it started, so retry asks for the branch again", async () => {
    conversations.messages.mockResolvedValue({
      conversation: { id: 3, title: "Leave" }, versions: [],
      messages: [{ role: "user", content: "Q1" }, { role: "assistant", content: "A1" }],
    });
    const { result } = setup();
    await act(() => result.current.load(3));
    streams(["conversation", { id: 11, title: "Leave", branch: true }], ["error", { kind: "model" }], ["done", { ok: false }]);
    await act(() => result.current.edit(result.current.messages[0], "Q1 bis"));
    expect(result.current.conversation).toMatchObject({ id: 3 });
    const failure = result.current.messages.at(-1);
    expect(failure).toMatchObject({ role: "failure", branchFrom: 0 });
    streams(["conversation", { id: 12, title: "Leave", branch: true }], ["token", { text: "ok" }], DONE);
    await act(() => result.current.retry(failure));
    expect(chat.send.mock.calls[1][3]).toBe(0);
  });

  it("shows the action waiting for confirmation on its answer until a command settles it", async () => {
    const card = { title: "Leave request to confirm", plan: "I will file this leave request" };
    streams(["conversation", { id: 5, title: "Leave" }], ["confirmation", card], ["answer", { text: "=== plan ===" }], DONE);
    const { result } = setup();
    await act(() => result.current.send("I take Monday off"));
    expect(result.current.messages[1].confirmation).toEqual(card);
    commands.run.mockResolvedValue({ output: "Still waiting", model: "m", pending: card });
    await act(() => result.current.runCommand("/leaves"));
    expect(result.current.messages[1].confirmation).toEqual(card);
    commands.run.mockResolvedValue({ output: "Dropped", model: "m", pending: null });
    await act(() => result.current.runCommand("/cancel"));
    expect(result.current.messages[1].confirmation).toBeNull();
  });

  it("puts the waiting action back on the last answer when the conversation is reloaded", async () => {
    const card = { title: "Leave request to confirm", plan: "plan" };
    conversations.messages.mockResolvedValue({
      conversation: { id: 5, title: "Leave" }, versions: [], pending: card,
      messages: [{ role: "user", content: "Q" }, { role: "assistant", content: "=== plan ===" }],
    });
    const { result } = setup();
    await act(() => result.current.load(5));
    expect(result.current.messages.map((message) => message.confirmation)).toEqual([undefined, card]);
  });

  it("a file attached before the first message opens the chat, the next ones join it", async () => {
    attachments.join
      .mockResolvedValueOnce({ conversation: { id: 8, title: "contract.md" }, attachment: { source: "contract.md", chunks: 2 } })
      .mockResolvedValueOnce({ conversation: { id: 8, title: "contract.md" }, attachment: { source: "rider.txt", chunks: 1 } })
      .mockRejectedValueOnce(new Error("SENSAI could not read any text in this file (a scanned PDF?)."));
    const { result, onConversation } = setup();
    await act(() => result.current.attach([new File(["a"], "contract.md"), new File(["b"], "rider.txt")]));
    expect(attachments.join.mock.calls.map(([file, id]) => [file.name, id])).toEqual([["contract.md", undefined], ["rider.txt", 8]]);
    expect(onConversation).toHaveBeenCalledWith({ id: 8, title: "contract.md" });
    expect(result.current.attachments.map((item) => item.source)).toEqual(["contract.md", "rider.txt"]);
    await act(() => result.current.attach([new File(["c"], "scan.pdf")]));
    expect(result.current.attaching).toEqual({ name: null, error: "scan.pdf: SENSAI could not read any text in this file (a scanned PDF?)." });
    expect(result.current.attachments).toHaveLength(2);
  });

  it("loads a saved conversation, and reset empties the thread", async () => {
    conversations.messages.mockResolvedValue({
      conversation: { id: 3, title: "Remote work" },
      messages: [{ role: "user", content: "Rules?" }, { role: "assistant", content: "Two days a week." }],
      versions: [],
    });
    const { result } = setup();
    await act(() => result.current.load(3));
    expect(result.current.conversation).toEqual({ id: 3, title: "Remote work" });
    expect(result.current.messages.map((message) => message.text)).toEqual(["Rules?", "Two days a week."]);
    act(() => result.current.reset());
    expect(result.current.messages).toEqual([]);
    expect(result.current.conversation).toBeNull();
  });
});
