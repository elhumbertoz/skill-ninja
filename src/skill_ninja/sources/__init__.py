"""Pluggable source adapters: discover + fetch skills per origin (CLAUDE.md §9)."""

from .base import BundleManifest, DiscoverResult, SourceAdapter, SourceError
from .github import GitHubAdapter

__all__ = [
    "SourceAdapter",
    "DiscoverResult",
    "BundleManifest",
    "SourceError",
    "GitHubAdapter",
]
