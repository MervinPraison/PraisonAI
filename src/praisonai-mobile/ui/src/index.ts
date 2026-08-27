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

export {
  CONFIGURED,
  GENERAL_SECTION,
  NOT_SET,
  SOFTWARE_SECRETS_WARNING,
  buildSettings,
  controlFor,
  labelOf,
  rowsOf,
  secretRowsOf,
  validateInput,
} from "./settings/view-model.ts";
export type {
  ControlKind,
  PresenceState,
  SecretPresence,
  SecretRow,
  SecretStatus,
  SettingsRow,
  SettingsSection,
  SettingsView,
  ValueRow,
  WarningRow,
} from "./settings/view-model.ts";

export {
  COMPOSER_LINE_PX,
  COMPOSER_MAX_PX,
  COMPOSER_MIN_PX,
  COMPOSER_PADDING_PX,
  DEFAULT_SUBMIT_POLICY,
  DRAFT_NEW_CHAT,
  canSend,
  clearDraft,
  draftOf,
  emptyComposer,
  focusDraft,
  heightFor,
  keyAction,
  lineCountOf,
  restoreComposer,
  setDraft,
  snapshotOf,
  submit,
} from "./composer/composer.ts";
export type {
  ComposerSnapshot,
  ComposerState,
  KeyAction,
  KeyPress,
  SubmitPolicy,
  SubmitResult,
} from "./composer/composer.ts";

/** The renderer's half of the transcript: what to change, computed without a
 *  DOM. Exported here because a renderer that cannot reach it rebuilds the
 *  whole list on every publish, which is the jank this package exists to avoid. */
export { emptyRender, reconcile, signatureOf } from "./render/reconcile.ts";
export type { Diff, Op, RenderState } from "./render/reconcile.ts";

/**
 * Internationalisation. A string table, locale plumbing, and the locale-aware
 * formatters that sit ALONGSIDE format.ts rather than replacing it -- format.ts
 * stays deterministic so its tests can assert literals; see format-intl.ts.
 */
export { canonicalise, direction, isRtl, logicalInsets, resolveLocale } from "./i18n/locale.ts";
export type { Direction, LogicalInsets } from "./i18n/locale.ts";

export { countedPhrase, pluralCategory, selectPlural } from "./i18n/plural.ts";
export type { PluralCategory, PluralForms } from "./i18n/plural.ts";

export { completedLength, endsSentence, sentences } from "./i18n/segment.ts";

export { en, stringKeys } from "./i18n/strings.ts";
export type { DecisionStatus, StringKey, Strings } from "./i18n/strings.ts";

export {
  MISSING_CLOSE,
  MISSING_OPEN,
  createBundle,
  describeBundle,
  enBundle,
  isComplete,
  isMarked,
  markMissing,
} from "./i18n/bundle.ts";
export type { Bundle, MissingKeyMode } from "./i18n/bundle.ts";

export {
  formatCountLocalised,
  formatDate,
  formatElapsedLocalised,
  formatNumber,
  formatRelativeFromStrings,
  formatRelativeLocalised,
  relativeParts,
} from "./i18n/format-intl.ts";
export type { RelativeParts } from "./i18n/format-intl.ts";

/**
 * Accessibility POLICY: what to announce, how urgently, and where focus goes.
 * Pure logic with no DOM in it, for the same reason as everything else in this
 * layer -- a rule expressed as a function is a rule a test can hold.
 */
export { politenessFor, priorityOf, roleFor } from "./a11y/politeness.ts";
export type { AnnounceReason, LiveRole, Politeness } from "./a11y/politeness.ts";

export {
  accessibleName,
  approvalRowName,
  chatRowName,
  droppedRowName,
  errorRowName,
  noticeRowName,
  routeTitle,
  toolRowName,
} from "./a11y/names.ts";

export { ANNOUNCE_INTERVAL_MS, announce, initialAnnouncer, resetAnnouncer } from "./a11y/announce.ts";
export type { AnnounceInput, AnnounceResult, Announcement, AnnouncerState } from "./a11y/announce.ts";

export {
  approvalButtonId,
  approvalGroupId,
  focusAfterDisable,
  focusForRoute,
  headingId,
  isLostFocus,
  screenAnnouncement,
} from "./a11y/focus.ts";
export type { DisableInput, FocusTarget, Navigation } from "./a11y/focus.ts";
