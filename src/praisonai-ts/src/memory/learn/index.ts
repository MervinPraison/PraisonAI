/**
 * Learn module - continuous learning within the memory system.
 *
 * Python parity: praisonaiagents/memory/learn/__init__.py (the `__all__` list
 * at :28-44, plus the store base class, entry model and backends that the
 * Python package exposes from `stores.py`).
 */

export {
  LearnManager,
  resolveLearnConfig,
  type LearnManagerConfig,
  type ResolvedLearnConfig,
  type LearnExtractor,
  type LearnStore,
} from './manager';

export {
  BaseStore,
  LearnEntry,
  PersonaStore,
  InsightStore,
  ThreadStore,
  PatternStore,
  DecisionStore,
  FeedbackStore,
  ImprovementStore,
  SQLiteLearnBackend,
  RedisLearnBackend,
  MongoDBLearnBackend,
  getDataDir,
  getLearnDir,
  type BaseStoreOptions,
  type LearnEntryInit,
  type LearnStorageBackend,
} from './stores';

export {
  LearnMode,
  LearnError,
  LearnBackendNotAvailableError,
  toLearnEntryDict,
  type LearnEntryData,
  type LearnEntryConvertible,
  type LearnEntryLike,
  type LearnMessage,
  type LearnProtocol,
  type AsyncLearnProtocol,
  type LearnManagerProtocol,
  type ProcessConversationResult,
} from './protocols';
