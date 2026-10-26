import { deleteJson, getJson, patchJson } from "../../lib/http.js";

export const conversations = {
  list: () => getJson("/conversations"),
  messages: (id) => getJson(`/conversations/${id}/messages`),
  rename: (id, title) => patchJson(`/conversations/${id}`, { title }),
  remove: (id) => deleteJson(`/conversations/${id}`),
};
