from typing import ClassVar

from ill_bridge.common.exceptions import MappingProfileNotFound
from ill_bridge.providers.base import MappingProfile
from ill_bridge.providers.libris.mapping import LibrisMappingProfile

# TODO: Add other mapping profiles here as they are implemented.
# from ill_bridge.providers.fake.mapping import FakeMappingProfile
# from ill_bridge.providers.rapidill.mapping import RapidILLMappingProfile


class MappingLoader:
    _profiles: ClassVar[dict[str, type[MappingProfile]]] = {
        LibrisMappingProfile.version: LibrisMappingProfile,
    }

    @classmethod
    def available_versions(cls) -> list[str]:
        return list(cls._profiles.keys())

    @classmethod
    def load(cls, version: str) -> MappingProfile:
        try:
            profile_cls = cls._profiles[version]
        except KeyError as exc:
            raise MappingProfileNotFound(version) from exc

        return profile_cls()
