import test from "node:test";
import assert from "node:assert/strict";

import { streamRequest } from "./api.js";

const encoder = new TextEncoder();

function mockStream(t, chunks) {
  t.mock.method(globalThis, "fetch", async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
          controller.close();
        },
      }),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    ),
  );
}

test("parses split SSE frames and a final frame without a blank-line terminator", async (t) => {
  mockStream(t, [
    'event: progress\r\ndata: {"node":',
    '"plan"}\r\n\r\nevent: complete\ndata: {"answer":"done"}',
  ]);
  const progress = [];
  const result = await streamRequest("/assistant/research/stream", {}, (event) =>
    progress.push(event),
  );

  assert.deepEqual(progress, [{ node: "plan" }]);
  assert.deepEqual(result, { answer: "done" });
});

test("preserves CRLF when the pair is split across network chunks", async (t) => {
  mockStream(t, [
    "event: progress\r",
    '\ndata: {"node":"plan"}\r',
    "\n\r",
    '\nevent: complete\r\ndata: {"answer":"ok"}\r\n\r\n',
  ]);
  const progress = [];
  const result = await streamRequest("/assistant/research/stream", {}, (event) =>
    progress.push(event),
  );

  assert.deepEqual(progress, [{ node: "plan" }]);
  assert.deepEqual(result, { answer: "ok" });
});

test("supports multiple events in one chunk and ignores unknown event types", async (t) => {
  mockStream(t, [
    'event: custom\ndata: {"ignored":true}\n\nevent: progress\ndata: {"step":1}\n\nevent: complete\ndata: {"answer":"ok"}\n\n',
  ]);
  const progress = [];
  const result = await streamRequest("/assistant/research/stream", {}, (event) =>
    progress.push(event),
  );

  assert.deepEqual(progress, [{ step: 1 }]);
  assert.deepEqual(result, { answer: "ok" });
});

test("supports lone CR line endings", async (t) => {
  mockStream(t, ['event: progress\rdata: {"step":1}\r\revent: complete\rdata: {"answer":"ok"}']);
  const progress = [];
  const result = await streamRequest("/assistant/research/stream", {}, (event) =>
    progress.push(event),
  );

  assert.deepEqual(progress, [{ step: 1 }]);
  assert.deepEqual(result, { answer: "ok" });
});

test("reports malformed SSE JSON clearly", async (t) => {
  mockStream(t, ['event: complete\ndata: {"answer":\n\n']);
  await assert.rejects(
    streamRequest("/assistant/research/stream", {}),
    /invalid JSON event/,
  );
});

test("rejects null completion payload", async (t) => {
  mockStream(t, ["event: complete\ndata: null\n\n"]);
  await assert.rejects(
    streamRequest("/assistant/research/stream", {}),
    /invalid completion payload/,
  );
});

test("rejects completion payload without a string answer", async (t) => {
  mockStream(t, ['event: complete\ndata: {"results":{}}\n\n']);
  await assert.rejects(
    streamRequest("/assistant/research/stream", {}),
    /invalid completion payload/,
  );
});

test("surfaces server-sent error events", async (t) => {
  mockStream(t, ['event: error\ndata: {"detail":"Research failed"}\n\n']);
  await assert.rejects(
    streamRequest("/assistant/research/stream", {}),
    /Research failed/,
  );
});

test("handles null server-sent error payload safely", async (t) => {
  mockStream(t, ["event: error\ndata: null\n\n"]);
  await assert.rejects(streamRequest("/assistant/research/stream", {}), {
    message: "Research stream failed.",
  });
});

test("reports a stream that closes before a completion event", async (t) => {
  mockStream(t, ['event: progress\ndata: {"step":1}\n\n']);
  await assert.rejects(
    streamRequest("/assistant/research/stream", {}),
    /ended before returning a result/,
  );
});

test("rejects immediately when signal is aborted while fetch resolves", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    new Response(
      new ReadableStream({
        start() {},
        cancel() {},
      }),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    ),
  );
  const controller = new AbortController();
  controller.abort();

  await assert.rejects(
    streamRequest("/assistant/research/stream", {}, undefined, controller.signal),
    { name: "AbortError" },
  );
});

test("aborts an active response stream and rejects with AbortError", async (t) => {
  let cancelled = false;
  t.mock.method(globalThis, "fetch", async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('event: progress\ndata: {"step":1}\n\n'));
        },
        cancel() {
          cancelled = true;
        },
      }),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    ),
  );

  const controller = new AbortController();
  const pending = streamRequest("/assistant/research/stream", {}, undefined, controller.signal);
  await new Promise((resolve) => setImmediate(resolve));
  controller.abort();

  await assert.rejects(pending, { name: "AbortError" });
  assert.equal(cancelled, true);
});
