import { getJson, putJson } from "./http.js";

// [M1] The user's profile, added to the system prompt of every answer (back/Memories/Profile.py).
export const profile = {
  get: () => getJson("/profile"),
  save: (values) => putJson("/profile", values),
};
