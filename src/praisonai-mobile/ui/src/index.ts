/**
 * The UI layer's outward surface, as one import site.
 *
 * Everything here is a pure function over data: given a TurnState, a set of
 * measurements or a route stack, it returns a DESCRIPTION of what to render.
 * Nothing in this layer touches a document, a window or a Tauri API -- which is
 * what makes the React Native port a new renderer rather than a rewrite, and
 * what lets every rule in it be asserted by calling a function.
 */
export {
  UNKNOWN,
  firstLine,
  formatCount,
  formatElapsed,
  formatRelative,
  graphemes,
  truncate,
} from "./format.ts";

export {
  geometryOf,
  initialLayout,
  px,
  withComposer,
  withInsets,
  withKeyboard,
  withViewport,
} from "./layout/insets.ts";
export type { Geometry, LayoutInput } from "./layout/insets.ts";

export {
  PREVIEW_CHARS,
  approvalRowsOf,
  buildTranscript,
  decisionIdOf,
  recoveryFor,
  toneForTool,
  toolRowsOf,
} from "./transcript/view-model.ts";
export type {
  ApprovalRowView,
  DroppedRow,
  ErrorRow,
  NoticeRow,
  ReasoningRow,
  Recovery,
  Row,
  RowTone,
  TextRow,
  ToolRowView,
  TranscriptView,
  TurnActions,
  UsageView,
} from "./transcript/view-model.ts";

export {
  FOLLOW_THRESHOLD_PX,
  distanceFromBottom,
  initialFollow,
  isAtBottom,
  jumpToLatest,
  maxScrollTop,
  onContentChanged,
  onScroll,
  shouldShowJumpToLatest,
} from "./transcript/scroll.ts";
export type { FollowState, ScrollAction, ScrollMetrics } from "./transcript/scroll.ts";

export { attachBackGesture, backDecision, createRouter, sameRoute } from "./router.ts";
export type { BackDecision, Route, Router } from "./router.ts";

export { TITLE_CHARS, UNTITLED, buildChatList } from "./chats/list-view-model.ts";
export type {
  ChatListRow,
  ChatListState,
  ChatListView,
  ChatRow,
  UnreadableRow,
} from "./chats/list-view-model.ts";
