import { getJson, putJson } from "../../lib/http.js";

export const settings = {
  get: () => getJson("/settings"),
  set: (name, value) => putJson(`/settings/${encodeURIComponent(name)}`, { value: String(value) }),
};
