const DAY_MS = 24 * 60 * 60 * 1000;
const WEEK_DAYS = 7;
const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });
const shortDate = new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short" });
const fullDate = new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", year: "numeric" });
const weekday = new Intl.DateTimeFormat("en-US", { weekday: "short" });
const decimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

export function parseUtc(value) {
  return new Date(`${value.replace(" ", "T")}Z`);
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function daysAgo(date, now = new Date()) {
  return Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
}

export function dayGroup(date) {
  const days = daysAgo(date);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < WEEK_DAYS) return "Earlier this week";
  return "Older";
}

export function historyDate(date) {
  if (daysAgo(date) <= 1) return time.format(date);
  return `${weekday.format(date)}, ${shortDate.format(date)}`;
}

export function formatDate(date) {
  return fullDate.format(date);
}

export function formatShortDate(date) {
  return shortDate.format(date);
}

export function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${decimal.format(bytes / (1024 * 1024))} MB`;
}

export function formatTokens(tokens) {
  return `${decimal.format(tokens / 1000)}k`;
}

export function formatDecimal(value) {
  return decimal.format(value);
}

export function plainText(markdown) {
  return markdown.replace(/[*`#]/g, "").replace(/\s+/g, " ").trim();
}

const FILE_TYPES = { pdf: "PDF", md: "Markdown", txt: "TXT" };

export function fileType(name) {
  const extension = name.split(".").pop().toLowerCase();
  return FILE_TYPES[extension] || extension.toUpperCase();
}
