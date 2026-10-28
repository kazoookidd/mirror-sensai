import { check } from "./http.js";

function parse(block) {
  let name = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:"))
      name = line.slice(6).trim();
    else if (line.startsWith("data:"))
      data.push(line.slice(5).trim());
  }
  return { name, data: data.length ? JSON.parse(data.join("\n")) : {} };
}

export async function postStream(path, body, onEvent) {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });
  await check(response);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const { name, data } = parse(buffer.slice(0, end));
      buffer = buffer.slice(end + 2);
      onEvent(name, data);
    }
  }
}
