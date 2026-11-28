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

  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (!line || line.startsWith(":")) continue;

    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value || "message";
    else if (field === "data") data.push(value);
  }

  if (!data.length) return;
  let payload;
  try {
    payload = JSON.parse(data.join("\n"));
  } catch (cause) {
    throw new Error("Received an invalid JSON event from the research stream.", { cause });
  }

  if (event === "progress") {
    onProgress?.(payload);
  } else if (event === "complete") {
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
      throw new Error("Research stream returned an invalid completion payload.");
    }
    state.completed = payload;
  } else if (event === "error") {
    const detail =
      typeof payload === "string"
        ? payload
        : typeof payload.detail === "string"
          ? payload.detail
          : "Research stream failed.";
    throw new Error(detail);
  }
  // Unknown event types are ignored, as required by the SSE event model.
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
  const cancelOnAbort = () => {
    reader.cancel().catch(() => {});
  };
  signal?.addEventListener("abort", cancelOnAbort, { once: true });

  // Detect complete SSE frame separators without normalizing partial CRLF sequences.
  const separator = /(?:\r\n|\r|\n){2}/;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (signal?.aborted) {
        throw signal.reason || new DOMException("The operation was aborted.", "AbortError");
      }
      buffer += decoder.decode(value, { stream: !done });

      let match;
      while ((match = separator.exec(buffer)) !== null) {
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        if (frame) parseSSEFrame(frame, onProgress, state);
      }

      if (done) {
        streamEnded = true;
        // Preserve compatibility with servers that close after the final event
        // without sending the usual blank-line terminator.
        if (buffer.trim()) parseSSEFrame(buffer, onProgress, state);
        break;
      }
    }
  } finally {
    signal?.removeEventListener("abort", cancelOnAbort);
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
