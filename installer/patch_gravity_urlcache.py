#!/usr/bin/env python3
"""Preserve signed redirect query strings in Gravity's range downloader."""

import argparse
from pathlib import Path


HELPER = '''def _request_path(url, cache_buster=None):
    """Build an HTTP request target without discarding signed URL queries."""
    query = url.query
    if cache_buster is not None:
        query += ("&" if query else "") + cache_buster
    return url.path + (("?" + query) if query else "")
'''
OLD_IMPORTS = "from util import *\n"
NEW_IMPORTS = OLD_IMPORTS + "\n\n" + HELPER + "\n"
OLD_HEAD = 'con.request("HEAD", self.url.path, headers={"Connection":" keep-alive"})'
NEW_HEAD = 'con.request("HEAD", _request_path(self.url), headers={"Connection":" keep-alive"})'
OLD_GET = '''path = self.url.path
        if bypass_cache:
            path += f"?{random.random()}"'''
NEW_GET = '''path = _request_path(self.url, str(random.random()) if bypass_cache else None)'''


def patch_source(source: str) -> str:
    if HELPER in source:
        if NEW_HEAD in source and NEW_GET in source:
            return source
        raise ValueError("Gravity urlcache.py contains a partial query-preservation patch")

    if source.count(OLD_IMPORTS) != 1:
        raise ValueError("unexpected Gravity urlcache.py import layout")
    if source.count(OLD_HEAD) != 1:
        raise ValueError("unexpected Gravity URLCache HEAD request")
    if source.count(OLD_GET) != 1:
        raise ValueError("unexpected Gravity URLCache range request")

    return (
        source.replace(OLD_IMPORTS, NEW_IMPORTS, 1)
        .replace(OLD_HEAD, NEW_HEAD, 1)
        .replace(OLD_GET, NEW_GET, 1)
    )


def patch_runtime(runtime: Path) -> None:
    source_file = runtime / "urlcache.py"
    source_file.write_text(patch_source(source_file.read_text()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gravity_runtime", type=Path)
    args = parser.parse_args()
    patch_runtime(args.gravity_runtime)
    print(f"patched signed-URL handling in {args.gravity_runtime / 'urlcache.py'}")


if __name__ == "__main__":
    main()
