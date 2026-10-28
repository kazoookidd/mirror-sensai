import { useCallback, useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { helpText } from "./CommandMenu/commands.js";
import { Composer } from "./Composer/Composer.jsx";
import { useApp } from "../../context/AppContext.jsx";
import { ChatActions } from "../export/ChatActions.jsx";
import { downloadChat } from "../export/download.js";
import { AppShell } from "../../layout/AppShell.jsx";
import { StartView } from "./StartView.jsx";
import { ThreadView } from "./ThreadView.jsx";
import { useChat } from "./useChat.js";

export function ChatPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const composer = useRef(null);
  const { ollama } = useApp();

  const onConversation = useCallback((conversation) => {
    navigate(`/chat/${conversation.id}`, { replace: true });
  }, [navigate]);
  const { messages, versions, conversation, busy, attachments, attaching, send, edit, regenerate, stop, retry, load, reset, runCommand, attach } = useChat({ onConversation });

  const exportChat = (text) => {
    if (!conversation) return runCommand(text, "Error: This chat has no messages yet.");
    const format = text.split(/\s+/)[1]?.toLowerCase() || "md";
    return downloadChat(conversation.id, format).then(
      (name) => runCommand(text, `Downloaded ${name}`),
      (failure) => runCommand(text, `Error: ${failure.message}`),
    );
  };

  const submit = (text) => {
    if (!text.startsWith("/"))
      return send(text);
    const name = text.split(/\s/)[0].toLowerCase();
    if (name === "/new")
      return id ? navigate("/chat") : reset();
    if (name === "/conversations")
      return navigate("/history");
    if (name === "/help")
      return runCommand(text, helpText());
    if (name === "/export")
      return exportChat(text);
    return runCommand(text);
  };

  useEffect(() => {
    if (!id) reset();
    else if (Number(id) !== conversation?.id) load(Number(id)).catch(() => navigate("/not-found", { replace: true }));
  }, [id]);

  useEffect(() => {
    if (!busy)
      composer.current?.focus();
  }, [busy]);

  const started = Boolean(id) || messages.length > 0;
  const actions = (compact) => conversation && <ChatActions conversationId={conversation.id} disabled={busy} compact={compact} />;
  const nav = conversation
  ? { active: "chat", mobile: "back", title: conversation.title, back: "/history", tabs: false, actions: actions(true) }
  : { active: "chat", mobile: started ? "back" : "root", title: "", back: "/history", tabs: !started };
  const input = <Composer ref={composer} busy={busy} onSend={submit} onStop={stop}
    attachments={attachments} attaching={attaching} onAttach={attach} />;

  return (
    <AppShell nav={nav}>
      {started
      ? <ThreadView messages={messages} versions={versions} busy={busy} offline={!ollama.online} composer={input} toolbar={actions(false)} onRetry={retry}
        onEdit={edit} onRegenerate={regenerate} onVersion={(conversationId) => navigate(`/chat/${conversationId}`)}
        onCommand={runCommand} />
      : <StartView composer={input} onSuggestion={(text) => composer.current.fill(text)} />}
    </AppShell>
  );
}
