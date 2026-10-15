from __future__ import annotations
import os
from typing import Any, Callable, Protocol
from enum import StrEnum

from ill_bridge.common.enums import ILLDirection  # or define it here


class LibrisFeed(StrEnum):
    # ---- Lending ----
    INCOMING = "incoming"
    RECENT = "recent"
    RESERVATIONS = "reservations"
    CANCELLATIONS = "cancellations"

    # ---- Borrowing ----
    INBOX = "inbox"
    MAY_RESERVE = "may_reserve"
    NOT_FULFILLED = "notfullfilled"
    DELIVERED = "delivered"
    LAST = "last"

    # ------------------------------------------------------------------
    # Convenience grouping
    # ------------------------------------------------------------------

    @property
    def direction(self) -> ILLDirection:
        if self in self.lending():
            return ILLDirection.LENDING
        return ILLDirection.BORROWING

    @classmethod
    def lending(cls) -> tuple[LibrisFeed, ...]:
        return (
            cls.INCOMING,
            cls.RECENT,
            cls.RESERVATIONS,
            cls.CANCELLATIONS,
        )

    @classmethod
    def borrowing(cls) -> tuple[LibrisFeed, ...]:
        return (
            cls.INBOX,
            cls.MAY_RESERVE,
            cls.NOT_FULFILLED,
            cls.DELIVERED,
            cls.LAST,
        )

    @classmethod
    def all(cls) -> list[str]:
        # [feed.value for feed in LibrisFeed]
        # return cls.lending() + cls.borrowing()
        return [feed.value for feed in cls]


print(LibrisFeed.all())
print([feed for feed in LibrisFeed.all()])
print("works?-->", [feed for feed in LibrisFeed])



class classproperty:
    def __init__(self, getter: Callable[[type], Any]):
        self.getter = getter

    def __get__(self, obj: Any, cls: type) -> Any:
        return self.getter(cls)


class LibrisAdapter:
    def __init__(self, *, sigel, base_url, api_key, mapping, writes_enabled):
        self.sigel = sigel
        self.mapping = mapping
        self.writes_enabled = writes_enabled

    @classproperty
    def feeds(self) -> tuple[str, ...]:
        return tuple(feed.value for feed in LibrisFeed)


class SecretResolver(Protocol):
    def resolve(self, secret_ref: str) -> str:
        pass


class SecretResolverPassbolt:        
    @classmethod
    def resolve(cls, secret_ref: str) -> str:
        if not secret_ref:
            raise Exception("Empty secret reference provided.")

        # Simple env-var fallback pattern
        env_var_name = secret_ref.removeprefix("env://")

        value = os.getenv(env_var_name)
        if not value:
            raise Exception(
                f"Could not resolve secret for reference: {secret_ref}"
            )

        return value
    
print("SecretResolverPassbolt.resolve('env://ILL_LIBRIS_API_KEY'):", SecretResolverPassbolt.resolve('env://ILL_LIBRIS_API_KEY'))