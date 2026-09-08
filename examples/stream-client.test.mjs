import assert from "node:assert/strict";
import test from "node:test";
import { streamTurn } from "./stream-client.mjs";

function frame(event, sequence, payload) {
  return `event: ${event}\ndata: ${JSON.stringify({ event, sequence, message_id: "id", payload })}\n\n`;
}

test("parses split UTF-8 and SSE frames, ignores keepalives, returns authoritative text", async t => {
  const wire = new TextEncoder().encode(
    frame("turn.started", 1, {}) + ": keepalive\n\n" +
    frame("message.delta", 2, { text: "世界\n🦊" }) +
    frame("message.cancelled", 3, { message: { content: "世界", status: "cancelled" } }),
  );
  t.mock.method(globalThis, "fetch", async () => new Response(new ReadableStream({
    start(controller) {
      for (const byte of wire) controller.enqueue(Uint8Array.of(byte));
      controller.close();
    },
  })));
  const events = [];
  const saved = await streamTurn({ conversationId: "c", token: "test", content: "hi", onEvent: e => events.push(e) });
  assert.equal(events[1].payload.text, "世界\n🦊");
  assert.deepEqual(saved, { content: "世界", status: "cancelled" });
});

for (const [name, wire, error] of [
  ["missing terminal", frame("message.delta", 1, { text: "partial" }), /No terminal event/],
  ["unknown outcome", frame("stream.error", 1, {}), /Outcome unknown/],
  ["wrong sequence", frame("message.delta", 2, {}), /Unexpected stream ordering/],
]) {
  test(name, async t => {
    t.mock.method(globalThis, "fetch", async () => new Response(wire));
    await assert.rejects(streamTurn({ conversationId: "c", token: "test", content: "hi" }), error);
  });
}
