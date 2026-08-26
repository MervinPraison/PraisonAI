/**
 * Server-sent events, read incrementally.
 *
 * Stateful by necessity: on a cellular link the bytes arrive in whatever sizes
 * the radio produced, so a frame is routinely split across chunks and the
 * reader has to hold the remainder. A stateless "split the string on \n\n"
 * loses the tail of every partial frame, which on a slow network is most of
 * them.
 *
 * This is a reader, not a validator. A frame with no `event:` line is still
 * returned, because deciding what a malformed frame means belongs to decode.ts
 * where the reason can be recorded. Two jobs, two files.
 */

export interface SseFrame {
  /** The `event:` field, or "" when the frame carried none. */
  readonly event: string;
  /** Every `data:` line joined with newlines, per the SSE specification. */
  readonly data: string;
}

/**
 * Returns a reader. Feed it chunks in arrival order; it returns whatever
 * complete frames that chunk finished, and keeps the remainder for next time.
 *
 * One reader per response. Sharing one across two streams interleaves their
 * buffers and corrupts both.
 */
export function createSseReader(): (chunk: string) => readonly SseFrame[] {
  let buffer = "";

  return (chunk: string): readonly SseFrame[] => {
    // Normalise line endings once, here, rather than in every field match. A
    // proxy is free to rewrite them and the spec permits either.
    buffer += chunk.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    const frames: SseFrame[] = [];

    for (;;) {
      const boundary = buffer.indexOf("\n\n");
      if (boundary === -1) break;

      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      const frame = parseBlock(block);
      if (frame !== null) frames.push(frame);
    }

    return frames;
  };
}

/**
 * One frame's worth of lines. Exported so a test can call it directly rather
 * than reaching it only through the reader's buffering.
 *
 * Returns null for a block that carries no fields at all -- a run of blank
 * lines, or a block of nothing but comments. Emitting a frame for those would
 * inject a junk event into the stream on every keep-alive.
 */
export function parseBlock(block: string): SseFrame | null {
  let event = "";
  const dataLines: string[] = [];
  let sawField = false;

  for (const line of block.split("\n")) {
    // A line starting with ":" is a comment. Servers use them as heartbeats.
    if (line.startsWith(":")) continue;
    if (line === "") continue;

    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    // Exactly one leading space is stripped, per the specification. Stripping
    // more would corrupt a payload that legitimately begins with whitespace.
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") {
      event = value;
      sawField = true;
    } else if (field === "data") {
      // Collected, not overwritten. The desktop's `.match(/^data: (.+)$/m)`
      // takes the first line only and silently truncates a folded payload into
      // invalid JSON.
      dataLines.push(value);
      sawField = true;
    } else if (field === "id" || field === "retry") {
      // Read and discarded for now. The desktop engine sends neither; when
      // resume-after-background lands, `id` becomes the cursor.
      sawField = true;
    }
  }

  if (!sawField) return null;

  return { event, data: dataLines.join("\n") };
}
