import { getJson } from "../../lib/http.js";

export const documents = {
  list: () => getJson("/documents"),
};
