import { describe, expect, it, vi } from "vitest";
import { ApiError, getJson, postJson, whenUnauthorized } from "./http.js";

function reply(status, body) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(text, { status }));
}

describe("http", () => {
  it("sends JSON to /api and returns the parsed answer", async () => {
    const fetch = reply(200, { ok: true });
    expect(await postJson("/login", { email: "a" })).toEqual({ ok: true });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ email: "a" });
  });

  it("raises the server's message", async () => {
    reply(422, { detail: "The message is empty." });
    await expect(getJson("/chat")).rejects.toMatchObject({ status: 422, message: "The message is empty." });
  });

  it("falls back to the status code when the body is not JSON", async () => {
    reply(500, "boom");
    const error = await getJson("/status").catch((failure) => failure);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe("Error 500");
  });

  it("calls the unauthorized handler on 401, unless told not to", async () => {
    const handler = vi.fn();
    whenUnauthorized(handler);
    reply(401, { detail: "Session expired, please log in again." });
    await getJson("/conversations").catch(() => {});
    expect(handler).toHaveBeenCalledTimes(1);
    reply(401, { detail: "Incorrect email or password." });
    await getJson("/me", { redirect: false }).catch(() => {});
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
