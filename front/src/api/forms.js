import { postJson } from "./http.js";

// [X4] The values of the form the assistant is waiting for (back/Web/Routes/Forms.py).
// The server checks them again: { ok: true, settled } or { ok: false, errors: { field: message } }.
export const forms = {
  submit: (conversationId, values) => postJson("/form", { conversation_id: conversationId, values }),
};
