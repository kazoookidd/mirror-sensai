import { deleteJson, getJson, postJson } from "./http.js";

export const shares = {
  get: (conversationId) => getJson(`/conversations/${conversationId}/share`),
  create: (conversationId) => postJson(`/conversations/${conversationId}/share`),
  remove: (conversationId) => deleteJson(`/conversations/${conversationId}/share`),
  open: (token) => getJson(`/share/${encodeURIComponent(token)}`, { redirect: false }),
};
