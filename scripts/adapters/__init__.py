"""Public source adapters for Frontier Model Bench.

Use :func:`all_adapters` from the maintenance fetch CLI.  Importing this
package performs no network requests.
"""

from typing import Sequence

from .ale import (
    ALEV1Adapter,
    ALELeaderboardAdapter,
    AgentsLastExamAdapter,
    build_ale_adapters,
)
from .aider import AiderPolyglotAdapter
from .arena import ArenaHFDatasetAdapter, ArenaMetadataAdapter, build_arena_adapters
from .bfcl import BFCLAdapter, BFCLOfficialAdapter, build_bfcl_adapters
from .helm import build_helm_adapters
from .huggingface import build_huggingface_adapters
from .livebench import LiveBenchAdapter
from .mlebench import MLEBenchAdapter
from .epoch import EpochBenchmarkAdapter
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
    adapters["src-aider-polyglot"] = AiderPolyglotAdapter()
    adapters["src-mle-bench"] = MLEBenchAdapter()
    adapters["src-epoch-benchmark-hub"] = EpochBenchmarkAdapter()
    adapters.update(build_helm_adapters())
    adapters.update(build_ale_adapters())
    adapters.update(build_bfcl_adapters())
    adapters.update(
        build_arena_adapters(
            configs=arena_configs, max_rows_per_config=arena_max_rows
        )
    )
    return adapters


__all__ = [
    "all_adapters",
    "AiderPolyglotAdapter",
    "MLEBenchAdapter",
    "EpochBenchmarkAdapter",
    "AgentsLastExamAdapter",
    "ALELeaderboardAdapter",
    "ALEV1Adapter",
    "BFCLOfficialAdapter",
    "BFCLAdapter",
    "build_bfcl_adapters",
    "ArenaHFDatasetAdapter",
    "ArenaMetadataAdapter",
]
