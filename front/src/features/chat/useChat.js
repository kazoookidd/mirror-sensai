import { useCallback, useRef, useState } from "react";
import { useApp } from "../../context/AppContext.jsx";
import { conversations } from "../../api/conversations.js";
import { chat, commands } from "../../api/chat.js";

const CHARS_PER_TOKEN = 4;

let nextId = 0;
const newId = () => ++nextId;

// Same estimate as the backend (Memories/Compression.py): about 4 characters per token.
function estimateTokens(history) {
  return Math.round(history.reduce((total, message) => total + message.content.length, 0) / CHARS_PER_TOKEN);
}

export function useChat({ onConversation }) {
  const { model, setModel, setContext, refreshConversations, refreshPersonas } = useApp();
  const [messages, setMessages] = useState([]);
  const [versions, setVersions] = useState([]);
  const [conversation, setConversation] = useState(null);
  const [busy, setBusy] = useState(false);
  const current = useRef(null);

  const updateAnswer = (id, change) => setMessages((list) => list.map((message) => (
    message.id === id ? { ...message, ...change(message) } : message)));

  const refreshVersions = useCallback(async (id) => {
    try {
      setVersions((await conversations.messages(id)).versions);
    } catch {
      setVersions([]);
    }
  }, []);

  const stream = useCallback(async (text, userId, branchFrom = null) => {
    const answerId = newId();
    setMessages((list) => [...list, { id: answerId, role: "assistant", text: "", model, streaming: true }]);
    setBusy(true);
    let failure = null;
    let branch = null;
    let ok = false;
    try {
      await chat.send(text, current.current?.id ?? null, (name, data) => {
        if (name === "conversation" && data.branch) {
          branch = data;
        } else if (name === "conversation" && !current.current) {
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
        } else if (name === "stopped") {
          updateAnswer(answerId, () => ({ stopped: true }));
        } else if (name === "error") {
          failure = data.kind;
        } else if (name === "done") {
          ok = data.ok;
        }
      }, branchFrom);
    } catch {
      failure = failure ?? "other";
    }
    setMessages((list) => {
      const savedBefore = list.filter((message) => message.saved).length;
      const done = list.map((message) => {
        if (ok && message.id === userId)
          return { ...message, saved: true, position: savedBefore };
        if (message.id !== answerId)
          return message;
        return { ...message, streaming: false, ...(ok && { saved: true, position: savedBefore + 1 }) };
      }).filter((message) => message.id !== answerId || message.text.trim() || message.stopped);
      return failure || !ok && !done.some((message) => message.id === answerId)
        ? [...done, { id: newId(), role: "failure", kind: failure ?? "other", text, branchFrom }]
        : done;
    });
    if (ok && branch) {
      current.current = branch;
      setConversation(branch);
      onConversation(branch);
    }
    if (ok && (branch || branchFrom !== null || versions.length)) refreshVersions(current.current.id);
    setBusy(false);
    refreshConversations();
  }, [model, versions.length, onConversation, setContext, refreshConversations, refreshVersions]);

  const send = useCallback((text) => {
    const userId = newId();
    setMessages((list) => [...list, { id: userId, role: "user", text }]);
    return stream(text, userId);
  }, [stream]);

  const branchAt = useCallback((question, text) => {
    const userId = newId();
    setMessages((list) => [...list.slice(0, list.indexOf(question)), { id: userId, role: "user", text }]);
    return stream(text, userId, question.position);
  }, [stream]);

  const edit = useCallback((question, text) => branchAt(question, text), [branchAt]);

  const regenerate = useCallback((answer) => {
    const question = messages.find((message) => message.saved && message.position === answer.position - 1);
    return question ? branchAt(question, question.text) : undefined;
  }, [messages, branchAt]);

  const stop = useCallback(() => chat.stop().catch(() => {}), []);

  const runCommand = useCallback(async (text, localOutput) => {
    const id = newId();
    setMessages((list) => [...list, { id, role: "command", text, output: localOutput, pending: localOutput === undefined }]);
    if (localOutput !== undefined) return;
    setBusy(true);
    try {
      const result = await commands.run(text);
      updateAnswer(id, () => ({ output: result.output, pending: false }));
      setModel(result.model);
      refreshPersonas();
    } catch (failure) {
      updateAnswer(id, () => ({ error: failure.message, pending: false }));
    }
    setBusy(false);
  }, [setModel, refreshPersonas]);

  const retry = useCallback((failure) => {
    const userId = [...messages].reverse().find((message) => message.role === "user")?.id;
    setMessages((list) => list.filter((message) => message.id !== failure.id));
    return stream(failure.text, userId, failure.branchFrom ?? null);
  }, [messages, stream]);

  const load = useCallback(async (id) => {
    const data = await conversations.messages(id);
    const loaded = { id: data.conversation.id, title: data.conversation.title };
    current.current = loaded;
    setConversation(loaded);
    setMessages(data.messages.map((message, position) => (
      { id: newId(), role: message.role, text: message.content, saved: true, position })));
    setVersions(data.versions);
    setContext((context) => ({ ...context, tokens: estimateTokens(data.messages) }));
  }, [setContext]);

  const reset = useCallback(() => {
    current.current = null;
    setConversation(null);
    setMessages([]);
    setVersions([]);
    setContext((context) => ({ ...context, tokens: 0 }));
  }, [setContext]);

  return { messages, versions, conversation, busy, send, edit, regenerate, stop, retry, load, reset, runCommand };
}
