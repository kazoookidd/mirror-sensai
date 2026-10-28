import { useLocation, useNavigate } from "react-router-dom";
import { useApp } from "../../context/AppContext.jsx";
import { conversations as conversationsApi } from "../../api/conversations.js";

export function useConversationActions({ onRenamed, onDeleted } = {}) {
  const { refreshConversations } = useApp();
  const navigate = useNavigate();
  const location = useLocation();

  const rename = async (conversation, title) => {
    await conversationsApi.rename(conversation.id, title);
    refreshConversations();
    onRenamed?.(conversation, title);
  };

  const remove = async (conversation) => {
    if (!window.confirm(`Delete "${conversation.title}"? This cannot be undone.`)) return;
    const { deleted } = await conversationsApi.remove(conversation.id);
    refreshConversations();
    onDeleted?.(conversation);
    const open = Number(location.pathname.match(/^\/chat\/(\d+)/)?.[1]);
    if (deleted.includes(open)) navigate("/chat", { replace: true });
  };

  return { rename, remove };
}
