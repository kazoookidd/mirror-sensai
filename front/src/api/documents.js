import { getJson, sendFile } from "./http.js";

export const documents = {
  list: () => getJson("/documents"),
  upload: (file) => sendFile(`/documents?name=${encodeURIComponent(file.name)}`, file),
};
