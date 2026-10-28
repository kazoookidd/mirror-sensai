import { useCallback, useRef, useState } from "react";
import { useApp } from "../../context/AppContext.jsx";
import { attachments as attachmentsApi } from "../../api/attachments.js";
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
  const [attachments, setAttachments] = useState([]);
  const [attaching, setAttaching] = useState({ name: null, error: "" });
  const current = useRef(null);

  const updateAnswer = (id, change) => setMessages((list) => list.map((message) => (
    message.id === id ? { ...message, ...change(message) } : message)));

  // [A3] One action waits at a time, on the answer that prepared it.
  const showConfirmation = (id, confirmation) => setMessages((list) => list.map((message) => (
    message.id === id ? { ...message, confirmation } : message.confirmation ? { ...message, confirmation: null } : message)));

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
        } else if (name === "trace") {
          // [A1] What streamed before a tool call is the agent's thought: it moves to the trace.
          updateAnswer(answerId, (message) => ({
            steps: [...(message.steps ?? []), { kind: data.kind, text: data.text }],
            ...(data.kind === "thought" && { text: "" }),
          }));
        } else if (name === "confirmation") {
          showConfirmation(answerId, { title: data.title, plan: data.plan });
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
      if (!result.pending) showConfirmation(null, null);
      setModel(result.model);
      refreshPersonas();
    } catch (failure) {
      updateAnswer(id, () => ({ error: failure.message, pending: false }));
    }
    setBusy(false);
  }, [setModel, refreshPersonas]);

  const attach = useCallback(async (files) => {
    for (const file of files) {
      setAttaching({ name: file.name, error: "" });
      try {
        const data = await attachmentsApi.join(file, current.current?.id);
        if (!current.current) {
          current.current = data.conversation;
          setConversation(data.conversation);
          onConversation(data.conversation);
        }
        setAttachments((list) => [...list.filter((item) => item.source !== data.attachment.source), data.attachment]);
      } catch (failure) {
        setAttaching({ name: null, error: `${file.name}: ${failure.message}` });
        return;
      }
    }
    setAttaching({ name: null, error: "" });
  }, [onConversation]);

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
    const loadedMessages = data.messages.map((message, position) => (
      { id: newId(), role: message.role, text: message.content, saved: true, position }));
    const last = loadedMessages.at(-1);
    if (data.pending && last?.role === "assistant") last.confirmation = data.pending;
    setMessages(loadedMessages);
    setVersions(data.versions);
    setAttachments(data.attachments ?? []);
    setContext((context) => ({ ...context, tokens: estimateTokens(data.messages) }));
  }, [setContext]);

  const reset = useCallback(() => {
    current.current = null;
    setConversation(null);
    setMessages([]);
    setVersions([]);
    setAttachments([]);
    setAttaching({ name: null, error: "" });
    setContext((context) => ({ ...context, tokens: 0 }));
  }, [setContext]);

  return {
    messages, versions, conversation, busy, attachments, attaching,
    send, edit, regenerate, stop, retry, load, reset, runCommand, attach,
  };
}
