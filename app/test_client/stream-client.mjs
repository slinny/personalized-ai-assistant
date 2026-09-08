// Same-origin browser example. Treat deltas as provisional until a terminal event.
// On any thrown error (including AbortError), reconcile with saved message history.
export async function streamTurn({
  baseURL = "", conversationId, token, content, signal, onEvent = () => {},
}) {
  const response = await fetch(
    `${baseURL}/conversations/${encodeURIComponent(conversationId)}/messages/stream`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ content }), signal,
    },
  );
  if (!response.ok) throw new Error(`Stream setup failed: HTTP ${response.status}`);
  if (!response.body) throw new Error("Missing response body; fetch saved history");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sequence = 0;
  let messageId;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      // This API emits LF-delimited SSE frames. Network chunks are unrelated to frames.
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame.split("\n").filter(line => line.startsWith("data:"))
          .map(line => line.slice(5).trimStart()).join("\n");
        if (!data) continue; // Keepalive comments.
        const event = JSON.parse(data);
        messageId ??= event.message_id;
        if (event.sequence !== ++sequence || event.message_id !== messageId) {
          throw new Error("Unexpected stream ordering; fetch saved history");
        }
        onEvent(event);
        if (event.event === "stream.error") {
          throw new Error("Outcome unknown; fetch saved history");
        }
        if (["message.completed", "message.cancelled", "message.failed"].includes(event.event)) {
          return event.payload.message; // Replace displayed text with this authoritative value.
        }
      }
      if (done) throw new Error("No terminal event; fetch saved history before resending");
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function cancelTurn({ baseURL = "", conversationId, messageId, token }) {
  const response = await fetch(
    `${baseURL}/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/cancel`,
    { method: "POST", headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok) throw new Error(`Cancellation failed: HTTP ${response.status}`);
  return response.json();
}
