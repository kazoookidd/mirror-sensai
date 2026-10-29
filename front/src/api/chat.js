import { postJson } from "./http.js";
import { postStream } from "./sse.js";

export const chat = {
  send: (message, conversationId, onEvent, branchFrom = null) =>
    postStream("/chat", { message, conversation_id: conversationId, branch_from: branchFrom }, onEvent),
  stop: () => postJson("/chat/stop", {}),
};

export const commands = {
  run: (text, conversationId = null) => postJson("/command", { text, conversation_id: conversationId }),
};
