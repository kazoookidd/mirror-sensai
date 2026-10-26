export const COMMANDS = [
  { name: "/help", description: "Show the commands", local: true },
  { name: "/new", description: "Start a new chat", local: true },
  { name: "/conversations", description: "Open your chat history", local: true },
  { name: "/personas", description: "List the personas" },
  { name: "/persona", args: "[id|number]", description: "Show the persona, or switch to another one (history is kept)" },
  { name: "/models", description: "List the models installed in Ollama" },
  { name: "/model", args: "[name|number]", description: "Show the model, or switch to another one" },
  { name: "/temperature", args: "[value|default]", description: "Show or set how creative the answers are (0 to 2)" },
  { name: "/settings", args: "[name [value]]", description: "List the settings, or show or change one" },
  { name: "/search", description: "List the web search engines" },
  { name: "/switch_search", args: "[name|number]", description: "Switch the web search engine" },
  { name: "/leave", args: "<request>", description: "File a leave request in plain language" },
  { name: "/leaves", description: "List the leave requests you filed" },
  { name: "/ingest", description: "Index the HR documents of data/docs" },
  { name: "/cache", args: "[clear]", description: "Show the semantic cache, or empty it" },
];

export function matchCommands(text) {
  if (!text.startsWith("/") || /\s/.test(text))
    return [];
  const typed = text.toLowerCase();
  return COMMANDS.filter((command) => command.name.startsWith(typed));
}

export function helpText() {
  const width = Math.max(...COMMANDS.map((command) => `${command.name} ${command.args ?? ""}`.length));
  return COMMANDS.map((command) => `${`${command.name} ${command.args ?? ""}`.padEnd(width)}  ${command.description}`).join("\n");
}
