import test from "node:test";
import assert from "node:assert/strict";

import { streamRequest } from "./api.js";

function mockStream(chunks) {
  globalThis.fetch = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
          controller.close();
        },
      }),
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    );
}

test("parses split SSE frames and a final frame without a blank-line terminator", async () => {
  mockStream([
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

test("reports malformed SSE JSON clearly", async () => {
  mockStream(['event: complete\ndata: {"answer":\n\n']);
  await assert.rejects(
    streamRequest("/assistant/research/stream", {}),
    /invalid JSON event/,
  );
});

test("surfaces server-sent error events", async () => {
  mockStream(['event: error\ndata: {"detail":"Research failed"}\n\n']);
  await assert.rejects(
    streamRequest("/assistant/research/stream", {}),
    /Research failed/,
  );
});
