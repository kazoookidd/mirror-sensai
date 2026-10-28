import { getJson, postJson } from "./http.js";

export const auth = {
  login: (email, password, remember) => postJson("/login", { email, password, remember }, { redirect: false }),
  logout: () => postJson("/logout", {}),
  me: () => getJson("/me", { redirect: false }),
};
