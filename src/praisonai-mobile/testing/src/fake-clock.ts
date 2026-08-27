/**
 * A monotonic clock the test advances by hand.
 *
 * src-tauri/src/coalesce.rs takes `now_ms` as a parameter for the same reason
 * this exists: "so every property below is tested deterministically with no
 * sleeping and no flakiness". A coalescer bounded by elapsed time cannot be
 * tested against a real clock without either sleeping or accepting flakes.
 */
export interface FakeClock {
  nowMs(): number;
  advance(ms: number): void;
}

export function createFakeClock(startMs = 0): FakeClock {
  let now = startMs;
  return {
    nowMs: () => now,
    advance(ms) {
      // Monotonic by construction. A test that could rewind the clock would be
      // testing a condition the platform never produces.
      if (ms < 0) throw new Error("fake clock cannot go backwards");
      now += ms;
    },
  };
}
