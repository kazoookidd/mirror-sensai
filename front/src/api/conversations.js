import { deleteJson, download, getJson, patchJson } from "./http.js";

export const conversations = {
  list: () => getJson("/conversations"),
  messages: (id) => getJson(`/conversations/${id}/messages`),
  rename: (id, title) => patchJson(`/conversations/${id}`, { title }),
  remove: (id) => deleteJson(`/conversations/${id}`),
  exportFile: (id, format) => download(`/conversations/${id}/export?format=${format}`),
};
