import { deleteJson, getJson, patchJson, sendFile } from "./http.js";

export const documents = {
  list: () => getJson("/documents"),
  upload: (file) => sendFile(`/documents?name=${encodeURIComponent(file.name)}`, file),
  rename: (source, name) => patchJson(`/documents/${encodeURIComponent(source)}`, { name }),
  remove: (source) => deleteJson(`/documents/${encodeURIComponent(source)}`),
};
