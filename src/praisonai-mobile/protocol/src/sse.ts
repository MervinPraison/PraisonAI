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
  /** True when the previous chunk ended with `\r`, which was emitted as a
   *  terminator on the assumption it stood alone.
   *
   *  Normalising each chunk in ISOLATION was wrong: a chunk ending in `\r`
   *  became `\n`, and the next chunk's leading `\n` then completed a `\n\n`
   *  that was never a frame boundary -- one frame became two malformed ones.
   *  Measured end to end against the real engine over a CRLF stream: at the
   *  repo's own 7-byte test chunk size half the answer vanished; at 1-3 bytes
   *  the whole answer did and the turn reported "the engine produced no
   *  output", blaming the model for a transport bug. CRLF is not exotic: the
   *  spec permits it and any proxy may rewrite to it.
   *
   *  Holding the `\r` back instead would break the other legal ending -- a
   *  lone-CR stream ends on `\r` with no chunk after it, so its last frame
   *  would never complete. That was tried and it regressed CR-only streams
   *  from working to silent. So the `\r` is emitted immediately and the
   *  matching `\n`, if one follows, is swallowed here. */
  let swallowLeadingLf = false;
  /** The buffered text, UNJOINED.
   *
   *  `buffer += chunk` then `buffer.indexOf("\n\n")` re-scans -- and, because
   *  the append builds a rope that `indexOf` must flatten, re-COPIES -- the
   *  whole buffer on every chunk. A single large frame arriving over many
   *  small chunks is then O(n^2) in its length: the shape of a `tool_result`
   *  carrying a big file over a cellular link. Measured, one 1 MB frame over
   *  512-byte chunks: 2.4 / 10.7 / 40.7 / 163.1 ms at 128 / 256 / 512 /
   *  1024 kB -- 4.01x per doubling, roughly 650 ms of blocked main thread on a
   *  phone. Adding a scan offset did NOT help, because the flatten is the
   *  cost, not the search.
   *
   *  So the search runs over the arriving chunk alone and the pieces are
   *  joined only when a frame actually completes -- once per frame, over that
   *  frame's own length. */
  let parts: string[] = [];
  /** Whether the buffered text ends with `\n`. A boundary can straddle the
   *  join between two pieces, and neither piece contains `\n\n` when it
   *  does. */
  let endsWithLf = false;

  return (chunk: string): readonly SseFrame[] => {
    // Normalise line endings once, here, rather than in every field match. A
    // proxy is free to rewrite them and the spec permits either.
    let text = chunk;
    const swallowed = swallowLeadingLf && text.startsWith("\n");
    if (swallowed) text = text.slice(1);
    // A chunk that decodes to NOTHING must not touch the pending-CR state.
    //
    // Reading `"".endsWith("\r")` as false would drop the swallow flag, and a
    // `\n` arriving in a LATER chunk would then survive as a false frame
    // boundary -- splitting one CRLF frame into two malformed ones. The
    // regression is only reachable with an empty chunk (or a bare `\n` chunk
    // that the swallow consumed) landing between the `\r` and its `\n`, but a
    // proxy chunking on the radio's whim produces exactly that.
    //
    // When there ARE characters, the trailing `\r` decides the flag as before.
    // When there are none but we just swallowed the LF, the CRLF is complete,
    // so the flag clears. When there are none and nothing was swallowed (a
    // truly empty chunk), the flag is left as-is so the pending `\r` survives.
    if (text.length > 0) swallowLeadingLf = text.endsWith("\r");
    else if (swallowed) swallowLeadingLf = false;
    const normalised = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    const frames: SseFrame[] = [];
    const push = (block: string): void => {
      const frame = parseBlock(block);
      if (frame !== null) frames.push(frame);
    };

    let rest = normalised;

    // The straddling boundary: the buffered text ends with `\n` and this chunk
    // begins with one, so the `\n\n` exists only across the join and neither
    // side contains it. Handled first, because the search below cannot see it.
    if (endsWithLf && rest.startsWith("\n")) {
      // `slice(0, -1)` drops the buffered `\n` that forms the first half of
      // the boundary. Keeping it is provably equivalent -- `parseBlock` skips
      // empty lines, so a trailing newline yields one and is discarded, and a
      // differential probe over 932 (stream, chunking) pairs found no input
      // that distinguishes them. It is here for exactness about what a block
      // is, not as a guard, so do not read its survival as a missing test.
      push(parts.join("").slice(0, -1));
      parts = [];
      rest = rest.slice(1);
    }

    for (;;) {
      const boundary = rest.indexOf("\n\n");
      if (boundary === -1) break;
      push(parts.join("") + rest.slice(0, boundary));
      parts = [];
      // Past both newlines. `+ 1` is equivalent for the same reason as above:
      // the leftover `\n` becomes an empty line the next block skips. Proven,
      // not assumed, by the same differential probe.
      rest = rest.slice(boundary + 2);
    }

    if (rest !== "") parts.push(rest);
    endsWithLf = (parts[parts.length - 1] ?? "").endsWith("\n");

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
