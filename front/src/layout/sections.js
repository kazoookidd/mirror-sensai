export const SECTIONS = [
  { id: "chat", label: "Chat", to: "/chat", icon: "message", sidebarIcon: 16 },
  { id: "documents", label: "Documents", to: "/documents", icon: "file-text", sidebarIcon: 16 },
  { id: "history", label: "History", to: "/history", icon: "history", sidebarIcon: 18 },
];

// [M1] Only HR accounts see the leave requests of every employee. Hiding the section is a
// convenience: the server refuses the data to anyone else (403).
export const HR_SECTIONS = [
  { id: "leaves", label: "Leave requests", shortLabel: "Leaves", to: "/leaves", icon: "users", sidebarIcon: 16 },
];

export function sectionsFor(user) {
  return user?.account_role === "hr" ? [...SECTIONS, ...HR_SECTIONS] : SECTIONS;
}
