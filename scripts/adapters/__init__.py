"""Public source adapters for Frontier Model Bench.

Use :func:`all_adapters` from the maintenance fetch CLI.  Importing this
package performs no network requests.
"""

from typing import Sequence

from .arena import ArenaHFDatasetAdapter, ArenaMetadataAdapter, build_arena_adapters
from .helm import build_helm_adapters
from .huggingface import build_huggingface_adapters
from .livebench import LiveBenchAdapter
from .swebench import SWEbenchOfficialAdapter


def all_adapters(
    *,
    arena_configs: Sequence[str] | None = None,
    arena_max_rows: int = 100,
) -> dict[str, object]:
    adapters: dict[str, object] = {}
    adapters.update(build_huggingface_adapters())
    adapters["swebench-official"] = SWEbenchOfficialAdapter()
    adapters["livebench-official"] = LiveBenchAdapter()
    adapters.update(build_helm_adapters())
    adapters.update(
        build_arena_adapters(
            configs=arena_configs, max_rows_per_config=arena_max_rows
        )
    )
    return adapters


__all__ = ["all_adapters", "ArenaHFDatasetAdapter", "ArenaMetadataAdapter"]
