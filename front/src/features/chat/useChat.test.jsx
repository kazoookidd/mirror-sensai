import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { conversations } from "../history/api.js";
import { chat, commands } from "./api.js";
import { useChat } from "./useChat.js";

const app = { model: "qwen2.5:3b", setModel: vi.fn(), setContext: vi.fn(), refreshConversations: vi.fn() };

vi.mock("../../context/AppContext.jsx", () => ({ useApp: () => app }));
vi.mock("./api.js", () => ({ chat: { send: vi.fn() }, commands: { run: vi.fn() } }));
vi.mock("../history/api.js", () => ({ conversations: { messages: vi.fn() } }));

function streams(...events) {
  chat.send.mockImplementation(async (text, id, onEvent) => events.forEach(([name, data]) => onEvent(name, data)));
}

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
      ["usage", { prompt: 10, completion: 2 }]);
    const { result, onConversation } = setup();
    await act(() => result.current.send("Hi"));
    expect(roles(result.current.messages)).toEqual(["user", "assistant"]);
    expect(result.current.messages[1]).toMatchObject({ text: "Hello", streaming: false });
    expect(result.current.conversation).toEqual({ id: 5, title: "Leave" });
    expect(onConversation).toHaveBeenCalledWith({ id: 5, title: "Leave" });
    expect(app.refreshConversations).toHaveBeenCalled();
    expect(result.current.busy).toBe(false);
  });

  it("sends the next message in the same conversation", async () => {
    streams(["conversation", { id: 5, title: "Leave" }], ["token", { text: "A" }]);
    const { result } = setup();
    await act(() => result.current.send("Hi"));
    await act(() => result.current.send("And then?"));
    expect(chat.send.mock.calls[1][1]).toBe(5);
  });

  it("replaces an empty answer by a failure that keeps the question", async () => {
    streams(["error", { kind: "model" }]);
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
    streams(["token", { text: "Back" }]);
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

  it("loads a saved conversation, and reset empties the thread", async () => {
    conversations.messages.mockResolvedValue({
      conversation: { id: 3, title: "Remote work" },
      messages: [{ role: "user", content: "Rules?" }, { role: "assistant", content: "Two days a week." }],
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
