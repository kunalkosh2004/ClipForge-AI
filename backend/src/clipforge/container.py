from dataclasses import dataclass

from clipforge.ai.gemini_provider import GeminiProvider
from clipforge.ai.mock_provider import MockAIProvider
from clipforge.cache.redis_cache import InMemoryCache, RedisCache
from clipforge.common.logging import get_logger
from clipforge.common.ports import AIProvider, CacheProvider, QueueBroker, StorageProvider
from clipforge.common.ports.event_bus import EventBus
from clipforge.config import Settings, get_settings
from clipforge.events.infrastructure.redis_streams import RedisStreamsEventBus
from clipforge.identity.domain.ports import PasswordHasher, TokenService
from clipforge.identity.infrastructure.hashing import Argon2PasswordHasher
from clipforge.identity.infrastructure.tokens import JWTTokenService
from clipforge.queue.dramatiq_broker import DramatiqBroker
from clipforge.storage.local_storage import LocalStorageProvider


@dataclass
class Container:
    settings: Settings
    storage: StorageProvider
    queue: QueueBroker
    cache: CacheProvider
    ai: AIProvider
    events: EventBus
    identity_hasher: PasswordHasher
    identity_tokens: TokenService


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()

    storage = LocalStorageProvider(
        root=settings.storage_root,
        signing_secret=settings.storage_signing_secret.get_secret_value(),
        base_url=settings.public_base_url,
    )
    queue = DramatiqBroker(redis_url=settings.redis_url)
    cache = InMemoryCache() if settings.app_env == "test" else RedisCache(settings.redis_url)
    events = RedisStreamsEventBus(redis_url=settings.redis_url)
    ai = _build_ai_provider(settings)
    identity_hasher = Argon2PasswordHasher()
    identity_tokens = JWTTokenService(
        secret=settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.access_token_expire_minutes,
        refresh_expire_days=settings.refresh_token_expire_days,
    )

    return Container(
        settings=settings,
        storage=storage,
        queue=queue,
        cache=cache,
        ai=ai,
        events=events,
        identity_hasher=identity_hasher,
        identity_tokens=identity_tokens,
    )


def _build_ai_provider(settings: Settings) -> AIProvider:
    if settings.ai_provider == "mock":
        return MockAIProvider()
    keys = [k.get_secret_value() for k in settings.gemini_keys()]
    if keys:
        from clipforge.db.session import SessionLocal
        from clipforge.usage.infrastructure.repositories import (
            SessionAIModelUsageRecorder,
        )

        recorder = SessionAIModelUsageRecorder(SessionLocal)
        return GeminiProvider(
            api_key=keys[0],
            api_keys=keys[1:],
            model=settings.gemini_model,
            models=settings.gemini_models,
            on_usage=recorder.record,
        )
    get_logger("container").warning(
        "gemini_api_key missing; falling back to MockAIProvider",
        ai_provider=settings.ai_provider,
    )
    return MockAIProvider()
