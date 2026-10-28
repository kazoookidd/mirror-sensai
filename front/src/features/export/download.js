import { conversations } from "../../api/conversations.js";

export const FORMATS = [
  { id: "md", label: "Markdown" },
  { id: "json", label: "JSON" },
  { id: "pdf", label: "PDF" },
];

export async function downloadChat(conversationId, format) {
  const { name, blob } = await conversations.exportFile(conversationId, format);
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return name;
}
