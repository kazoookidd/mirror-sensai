import { deleteJson, getJson, sendFile } from "./http.js";

export const attachments = {
  mine: () => getJson("/attachments"),
  remove: (id) => deleteJson(`/attachments/${id}`),
  join: (file, conversationId) => {
    const query = new URLSearchParams({ name: file.name, ...(conversationId != null && { conversation_id: conversationId }) });
    return sendFile(`/attachments?${query}`, file);
  },
};
