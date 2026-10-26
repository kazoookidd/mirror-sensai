import { describe, expect, it, vi } from "vitest";
import { postStream } from "./sse.js";

function streamOf(chunks, status = 200) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status }));
}

async function collect() {
  const events = [];
  await postStream("/chat", { message: "Hi" }, (name, data) => events.push([name, data]));
  return events;
}

describe("postStream", () => {
  it("reads every event, even when one is split across chunks", async () => {
    streamOf([
      'event: token\ndata: {"text": "Hel"}\n\nevent: tok',
      'en\ndata: {"text": "lo"}\n\n',
      'event: usage\ndata: {"prompt": 10, "completion": 2}\n\n',
    ]);
    expect(await collect()).toEqual([
      ["token", { text: "Hel" }],
      ["token", { text: "lo" }],
      ["usage", { prompt: 10, completion: 2 }],
    ]);
  });

  it("joins multi-line data and names unnamed events 'message'", async () => {
    streamOf(['data: {"a":\ndata: 1}\n\n', "event: done\n\n"]);
    expect(await collect()).toEqual([["message", { a: 1 }], ["done", {}]]);
  });

  it("raises when the server refuses the request", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "An answer is already being generated." }), { status: 409 }));
    await expect(collect()).rejects.toMatchObject({ status: 409 });
  });
});
