"""
Delivery routing and channel directory for proactive outbound messaging.

Provides:
- DeliveryRouter: Resolves symbolic targets to concrete (platform, channel_id)
- ChannelDirectory: Manages reachable channels with friendly aliases
- Helper functions for chat type detection
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .botos import BotOS

logger = logging.getLogger(__name__)


class DeliveryNotAccepted(Exception):
    """Raised internally when an adapter reports a send failure without raising.

    Some adapters signal a failed delivery by returning an explicit ``False``
    from ``send_message`` instead of raising. :meth:`DeliveryRouter.deliver`
    normalises that into this exception so the failure flows through the same
    path as a raised error: the idempotency key is not recorded (the send stays
    retryable) and a dead target is not cleared. It is a transient failure
    marker — never classified as a permanent target failure — so existing
    retry/DLQ behaviour is unchanged.

    Note: only an explicit ``False`` is treated as failure. The dominant adapter
    convention is to return a truthy message object (or ``None``/void for
    lightweight adapters) on success and to *raise* on failure, so ``None`` is
    deliberately left as a success signal to avoid regressing those paths.
    """


def detect_chat_type(platform: str, chat_id: str) -> str:
    """Detect chat type based on platform and chat ID patterns.
    
    Args:
        platform: Platform name (telegram, discord, slack, etc.)
        chat_id: The chat/channel ID
        
    Returns:
        Chat type: 'group', 'channel', 'direct', or 'unknown'
    """
    platform_lower = platform.lower()
    
    # Telegram patterns
    if platform_lower == "telegram":
        if chat_id.startswith("-100"):
            # -100 prefix is used for both supergroups and channels
            # Without additional metadata, we can't disambiguate
            return "unknown"
        elif chat_id.startswith("-"):
            return "group"  # Regular group
        else:
            return "direct"  # Direct message
    
    # Discord patterns
    elif platform_lower == "discord":
        # Discord IDs are snowflakes; without API we can't distinguish well
        # But we can use conventions if the bot tracks this
        return "channel"  # Most discord comms are in channels
    
    # Slack patterns
    elif platform_lower == "slack":
        if chat_id.startswith("C"):
            return "channel"  # Public channel
        elif chat_id.startswith("G"):
            return "group"  # Private channel/group
        elif chat_id.startswith("D"):
            return "direct"  # Direct message
        elif chat_id.startswith("U"):
            return "direct"  # User ID (for DMs)
    
    # WhatsApp patterns
    elif platform_lower == "whatsapp":
        if "@g.us" in chat_id:
            return "group"
        elif "@c.us" in chat_id:
            return "direct"
    
    # Default fallback
    return "unknown"


@dataclass
class SessionSource:
    """Source information for a message/session."""
    platform: str
    channel_id: str
    user_id: Optional[str] = None
    thread_id: Optional[str] = None


class ChannelDirectory:
    """
    Directory of reachable channels with friendly aliases.
    
    Maintains a mapping of:
    - Platform home channels
    - Named aliases to specific channels
    - Observed channels from active sessions
    
    Durability:
    - Home channels + observed channels are persisted to ``persist_path`` so
      reachable targets survive restarts.
    - Friendly aliases are kept in a separate, hand-editable overlay file
      (``aliases_path``) re-applied on every load/refresh, so a channel can be
      pre-named before it produces any traffic.
    
    Both paths default under ``~/.praisonai/state/`` alongside the existing
    ``HomeChannelRegistry``. Persistence is best-effort: failures are logged
    and never raised, keeping the in-memory directory fully usable.
    """
    
    def __init__(
        self,
        persist_path: Optional[Path] = None,
        aliases_path: Optional[Path] = None,
    ):
        """Initialize the channel directory.
        
        Args:
            persist_path: Path to persist home + observed channels. Defaults to
                          ~/.praisonai/state/channel_directory.json
            aliases_path: Path to the durable friendly-alias overlay. Defaults to
                          ~/.praisonai/state/channel_aliases.json
        """
        state_dir = Path.home() / ".praisonai" / "state"
        self._persist_path = persist_path or (state_dir / "channel_directory.json")
        self._aliases_path = aliases_path or (state_dir / "channel_aliases.json")
        
        # Home channel per platform (default delivery target)
        self._home_channels: Dict[str, str] = {}
        
        # Friendly aliases to (platform, channel_id)
        self._aliases: Dict[str, Tuple[str, str]] = {}
        
        # Alias names sourced from the durable overlay file, tracked so stale
        # entries can be pruned when the file is edited between refreshes.
        self._overlay_aliases: set = set()
        
        # Recently observed channels per platform
        self._observed: Dict[str, set] = {}
        
        # Restore observed + home across restarts, then apply durable aliases.
        self._load()
        self._apply_alias_overlay()
    
    def _load(self) -> None:
        """Restore home + observed channels from persistent storage."""
        if not self._persist_path.exists():
            return
        try:
            with open(self._persist_path, "r") as f:
                data = json.load(f)
            home = data.get("home_channels", {})
            if isinstance(home, dict):
                self._home_channels.update(
                    {str(k).lower(): str(v) for k, v in home.items()}
                )
            observed = data.get("observed", {})
            if isinstance(observed, dict):
                for platform, channels in observed.items():
                    if isinstance(channels, (list, set, tuple)):
                        self._observed.setdefault(str(platform).lower(), set()).update(
                            str(c) for c in channels
                        )
            logger.info(
                "ChannelDirectory: loaded %d home + %d observed platforms from %s",
                len(self._home_channels),
                len(self._observed),
                self._persist_path,
            )
        except Exception as e:
            logger.warning("ChannelDirectory: failed to load directory: %s", e)
    
    def _save(self) -> None:
        """Persist home + observed channels to disk (best-effort, atomic).

        Writes to a sibling temp file then atomically replaces the target via
        ``os.replace`` so an interrupted write (disk full, crash, power loss)
        can never leave a truncated/corrupt file that ``_load`` would silently
        discard.
        """
        try:
            data = {
                "home_channels": dict(self._home_channels),
                "observed": {
                    platform: sorted(channels)
                    for platform, channels in self._observed.items()
                },
            }
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._persist_path.with_suffix(
                self._persist_path.suffix + ".tmp"
            )
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self._persist_path)
            logger.debug("ChannelDirectory: saved directory to %s", self._persist_path)
        except Exception as e:
            logger.error("ChannelDirectory: failed to save directory: %s", e)
    
    def _apply_alias_overlay(self) -> None:
        """Re-apply the durable, hand-editable friendly-alias overlay.
        
        The overlay maps ``alias -> {"platform": ..., "channel_id": ...}`` (or
        the shorthand ``alias -> "platform:channel_id"``). It is read on every
        load/refresh so aliases survive restarts and can pre-name channels
        before they produce traffic. Conflicting/invalid entries are skipped
        with a warning rather than raising.
        """
        if not self._aliases_path.exists():
            return
        try:
            with open(self._aliases_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("ChannelDirectory: failed to load alias overlay: %s", e)
            return
        
        if not isinstance(data, dict):
            return
        
        # The overlay file is the source of truth for the aliases it defines:
        # drop any previously-applied alias whose name is no longer present so
        # a deletion in the file is honoured on the next load/refresh instead
        # of lingering in memory until the process restarts.
        overlay_names = set(data.keys())
        for name in list(self._aliases.keys()):
            if name in self._overlay_aliases and name not in overlay_names:
                self._aliases.pop(name, None)
        self._overlay_aliases = set()
        
        for name, value in data.items():
            platform: Optional[str] = None
            channel_id: Optional[str] = None
            if isinstance(value, dict):
                platform = value.get("platform")
                channel_id = value.get("channel_id")
            elif isinstance(value, str) and ":" in value:
                platform, channel_id = value.split(":", 1)
            
            if not platform or not channel_id:
                logger.warning(
                    "ChannelDirectory: skipping invalid alias overlay entry '%s'", name
                )
                continue
            
            platform_key = str(platform).lower()
            self._aliases[name] = (platform_key, str(channel_id))
            self._overlay_aliases.add(name)
            # An aliased channel is reachable, so record it as observed too.
            self._observed.setdefault(platform_key, set()).add(str(channel_id))
    
    def refresh_from_adapters(self, adapters: Dict[str, Any]) -> None:
        """Refresh the directory by enumerating connected adapters.
        
        Adapters exposing a ``list_channels()`` method (e.g. Discord/Slack) are
        enumerated and merged into the observed set, so channels the user has
        but has not messaged the bot from become addressable. The durable alias
        overlay is re-applied and the directory persisted afterwards.
        
        Args:
            adapters: Mapping of platform name -> adapter object. Adapters
                      without ``list_channels`` are skipped.
        """
        for platform, adapter in (adapters or {}).items():
            list_channels = getattr(adapter, "list_channels", None)
            if not callable(list_channels):
                continue
            try:
                channels = list_channels()
            except Exception as e:
                logger.warning(
                    "ChannelDirectory: list_channels failed for '%s': %s", platform, e
                )
                continue
            for ch in channels or []:
                channel_id = getattr(ch, "id", ch)
                if channel_id is None:
                    continue
                self.observe_channel(platform, str(channel_id))
        
        self._apply_alias_overlay()
        self._save()
    
    def set_home_channel(self, platform: str, channel_id: str) -> None:
        """Set the default/home channel for a platform."""
        platform_key = platform.lower()
        self._home_channels[platform_key] = channel_id
        logger.debug(f"ChannelDirectory: set home channel for {platform_key}: {channel_id}")
        self._save()
    
    def add_alias(self, name: str, platform: str, channel_id: str) -> None:
        """Add a friendly alias for a channel."""
        platform_key = platform.lower()
        existing = self._aliases.get(name)
        if existing and existing != (platform_key, channel_id):
            raise ValueError(
                f"Alias '{name}' already points to {existing[0]}:{existing[1]}"
            )
        self._aliases[name] = (platform_key, channel_id)
        logger.debug(f"ChannelDirectory: added alias '{name}' -> {platform_key}:{channel_id}")
    
    def observe_channel(self, platform: str, channel_id: str) -> None:
        """Record an observed channel from an active session.

        New observations are persisted immediately (best-effort) so channels
        seen from live traffic survive a restart even before the next refresh
        cycle runs, consistent with ``set_home_channel``.
        """
        platform_key = platform.lower()
        if platform_key not in self._observed:
            self._observed[platform_key] = set()
        if channel_id in self._observed[platform_key]:
            return
        self._observed[platform_key].add(channel_id)
        self._save()
    
    def get_home_channel(self, platform: str) -> Optional[str]:
        """Get the home channel for a platform."""
        return self._home_channels.get(platform.lower())
    
    def resolve_alias(self, alias: str) -> Optional[Tuple[str, str]]:
        """Resolve an alias to (platform, channel_id)."""
        return self._aliases.get(alias)
    
    def has_channel(self, platform: str, channel_id: str) -> bool:
        """Check if a channel is known (home, alias, or observed)."""
        platform_key = platform.lower()
        
        # Check if it's the home channel
        if self._home_channels.get(platform_key) == channel_id:
            return True
        
        # Check if it's in aliases
        for p, c in self._aliases.values():
            if p.lower() == platform_key and c == channel_id:
                return True
        
        # Check if it's observed
        if platform_key in self._observed and channel_id in self._observed[platform_key]:
            return True
        
        return False
    
    def describe_targets(self) -> list:
        """Describe all reachable targets for session context.
        
        Returns:
            List of dicts with 'name', 'platform', 'channel_id', 'kind' keys
        """
        targets = []
        
        # Add home channels
        for platform, channel_id in self._home_channels.items():
            targets.append({
                'name': f"{platform}:home",
                'platform': platform,
                'channel_id': channel_id,
                'kind': 'home'
            })
        
        # Add aliases
        for alias_name, (platform, channel_id) in self._aliases.items():
            targets.append({
                'name': alias_name,
                'platform': platform,
                'channel_id': channel_id,
                'kind': 'alias'
            })
        
        # Add observed channels (from passive traffic + adapter refresh) that
        # are not already represented by a home channel or an alias, so the
        # agent-facing `list` action can surface reachable-but-unnamed targets.
        named = {
            (t['platform'], t['channel_id']) for t in targets
        }
        for platform, channels in self._observed.items():
            for channel_id in sorted(channels):
                if (platform, channel_id) in named:
                    continue
                targets.append({
                    'name': f"{platform}:{channel_id}",
                    'platform': platform,
                    'channel_id': channel_id,
                    'kind': 'observed'
                })
        
        return targets


class DeliveryRouter:
    """
    Routes messages to target channels using symbolic targets.
    
    Target grammar:
    - "origin" - the channel the request came from
    - "<platform>" - that platform's home/default channel
    - "<platform>:<channel_id>" - explicit channel on a platform
    - "<alias>" - friendly name from the channel directory
    """
    
    def __init__(self, botos: BotOS, dead_targets: Optional[Any] = None):
        self._botos = botos
        self.directory = ChannelDirectory()
        # Optional self-healing dead-target registry (issue #2486). Default OFF:
        # when None, delivery behaves exactly as before (no suppression).
        self._dead_targets = dead_targets
        # Per-platform token-bucket rate limiters for the proactive path
        # (issue #2578). Agent-initiated sends previously bypassed the limiter
        # entirely, so a burst of scheduled/background sends could trip platform
        # 429s with no throttle. Built lazily per platform; if the live adapter
        # already owns a ``_rate_limiter`` we reuse it so proactive and reply
        # traffic share one bucket instead of double-counting.
        self._rate_limiters: Dict[str, Any] = {}
        # Bounded in-memory idempotency guard so a retried proactive send (e.g. a
        # scheduled job re-fired after a crash) with a caller-stable key does not
        # double-post. Best-effort and per-process; the outbox UNIQUE key remains
        # the durable dedup on the reply path.
        self._seen_keys: "OrderedDict[str, float]" = OrderedDict()
        self._seen_keys_max: int = 4096

    def _rate_limiter_for(self, platform: str) -> Optional[Any]:
        """Return a rate limiter for ``platform``, reusing the adapter's own.

        Prefers the live adapter's ``_rate_limiter`` (so proactive and reply
        sends share one bucket) and otherwise lazily builds a platform-default
        limiter. Returns None only if the rate-limit helper cannot be imported,
        in which case delivery proceeds unthrottled exactly as before.
        """
        bot = self._botos.get_bot(platform)
        adapter = getattr(bot, "adapter", None) or bot
        existing = getattr(adapter, "_rate_limiter", None)
        if existing is not None:
            return existing
        limiter = self._rate_limiters.get(platform)
        if limiter is not None:
            return limiter
        try:
            from ._rate_limit import RateLimiter

            limiter = RateLimiter.for_platform(platform)
        except Exception:  # pragma: no cover - defensive
            logger.debug(
                "DeliveryRouter: rate limiter unavailable for %s", platform,
                exc_info=True,
            )
            return None
        self._rate_limiters[platform] = limiter
        return limiter

    def _is_duplicate(self, idempotency_key: Optional[str]) -> bool:
        """Report whether ``idempotency_key`` was already delivered this process.

        Best-effort, bounded LRU dedup for the proactive path. Returns True when
        the key maps to a prior *successful* send (suppress the re-send), False
        for a fresh or absent key. The key is only recorded once delivery
        succeeds (see :meth:`_remember_key`) so a failed send stays retryable.
        """
        if not idempotency_key:
            return False
        if idempotency_key in self._seen_keys:
            self._seen_keys.move_to_end(idempotency_key)
            return True
        return False

    def _remember_key(self, idempotency_key: Optional[str]) -> None:
        """Record a successfully delivered ``idempotency_key`` for future dedup."""
        if not idempotency_key:
            return
        self._seen_keys[idempotency_key] = time.monotonic()
        self._seen_keys.move_to_end(idempotency_key)
        while len(self._seen_keys) > self._seen_keys_max:
            self._seen_keys.popitem(last=False)
    
    def refresh_directory(self) -> None:
        """Refresh the channel directory from the registered bots.
        
        Enumerates each registered bot/adapter that can list its channels and
        merges them into the durable directory. Intended to be called
        periodically by the gateway's background loop so reachable targets stay
        fresh without requiring inbound traffic.
        """
        adapters: Dict[str, Any] = {}
        for platform in self._botos.list_bots():
            bot = self._botos.get_bot(platform)
            if bot is not None:
                adapters[platform] = bot
        self.directory.refresh_from_adapters(adapters)
    
    def resolve(self, target: str, origin: Optional[SessionSource] = None) -> Tuple[str, str]:
        """
        Resolve a target string to (platform, channel_id).
        
        Args:
            target: Target specification (origin|platform|platform:channel|alias)
            origin: Optional source of the original request
            
        Returns:
            Tuple of (platform, channel_id)
            
        Raises:
            ValueError: If target cannot be resolved
        """
        # Handle "origin" target
        if target == "origin":
            if not origin:
                raise ValueError("Cannot resolve 'origin' without source context")
            return (origin.platform, origin.channel_id)
        
        # Handle "platform:channel_id" format
        if ":" in target:
            platform, channel_id = [p.strip() for p in target.split(":", 1)]
            if not platform or not channel_id:
                raise ValueError(
                    "Invalid target format. Expected '<platform>:<channel_id>'"
                )
            
            # Validate platform exists (normalize to lowercase)
            platform_key = platform.lower()
            if not self._botos.get_bot(platform_key):
                raise ValueError(f"Platform '{platform}' not configured")
            
            return (platform_key, channel_id)
        
        # Check if it's a platform name (use home channel) - check this BEFORE aliases
        platform_key = target.lower()
        if self._botos.get_bot(platform_key):
            home_channel = self.directory.get_home_channel(platform_key)
            if home_channel:
                return (platform_key, home_channel)
            raise ValueError(f"Platform '{target}' has no home channel configured")
        
        # Check if it's an alias
        alias_result = self.directory.resolve_alias(target)
        if alias_result:
            return alias_result
        
        # If nothing matches, it might be an undefined alias
        raise ValueError(f"Cannot resolve target '{target}': not a platform, alias, or platform:channel format")
    
    async def deliver(
        self,
        target: str,
        text: str,
        origin: Optional[SessionSource] = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> bool:
        """
        Deliver a message to a target.
        
        Args:
            target: Target specification (origin|platform|platform:channel|alias)
            text: Message content to deliver
            origin: Optional source of the original request
            idempotency_key: Optional caller-stable key (issue #2578). When
                supplied, a repeat proactive send with the same key is suppressed
                in-process so a retried scheduled/background job does not
                double-post. The adapter's own outbox remains the durable dedup.
            
        Returns:
            True if delivered successfully, False otherwise
        """
        try:
            platform, channel_id = self.resolve(target, origin)
            bot = self._botos.get_bot(platform)
            
            if not bot:
                logger.warning(f"DeliveryRouter: platform '{platform}' not available")
                return False

            # Idempotency short-circuit (issue #2578): suppress a duplicate
            # proactive send whose caller-stable key we have already delivered,
            # so a re-fired scheduled job cannot double-post.
            if self._is_duplicate(idempotency_key):
                logger.info(
                    "DeliveryRouter: suppressing duplicate proactive send "
                    "(idempotency_key=%s) to %s:%s",
                    idempotency_key,
                    platform,
                    channel_id,
                )
                return True
            
            # Short-circuit known-dead targets (issue #2486): the bot was
            # kicked/blocked or the chat no longer exists, so skip the doomed
            # API call instead of burning rate-limit budget and flooding logs.
            # Self-healing: once the re-probe interval elapses we let a single
            # send through so a recovered target (bot re-added, group restored)
            # can clear itself far sooner than the long TTL would allow.
            if self._dead_targets is not None and self._dead_targets.is_dead(
                platform, channel_id
            ):
                if self._dead_targets.should_reprobe(platform, channel_id):
                    logger.info(
                        "DeliveryRouter: re-probing dead target %s:%s "
                        "(target_reprobe_attempt)",
                        platform,
                        channel_id,
                    )
                else:
                    logger.info(
                        "DeliveryRouter: suppressing send to dead target %s:%s "
                        "(target_unreachable_suppressed)",
                        platform,
                        channel_id,
                    )
                    return False
            
            # Rate-limit the proactive path (issue #2578): a burst of
            # agent-initiated/scheduled sends must pass through the same
            # token-bucket the reply/streaming path uses so it cannot trip
            # platform 429s. Best-effort — if no limiter is available delivery
            # proceeds unthrottled exactly as before.
            limiter = self._rate_limiter_for(platform)
            if limiter is not None:
                try:
                    await limiter.acquire(channel_id)
                except Exception:
                    logger.debug(
                        "DeliveryRouter: rate-limit acquire failed for %s:%s",
                        platform,
                        channel_id,
                        exc_info=True,
                    )

            try:
                result = await bot.send_message(channel_id, text)
                # An adapter that explicitly returns ``False`` is signalling a
                # failed send without raising. Treat that as a failure so we do
                # not cache the idempotency key or clear a dead target for a
                # message that never left the process. The check is deliberately
                # ``is False`` only: the dominant convention across adapters is
                # to return a truthy message object on success, ``None``/void on
                # success for lightweight adapters, and to *raise* on failure —
                # so ``None`` must NOT be treated as a failure or those succeed
                # paths would regress.
                if result is False:
                    raise DeliveryNotAccepted(
                        f"{platform} adapter reported no delivery "
                        f"(send_message returned {result!r})"
                    )
            except Exception as send_err:
                # A server-mandated Retry-After widens the limiter's lane so the
                # next proactive sends hold off instead of re-tripping the 429.
                if limiter is not None:
                    try:
                        from ._resilience import server_retry_after

                        mandated = server_retry_after(send_err)
                        if mandated is not None and mandated > 0:
                            await limiter.penalise(channel_id, mandated)
                    except Exception:
                        logger.debug(
                            "DeliveryRouter: rate-limit penalise failed",
                            exc_info=True,
                        )
                # On a *confirmed permanent* failure, mark the whole target dead
                # so future cycles short-circuit. Transient errors and
                # message-scoped 404s stay on the existing retry path.
                if self._dead_targets is not None:
                    try:
                        from ._resilience import is_permanent_target_failure

                        if is_permanent_target_failure(send_err, platform):
                            self._dead_targets.mark_dead(
                                platform, channel_id, reason=str(send_err)
                            )
                    except Exception:
                        logger.debug(
                            "DeliveryRouter: dead-target classification failed",
                            exc_info=True,
                        )
                raise

            # Success self-heals: any earlier dead flag is cleared so a recovered
            # target (user re-added the bot, group restored) resumes delivery.
            if self._dead_targets is not None:
                try:
                    self._dead_targets.clear(platform, channel_id)
                except Exception:
                    logger.debug(
                        "DeliveryRouter: dead-target clear failed", exc_info=True
                    )

            # Record the idempotency key only after a confirmed success so a
            # failed send stays retryable while a re-fired job is deduplicated.
            self._remember_key(idempotency_key)

            logger.info(f"DeliveryRouter: delivered to {platform}:{channel_id}")
            return True
            
        except ValueError as e:
            logger.error(f"DeliveryRouter: failed to resolve target '{target}': {e}")
            return False
        except Exception as e:
            logger.error(f"DeliveryRouter: delivery failed for '{target}': {e}")
            return False
    
    async def send_media(
        self,
        target: str,
        path: str,
        *,
        caption: Optional[str] = None,
        origin: Optional[SessionSource] = None,
    ) -> bool:
        """Upload a local file ``path`` to a resolved ``target``.

        Resolves the symbolic target to a concrete (platform, channel_id) and
        dispatches the upload through the live adapter's native file primitive
        (see :func:`praisonai.bots._outbound_media.deliver_media_to_adapter`).
        The path is expected to have already passed the outbound-path guard.

        Returns:
            True if the adapter attached the file, False otherwise.
        """
        try:
            platform, channel_id = self.resolve(target, origin)
            bot = self._botos.get_bot(platform)
            if not bot:
                logger.warning(
                    "DeliveryRouter: platform '%s' not available for media", platform
                )
                return False

            from ._outbound_media import (
                deliver_media_to_adapter,
                validate_media_delivery_path,
            )

            # Final trusted boundary: re-run the baseline path guard here so a
            # direct caller of this public router method cannot bypass the
            # denylist (strict-mode policy is applied by the caller).
            safe_path = validate_media_delivery_path(path)

            # ``get_bot`` returns the user-facing ``Bot`` wrapper; the native
            # upload primitives (``_application``/``_client``) live on the
            # underlying adapter, so unwrap it before dispatch.
            media_target = getattr(bot, "adapter", None) or bot

            ok = await deliver_media_to_adapter(
                media_target, channel_id, safe_path, caption=caption
            )
            if ok:
                logger.info(
                    "DeliveryRouter: delivered media to %s:%s", platform, channel_id
                )
            return ok
        except ValueError as e:
            logger.error(
                "DeliveryRouter: failed to resolve media target '%s': %s", target, e
            )
            return False
        except Exception as e:
            logger.error(
                "DeliveryRouter: media delivery failed for '%s': %s", target, e
            )
            return False

    def configure_from_dict(self, config: Dict) -> None:
        """
        Configure the directory from a configuration dictionary.
        
        Expected format:
        {
            "platform_name": {
                "home_channel": "123456",
                "aliases": {
                    "ops-alerts": "123456",
                    "dev-chat": "789012"
                }
            }
        }
        """
        for platform, platform_config in config.items():
            # Set home channel
            if "home_channel" in platform_config:
                self.directory.set_home_channel(platform, platform_config["home_channel"])
            
            # Set aliases
            if "aliases" in platform_config:
                for alias_name, channel_id in platform_config["aliases"].items():
                    self.directory.add_alias(alias_name, platform, channel_id)
