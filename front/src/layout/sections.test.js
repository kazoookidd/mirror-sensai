import { describe, expect, it } from "vitest";
import { isHr, sectionsFor } from "./sections.js";

const ids = (user) => sectionsFor(user).map((section) => section.id);

describe("sectionsFor [M1]", () => {
  it("gives an employee their own files instead of the shared base", () => {
    expect(ids({ account_role: "employee" })).toEqual(["chat", "files", "history"]);
    expect(ids(null)).toEqual(["chat", "files", "history"]);
  });

  it("puts the knowledge base and the leave requests in the HR group", () => {
    expect(ids({ account_role: "hr" })).toEqual(["chat", "history", "documents", "leaves"]);
    expect(sectionsFor({ account_role: "hr" }).filter((section) => section.group === "HR").map((section) => section.id))
      .toEqual(["documents", "leaves"]);
    expect(isHr({ account_role: "hr" })).toBe(true);
    expect(isHr({ account_role: "employee" })).toBe(false);
  });
});
