#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_gravity_urlcache import HELPER, patch_source


FIXTURE = '''from util import *

class URLCache:
    def get_size(self):
        con.request("HEAD", self.url.path, headers={"Connection":" keep-alive"})

    def get_partial(self, off, size, bypass_cache=False):
        path = self.url.path
        if bypass_cache:
            path += f"?{random.random()}"
        con.request("GET", path)
'''


class GravityURLCachePatchTest(unittest.TestCase):
    def test_preserves_redirect_query_for_head_and_range_requests(self):
        patched = patch_source(FIXTURE)
        namespace = {"urlparse": urlparse}
        helper = patched[patched.index("def _request_path"):patched.index("\n\nclass URLCache")]
        exec(compile(helper, "<patched-urlcache-helper>", "exec"), namespace)

        request_path = namespace["_request_path"]
        signed_url = urlparse("https://release-assets.example/file.zip?token=secret&expires=42")
        self.assertEqual(request_path(signed_url), "/file.zip?token=secret&expires=42")
        self.assertEqual(
            request_path(signed_url, "0.5"),
            "/file.zip?token=secret&expires=42&0.5",
        )
        self.assertEqual(request_path(urlparse("https://example/file.zip"), "0.5"), "/file.zip?0.5")

    def test_patch_is_idempotent_and_rejects_unknown_upstream_layout(self):
        patched = patch_source(FIXTURE)
        self.assertEqual(patch_source(patched), patched)
        with self.assertRaisesRegex(ValueError, "unexpected Gravity"):
            patch_source(FIXTURE.replace("self.url.path", "self.url.path ", 1))


if __name__ == "__main__":
    unittest.main()
