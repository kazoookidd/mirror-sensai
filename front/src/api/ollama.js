import { getJson, putJson } from "./http.js";

export const status = {
  get: () => getJson("/status", { redirect: false }),
};

export const models = {
  list: () => getJson("/models"),
  select: (name) => putJson("/model", { name }),
};
