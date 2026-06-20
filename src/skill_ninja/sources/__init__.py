"""Pluggable source adapters: discover + fetch skills per origin (CLAUDE.md §9)."""

from .base import BundleManifest, DiscoverResult, SourceAdapter, SourceError
from .git import GitAdapter
from .github import GitHubAdapter
from .local import LocalAdapter

__all__ = [
    "SourceAdapter",
    "DiscoverResult",
    "BundleManifest",
    "SourceError",
    "GitHubAdapter",
    "GitAdapter",
    "LocalAdapter",
]
