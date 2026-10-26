import { postJson } from "../../lib/http.js";
import { postStream } from "../../lib/sse.js";

export const chat = {
  send: (message, conversationId, onEvent) =>
    postStream("/chat", { message, conversation_id: conversationId }, onEvent),
};

export const commands = {
  run: (text) => postJson("/command", { text }),
};
