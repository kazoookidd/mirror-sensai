const API = "/api";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized = () => {};

export function whenUnauthorized(handler) {
  onUnauthorized = handler;
}

async function detail(response) {
  try {
    const body = await response.json();
    return typeof body.detail === "string" ? body.detail : "Request refused.";
  } catch {
    return `Error ${response.status}`;
  }
}

export async function check(response, { redirect = true } = {}) {
  if (response.ok)
    return response;
  if (response.status === 401 && redirect)
    onUnauthorized();
  throw new ApiError(response.status, await detail(response));
}

export async function request(method, path, body, options) {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  await check(response, options);
  return response.json();
}

export async function download(path) {
  const response = await check(await fetch(`${API}${path}`, { credentials: "same-origin" }));
  const name = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "sensai-chat";
  return { name, blob: await response.blob() };
}

export async function sendFile(path, file) {
  const response = await fetch(`${API}${path}`, { method: "POST", body: file, credentials: "same-origin" });
  await check(response);
  return response.json();
}

export const getJson = (path, options) => request("GET", path, undefined, options);
export const postJson = (path, body, options) => request("POST", path, body, options);
export const putJson = (path, body) => request("PUT", path, body);
export const patchJson = (path, body) => request("PATCH", path, body);
export const deleteJson = (path) => request("DELETE", path);
