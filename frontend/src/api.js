const API = "/api/v1";

async function readPayload(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || `Request failed (${response.status})`));
  }
  return payload;
}

export async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  return readPayload(response);
}

export async function streamRequest(path, body, onProgress, signal) {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) return readPayload(response);
  if (!response.body) throw new Error("Streaming is not supported by this browser.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const lines = frame.split("\n");
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
      const dataLine = lines.find((line) => line.startsWith("data:"))?.slice(5).trim();
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine);
      if (event === "progress") onProgress?.(payload);
      if (event === "complete") completed = payload;
      if (event === "error") throw new Error(payload.detail || "Research stream failed.");
    }
    if (done) break;
  }
  if (!completed) throw new Error("Research stream ended before returning a result.");
  return completed;
}
