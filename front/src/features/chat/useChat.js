import { useCallback, useRef, useState } from "react";
import { useApp } from "../../context/AppContext.jsx";
import { conversations } from "../history/api.js";
import { chat, commands } from "./api.js";

const CHARS_PER_TOKEN = 4;

let nextId = 0;
const newId = () => ++nextId;

// Same estimate as the backend (Memories/Compression.py): about 4 characters per token.
function estimateTokens(history) {
  return Math.round(history.reduce((total, message) => total + message.content.length, 0) / CHARS_PER_TOKEN);
}

export function useChat({ onConversation }) {
  const { model, setModel, setContext, refreshConversations } = useApp();
  const [messages, setMessages] = useState([]);
  const [conversation, setConversation] = useState(null);
  const [busy, setBusy] = useState(false);
  const current = useRef(null);

  const updateAnswer = (id, change) => setMessages((list) => list.map((message) => (
    message.id === id ? { ...message, ...change(message) } : message)));

  const stream = useCallback(async (text) => {
    const answerId = newId();
    setMessages((list) => [...list, { id: answerId, role: "assistant", text: "", model, streaming: true }]);
    setBusy(true);
    let failure = null;
    try {
      await chat.send(text, current.current?.id ?? null, (name, data) => {
        if (name === "conversation" && !current.current) {
          current.current = data;
          setConversation(data);
          onConversation(data);
        } else if (name === "context") {
          setContext({ tokens: data.tokens, budget: data.budget });
        } else if (name === "token") {
          updateAnswer(answerId, (message) => ({ text: message.text + data.text }));
        } else if (name === "answer") {
          updateAnswer(answerId, () => ({ text: data.text }));
        } else if (name === "usage") {
          setContext((context) => ({ ...context, tokens: data.prompt + data.completion }));
        } else if (name === "error") {
          failure = data.kind;
        }
      });
    } catch {
      failure = failure ?? "other";
    }
    setMessages((list) => {
      const done = list.map((message) => (message.id === answerId ? { ...message, streaming: false } : message))
        .filter((message) => message.id !== answerId || message.text.trim());
      return failure ? [...done, { id: newId(), role: "failure", kind: failure, text }] : done;
    });
    setBusy(false);
    refreshConversations();
  }, [model, onConversation, setContext, refreshConversations]);

  const send = useCallback((text) => {
    setMessages((list) => [...list, { id: newId(), role: "user", text }]);
    return stream(text);
  }, [stream]);

  const runCommand = useCallback(async (text, localOutput) => {
    const id = newId();
    setMessages((list) => [...list, { id, role: "command", text, output: localOutput, pending: localOutput === undefined }]);
    if (localOutput !== undefined) return;
    setBusy(true);
    try {
      const result = await commands.run(text);
      updateAnswer(id, () => ({ output: result.output, pending: false }));
      setModel(result.model);
    } catch (failure) {
      updateAnswer(id, () => ({ error: failure.message, pending: false }));
    }
    setBusy(false);
  }, [setModel]);

  const retry = useCallback((failure) => {
    setMessages((list) => list.filter((message) => message.id !== failure.id));
    return stream(failure.text);
  }, [stream]);

  const load = useCallback(async (id) => {
    const data = await conversations.messages(id);
    const loaded = { id: data.conversation.id, title: data.conversation.title };
    current.current = loaded;
    setConversation(loaded);
    setMessages(data.messages.map((message) => ({ id: newId(), role: message.role, text: message.content })));
    setContext((context) => ({ ...context, tokens: estimateTokens(data.messages) }));
  }, [setContext]);

  const reset = useCallback(() => {
    current.current = null;
    setConversation(null);
    setMessages([]);
    setContext((context) => ({ ...context, tokens: 0 }));
  }, [setContext]);

  return { messages, conversation, busy, send, retry, load, reset, runCommand };
}
