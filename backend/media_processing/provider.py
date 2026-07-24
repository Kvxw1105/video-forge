from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .contracts import MediaExecutionRequest


class MediaProcessingError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None, retryable: bool = False):
        super().__init__(message)
        self.details = details or {}
        self.retryable = retryable


class MediaProvider(Protocol):
    provider_id: str

    def discover(self) -> dict[str, Any]: ...

    def execute(self, request: MediaExecutionRequest, source: Path, output: Path | None = None) -> dict[str, Any]: ...

    def verify_media(self, path: Path) -> dict[str, Any]: ...
