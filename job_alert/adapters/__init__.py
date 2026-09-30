from __future__ import annotations

from typing import Any

from .base import SourceAdapter
from .amazon import AmazonAdapter
from .generic_html import GenericHtmlAdapter
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .sample import SampleAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    "amazon": AmazonAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "generic_html": GenericHtmlAdapter,
    "sample": SampleAdapter,
}


def create_adapter(config: dict[str, Any], http: Any) -> SourceAdapter:
    kind = str(config.get("type", ""))
    try:
        adapter_class = ADAPTERS[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown source type {kind!r}. Available: {', '.join(sorted(ADAPTERS))}") from exc
    return adapter_class(config, http)
