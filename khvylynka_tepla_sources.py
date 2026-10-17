from __future__ import annotations

from urllib.parse import urlparse


def validate_sources(entry: dict) -> bool:
    """Проверяет ссылки и независимость доменов для фактической заметки."""
    sources = entry.get("sources", [])

    if not entry.get("factual", False):
        return not sources or all(
            isinstance(source, dict) and _valid_url(source.get("url", ""))
            for source in sources
        )

    if not isinstance(sources, list) or len(sources) < 2:
        return False

    domains = set()
    for source in sources:
        if not isinstance(source, dict):
            return False
        url = source.get("url", "")
        if not _valid_url(url):
            return False
        domains.add(urlparse(url).hostname.lower().removeprefix("www."))

    return len(domains) >= 2


def _valid_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname)
