import { getJson, postJson } from "./http.js";

export const auth = {
  login: (email, password, remember) => postJson("/login", { email, password, remember }, { redirect: false }),
  // [M1] Always an employee account: HR accounts are created in the CLI.
  signup: (userId, email, password, remember) =>
    postJson("/signup", { user_id: userId, email, password, remember }, { redirect: false }),
  logout: () => postJson("/logout", {}),
  me: () => getJson("/me", { redirect: false }),
};
