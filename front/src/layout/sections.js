const CHAT = { id: "chat", label: "Chat", to: "/chat", icon: "message", sidebarIcon: 16 };
const HISTORY = { id: "history", label: "History", to: "/history", icon: "history", sidebarIcon: 18 };
const FILES = { id: "files", label: "My files", shortLabel: "Files", to: "/files", icon: "file-text", sidebarIcon: 16 };

export const HR_SECTIONS = [
  { id: "documents", label: "Knowledge base", shortLabel: "Documents", to: "/documents", icon: "file-text", sidebarIcon: 16, group: "HR" },
  { id: "leaves", label: "Leave requests", shortLabel: "Leaves", to: "/leaves", icon: "users", sidebarIcon: 16, group: "HR" },
];

export function isHr(user) {
  return user?.account_role === "hr";
}

export function sectionsFor(user) {
  return isHr(user) ? [CHAT, HISTORY, ...HR_SECTIONS] : [CHAT, FILES, HISTORY];
}
