const API = "/api/v1";

async function readPayload(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const error = new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail || `Request failed (${response.status})`),
    );
    error.status = response.status;
    error.detail = detail;
    throw error;
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

function parseSSEFrame(frame, onProgress, state) {
  let event = "message";
  const data = [];

  for (const line of frame.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) {
      data.push(line.slice(5).replace(/^ /, ""));
    }
  }

  if (!data.length) return;
  let payload;
  try {
    payload = JSON.parse(data.join("\n"));
  } catch (cause) {
    throw new Error("Received an invalid JSON event from the research stream.", { cause });
  }

  if (event === "progress") onProgress?.(payload);
  else if (event === "complete") state.completed = payload;
  else if (event === "error") {
    throw new Error(payload.detail || "Research stream failed.");
  }
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
  const state = { completed: null };
  let buffer = "";
  let streamEnded = false;

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";
      for (const frame of frames) {
        if (frame.trim()) parseSSEFrame(frame, onProgress, state);
      }

      if (done) {
        streamEnded = true;
        if (buffer.trim()) parseSSEFrame(buffer, onProgress, state);
        break;
      }
    }
  } finally {
    if (!streamEnded) {
      await reader.cancel().catch(() => {});
    }
    reader.releaseLock();
  }

  if (!state.completed) {
    throw new Error("Research stream ended before returning a result.");
  }
  return state.completed;
}
