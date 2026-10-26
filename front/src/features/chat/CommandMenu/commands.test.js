import { describe, expect, it } from "vitest";
import { COMMANDS, helpText, matchCommands } from "./commands.js";

const names = (commands) => commands.map((command) => command.name);

describe("matchCommands", () => {
  it("lists every command for a lone slash", () => {
    expect(matchCommands("/")).toHaveLength(COMMANDS.length);
  });

  it("keeps the commands that start with what was typed, ignoring case", () => {
    expect(names(matchCommands("/mo"))).toEqual(["/models", "/model"]);
    expect(names(matchCommands("/MO"))).toEqual(["/models", "/model"]);
  });

  it("closes once arguments are typed, or for plain text", () => {
    expect(matchCommands("/model qwen")).toEqual([]);
    expect(matchCommands("hello")).toEqual([]);
    expect(matchCommands("/zzz")).toEqual([]);
  });
});

describe("helpText", () => {
  it("prints one aligned line per command", () => {
    const lines = helpText().split("\n");
    expect(lines).toHaveLength(COMMANDS.length);
    const columns = lines.map((line, index) => line.indexOf(COMMANDS[index].description));
    expect(new Set(columns).size).toBe(1);
  });
});
