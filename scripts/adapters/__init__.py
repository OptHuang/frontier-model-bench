"""Public source adapters for Frontier Model Bench.

Use :func:`all_adapters` from the maintenance fetch CLI.  Importing this
package performs no network requests.
"""

from .arena import ArenaMetadataAdapter
from .helm import build_helm_adapters
from .huggingface import build_huggingface_adapters
from .livebench import LiveBenchAdapter
from .swebench import SWEbenchOfficialAdapter


def all_adapters() -> dict[str, object]:
    adapters: dict[str, object] = {}
    adapters.update(build_huggingface_adapters())
    adapters["swebench-official"] = SWEbenchOfficialAdapter()
    adapters["livebench-official"] = LiveBenchAdapter()
    adapters.update(build_helm_adapters())
    adapters["lmsys-arena"] = ArenaMetadataAdapter()
    return adapters


__all__ = ["all_adapters"]
