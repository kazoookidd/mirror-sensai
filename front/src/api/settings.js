import { getJson, putJson } from "./http.js";

export const settings = {
  get: () => getJson("/settings"),
  set: (name, value) => putJson(`/settings/${encodeURIComponent(name)}`, { value: String(value) }),
};
