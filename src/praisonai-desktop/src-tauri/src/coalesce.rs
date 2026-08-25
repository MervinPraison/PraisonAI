//! Batching stream deltas so the renderer paints at a bounded rate.
//!
//! A fast provider emits tokens far faster than a screen refreshes. Forwarding
//! each one as its own UI event is the standard desktop-AI performance mistake:
//! the render cost scales with token count instead of with elapsed time, and the
//! app degrades exactly when the model is fastest.
//!
//! This coalescer bounds *both* axes. Text accumulates until it is worth a frame
//! (`max_bytes`) or until it has waited long enough (`max_delay`), whichever
//! comes first -- so throughput never costs frames and latency never costs
//! responsiveness. Structured events are never merged with text and never
//! reordered relative to it.
//!
//! Time is injected rather than read, so every property below is tested
//! deterministically with no sleeping and no flakiness.

/// What arrives from the engine.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Delta {
    /// Text to append to the current message. The only mergeable kind.
    Text(String),
    /// Anything with its own identity: tool calls, errors, run lifecycle.
    /// Merging these would destroy meaning, so they force a flush.
    Structured(String),
    /// The engine is finished. Nothing may be left buffered after this.
    End,
}

/// What the UI is asked to render. One frame is at most one repaint.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Frame {
    Text(String),
    Structured(String),
    End,
}

pub struct Coalescer {
    pending: String,
    /// Monotonic millis when `pending` became non-empty.
    opened_at: Option<u64>,
    max_bytes: usize,
    max_delay_ms: u64,
}

impl Coalescer {
    /// `max_bytes` caps how much text one frame carries; `max_delay_ms` caps how
    /// long the first buffered byte waits. At 60fps a 16ms delay is one frame.
    pub fn new(max_bytes: usize, max_delay_ms: u64) -> Self {
        Self { pending: String::new(), opened_at: None, max_bytes, max_delay_ms }
    }

    /// Feed one delta at time `now_ms`. Returns frames to render, in order.
    pub fn push(&mut self, delta: Delta, now_ms: u64) -> Vec<Frame> {
        match delta {
            Delta::Text(text) => {
                if self.pending.is_empty() {
                    self.opened_at = Some(now_ms);
                }
                self.pending.push_str(&text);
                if self.pending.len() >= self.max_bytes {
                    return self.drain().into_iter().collect();
                }
                Vec::new()
            }
            // Structured events must not be reordered behind buffered text, so
            // the text is flushed first and they are never merged.
            Delta::Structured(payload) => {
                let mut frames: Vec<Frame> = self.drain().into_iter().collect();
                frames.push(Frame::Structured(payload));
                frames
            }
            Delta::End => {
                let mut frames: Vec<Frame> = self.drain().into_iter().collect();
                frames.push(Frame::End);
                frames
            }
        }
    }

    /// Call on a timer. Emits a frame only if buffered text has waited too long,
    /// so an idle stream costs nothing.
    pub fn tick(&mut self, now_ms: u64) -> Option<Frame> {
        let opened_at = self.opened_at?;
        (now_ms.saturating_sub(opened_at) >= self.max_delay_ms)
            .then(|| self.drain())
            .flatten()
    }

    fn drain(&mut self) -> Option<Frame> {
        self.opened_at = None;
        (!self.pending.is_empty()).then(|| Frame::Text(std::mem::take(&mut self.pending)))
    }

    /// True when text is buffered. After `End` this must be false.
    pub fn has_pending(&self) -> bool {
        !self.pending.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(s: &str) -> Delta {
        Delta::Text(s.to_string())
    }

    /// Concatenate every Text frame, so we can assert nothing was lost.
    fn rendered(frames: &[Frame]) -> String {
        frames
            .iter()
            .filter_map(|f| match f {
                Frame::Text(t) => Some(t.as_str()),
                _ => None,
            })
            .collect()
    }

    #[test]
    fn coalescing_actually_reduces_frames() {
        // The positive control. Without this, every other test here would still
        // pass on an implementation that emits one frame per token and does
        // nothing at all.
        let mut c = Coalescer::new(64, 16);
        let tokens: Vec<Delta> = (0..200).map(|_| text("tok ")).collect();
        let mut frames = Vec::new();
        for t in tokens {
            frames.extend(c.push(t, 0));
        }
        frames.extend(c.push(Delta::End, 0));

        assert!(
            frames.len() < 30,
            "200 tokens produced {} frames; coalescing is not working",
            frames.len()
        );
        assert_eq!(rendered(&frames).len(), 800, "no text may be lost");
    }

    #[test]
    fn no_token_is_ever_lost_or_reordered() {
        let mut c = Coalescer::new(8, 16);
        let mut frames = Vec::new();
        for (i, word) in ["alpha ", "beta ", "gamma ", "delta "].iter().enumerate() {
            frames.extend(c.push(text(word), i as u64));
        }
        frames.extend(c.push(Delta::End, 9));
        assert_eq!(rendered(&frames), "alpha beta gamma delta ");
    }

    #[test]
    fn a_slow_trickle_still_paints_within_the_delay_budget() {
        // One token, then silence. Without the timer it would sit in the buffer
        // forever and the user would watch a frozen screen mid-answer.
        let mut c = Coalescer::new(1024, 16);
        assert!(c.push(text("hello"), 100).is_empty(), "not worth a frame yet");
        assert_eq!(c.tick(110), None, "10ms is inside the budget");
        assert_eq!(c.tick(116), Some(Frame::Text("hello".into())), "16ms is the deadline");
        assert_eq!(c.tick(200), None, "nothing left to flush");
    }

    #[test]
    fn a_structured_event_never_overtakes_buffered_text() {
        // If a tool call rendered before the sentence preceding it, the
        // transcript would read in the wrong order.
        let mut c = Coalescer::new(1024, 16);
        assert!(c.push(text("Let me check"), 0).is_empty());
        let frames = c.push(Delta::Structured("tool_call:search".into()), 1);
        assert_eq!(
            frames,
            vec![Frame::Text("Let me check".into()), Frame::Structured("tool_call:search".into())],
            "order must be text-then-event"
        );
    }

    #[test]
    fn end_leaves_nothing_buffered() {
        // The failure this prevents: the last few tokens of an answer never
        // appearing because the stream ended before the buffer filled.
        let mut c = Coalescer::new(1024, 16);
        c.push(text("the final words"), 0);
        assert!(c.has_pending());
        let frames = c.push(Delta::End, 1);
        assert_eq!(
            frames,
            vec![Frame::Text("the final words".into()), Frame::End]
        );
        assert!(!c.has_pending(), "text was still buffered after End");
    }

    #[test]
    fn a_burst_larger_than_the_cap_flushes_immediately() {
        let mut c = Coalescer::new(8, 1000);
        let frames = c.push(text("0123456789"), 0);
        assert_eq!(frames, vec![Frame::Text("0123456789".into())]);
        assert!(!c.has_pending());
    }

    #[test]
    fn an_idle_stream_costs_nothing() {
        // tick() on an empty buffer must never manufacture a repaint.
        let mut c = Coalescer::new(64, 16);
        for t in [0, 100, 10_000, 1_000_000] {
            assert_eq!(c.tick(t), None);
        }
    }

    #[test]
    fn structured_events_are_never_merged_with_each_other() {
        let mut c = Coalescer::new(1024, 16);
        let mut frames = c.push(Delta::Structured("a".into()), 0);
        frames.extend(c.push(Delta::Structured("b".into()), 0));
        assert_eq!(frames, vec![Frame::Structured("a".into()), Frame::Structured("b".into())]);
    }
}
