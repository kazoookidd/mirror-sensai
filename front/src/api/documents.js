import { getJson } from "./http.js";

export const documents = {
  list: () => getJson("/documents"),
};
