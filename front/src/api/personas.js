import { getJson, putJson } from "./http.js";

export const personas = {
  list: () => getJson("/personas"),
  select: (id) => putJson("/persona", { id }),
};
