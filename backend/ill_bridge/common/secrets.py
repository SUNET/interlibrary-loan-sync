import os
from typing import Protocol

from ill_bridge.common.exceptions import SecretResolutionError


class SecretResolver(Protocol):
    def resolve(self, secret_ref: str) -> str:
        pass


class SecretResolverPassbolt:        
    @classmethod
    def resolve(cls, secret_ref: str) -> str:
        if not secret_ref:
            raise SecretResolutionError("Empty secret reference provided.")

        # Simple env-var fallback pattern
        env_var_name = secret_ref.removeprefix("env://")

        value = os.getenv(env_var_name)
        if not value:
            raise SecretResolutionError(
                f"Could not resolve secret for reference: {secret_ref}"
            )

        return value

