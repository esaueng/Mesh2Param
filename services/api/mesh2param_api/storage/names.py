from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection


class UnsafeNameError(ValueError):
    """Raised when an external name is unsafe to store or reflect in a header."""


_ARTIFACT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_WINDOWS_RESERVED = {
    "aux",
    "clock$",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "con",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
    "nul",
    "prn",
}
_UNSAFE_WINDOWS_CHARS = frozenset('<>:"/\\|?*')


def _reject_reserved_basename(name: str) -> None:
    stem = name.split(".", 1)[0].casefold()
    if stem in _WINDOWS_RESERVED:
        raise UnsafeNameError("filename uses a reserved device name")


def validate_artifact_name(name: str) -> str:
    """Validate a server-owned logical artifact name.

    Artifact names are deliberately a single conservative ASCII path segment. They are
    identifiers, not filesystem paths; storage code must map them separately to CAS digests.
    """

    if not isinstance(name, str):
        raise UnsafeNameError("artifact name must be a string")
    if not _ARTIFACT_NAME.fullmatch(name):
        raise UnsafeNameError(
            "artifact name must be one ASCII path segment containing letters, digits, "
            "'.', '_', or '-'"
        )
    if name in {".", ".."} or ".." in name:
        raise UnsafeNameError("artifact name cannot contain a parent-directory marker")
    if name.endswith((".", " ")):
        raise UnsafeNameError("artifact name cannot end with a dot or space")
    _reject_reserved_basename(name)
    return name


def validate_display_filename(
    name: str,
    *,
    allowed_extensions: Collection[str] | None = None,
    max_characters: int = 255,
    max_utf8_bytes: int = 255,
) -> str:
    """Validate and NFC-normalize a user-visible filename without treating it as a path."""

    if not isinstance(name, str):
        raise UnsafeNameError("filename must be a string")
    normalized = unicodedata.normalize("NFC", name)
    if not normalized or normalized in {".", ".."}:
        raise UnsafeNameError("filename cannot be empty or a directory marker")
    if normalized != normalized.strip():
        raise UnsafeNameError("filename cannot have leading or trailing whitespace")
    if len(normalized) > max_characters or len(normalized.encode("utf-8")) > max_utf8_bytes:
        raise UnsafeNameError("filename is too long")
    if normalized.startswith("."):
        raise UnsafeNameError("hidden filenames are not accepted")
    if any(character in _UNSAFE_WINDOWS_CHARS for character in normalized):
        raise UnsafeNameError("filename contains a path separator or reserved character")
    if any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in normalized):
        raise UnsafeNameError("filename contains control or directional formatting characters")
    if normalized.endswith((".", " ")):
        raise UnsafeNameError("filename cannot end with a dot or space")
    _reject_reserved_basename(normalized)

    if allowed_extensions is not None:
        normalized_extensions = {
            extension.casefold() if extension.startswith(".") else f".{extension.casefold()}"
            for extension in allowed_extensions
        }
        dot = normalized.rfind(".")
        suffix = normalized[dot:].casefold() if dot >= 0 else ""
        if suffix not in normalized_extensions:
            expected = ", ".join(sorted(normalized_extensions))
            raise UnsafeNameError(f"filename extension must be one of: {expected}")

    return normalized


__all__ = ["UnsafeNameError", "validate_artifact_name", "validate_display_filename"]
