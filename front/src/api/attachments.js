import { sendFile } from "./http.js";

export const attachments = {
  join: (file, conversationId) => {
    const query = new URLSearchParams({ name: file.name, ...(conversationId != null && { conversation_id: conversationId }) });
    return sendFile(`/attachments?${query}`, file);
  },
};
