import hashlib

import pytest

from src.knowledge.acquisition.dedup.url_normalizer import (
    calculate_hash,
    calculate_hash_from_url,
    normalize_url,
)
from src.knowledge.documents_schema.discovery_model import DiscoveryResult


def make_discovery(url):
    return DiscoveryResult(
        title="t", url=url, domain="example.com", snippet="s", mime_type="text/html"
    )


class TestNormalizeUrl:

    def test_removes_scheme_www_trailing_slash_and_fragment(self):
        assert normalize_url("https://www.Example.com/path/#frag") == "//example.com/path"

    def test_keeps_query_string(self):
        assert normalize_url("https://example.com/a/?x=1&y=2") == "//example.com/a?x=1&y=2"

    def test_adds_scheme_when_missing(self):
        assert normalize_url("example.com/a") == "//example.com/a"

    def test_http_and_https_are_equivalent(self):
        assert normalize_url("http://example.com/a") == normalize_url("https://example.com/a")

    def test_path_case_is_preserved(self):
        assert normalize_url("https://example.com/CaseSensitive") == "//example.com/CaseSensitive"

    @pytest.mark.parametrize("url", ["", None])
    def test_empty_url_raises(self, url):
        with pytest.raises(ValueError):
            normalize_url(url)


class TestHashes:

    def test_hash_from_url_is_sha256_of_normalized_url(self):
        expected = hashlib.sha256(b"//example.com/a").hexdigest()

        assert calculate_hash_from_url("https://www.example.com/a/") == expected

    def test_calculate_hash_matches_hash_from_url(self):
        url = "https://www.example.com/a/"

        assert calculate_hash(make_discovery(url)) == calculate_hash_from_url(url)

    def test_different_urls_have_different_hashes(self):
        assert calculate_hash_from_url("https://a.com") != calculate_hash_from_url("https://b.com")

    def test_equivalent_urls_have_same_hash(self):
        assert calculate_hash_from_url("http://www.a.com/x/") == calculate_hash_from_url("https://a.com/x")