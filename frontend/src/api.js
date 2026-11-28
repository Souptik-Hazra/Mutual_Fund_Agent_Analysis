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

function abortError(signal) {
  return signal?.reason || new DOMException("The operation was aborted.", "AbortError");
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
    if (
      payload === null ||
      typeof payload !== "object" ||
      Array.isArray(payload) ||
      typeof payload.answer !== "string"
    ) {
      throw new Error("Research stream returned an invalid completion payload.");
    }
    state.completed = payload;
  } else if (event === "error") {
    const detail =
      typeof payload === "string"
        ? payload
        : payload && typeof payload.detail === "string"
          ? payload.detail
          : "Research stream failed.";
    throw new Error(detail);
  }
  // Unknown event types are ignored, as required by the SSE event model.
}

function consumeSSEText(text, parserState, onProgress, resultState, final = false) {
  parserState.buffer += text;
  let index = 0;

  const dispatchLine = () => {
    if (parserState.line === "") {
      if (parserState.frameLines.length) {
        parseSSEFrame(parserState.frameLines.join("\n"), onProgress, resultState);
        parserState.frameLines = [];
      }
    } else {
      parserState.frameLines.push(parserState.line);
    }
    parserState.line = "";
  };

  while (index < parserState.buffer.length) {
    const char = parserState.buffer[index];
    if (char === "\r") {
      // A CR at the end of a network chunk may be the first half of CRLF.
      if (index === parserState.buffer.length - 1 && !final) break;
      if (parserState.buffer[index + 1] === "\n") index += 1;
      dispatchLine();
    } else if (char === "\n") {
      dispatchLine();
    } else {
      parserState.line += char;
    }
    index += 1;
  }

  parserState.buffer = parserState.buffer.slice(index);

  if (final) {
    if (parserState.buffer) {
      parserState.line += parserState.buffer;
      parserState.buffer = "";
    }
    if (parserState.line) dispatchLine();
    if (parserState.frameLines.length) {
      parseSSEFrame(parserState.frameLines.join("\n"), onProgress, resultState);
      parserState.frameLines = [];
    }
  }
}

export async function streamRequest(path, body, onProgress, signal) {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (signal?.aborted) throw abortError(signal);
  if (!response.ok) return readPayload(response);
  if (!response.body) throw new Error("Streaming is not supported by this browser.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const resultState = { completed: null };
  const parserState = { buffer: "", line: "", frameLines: [] };
  let streamEnded = false;
  const cancelOnAbort = () => {
    reader.cancel().catch(() => {});
  };
  signal?.addEventListener("abort", cancelOnAbort, { once: true });

  try {
    while (true) {
      if (signal?.aborted) throw abortError(signal);
      const { value, done } = await reader.read();
      if (signal?.aborted) throw abortError(signal);

      consumeSSEText(
        decoder.decode(value, { stream: !done }),
        parserState,
        onProgress,
        resultState,
        done,
      );

      if (done) {
        streamEnded = true;
        break;
      }
    }
  } finally {
    signal?.removeEventListener("abort", cancelOnAbort);
    if (!streamEnded) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }

  if (!resultState.completed) {
    throw new Error("Research stream ended before returning a result.");
  }
  return resultState.completed;
}
