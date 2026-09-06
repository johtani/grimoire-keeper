"""Conservative URL canonicalization for duplicate detection."""

from collections.abc import Collection
from urllib.parse import unquote_plus, urlsplit, urlunsplit


def canonicalize_url(url: str, tracking_parameters: Collection[str] = ()) -> str:
    """Return a conservative dedupe key while preserving content-sensitive parts."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()

    userinfo = ""
    if "@" in parts.netloc:
        userinfo = f"{parts.netloc.rsplit('@', 1)[0]}@"
    hostname = (parts.hostname or "").lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    excluded = frozenset(tracking_parameters)
    query_parts = []
    for item in parts.query.split("&") if parts.query else ():
        raw_name = item.partition("=")[0]
        if unquote_plus(raw_name) not in excluded:
            query_parts.append(item)

    return urlunsplit(
        (scheme, f"{userinfo}{host}", parts.path or "/", "&".join(query_parts), "")
    )


def find_url_collisions(
    rows: Collection[tuple[int, str]], tracking_parameters: Collection[str] = ()
) -> list[dict[str, object]]:
    """Group existing URLs that collapse to the same canonical key."""
    groups: dict[str, list[dict[str, object]]] = {}
    for page_id, url in rows:
        key = canonicalize_url(url, tracking_parameters)
        groups.setdefault(key, []).append({"page_id": page_id, "url": url})
    return [
        {"dedupe_key": key, "pages": pages}
        for key, pages in sorted(groups.items())
        if len(pages) > 1
    ]
