"""Safe parsing for lore Markdown front matter."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ..errors import ContentParseError
from .models import LoreDocument, LoreFrontMatter

MAX_LORE_BYTES = 1024 * 1024


def read_lore_document(path: Path, relative_path: str) -> LoreDocument:
    """Read one bounded Markdown file and derive metadata when needed."""
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ContentParseError(f"{path}: unable to read lore file: {error}") from error
    if len(content) > MAX_LORE_BYTES:
        raise ContentParseError(f"{path}: file exceeds 1 MiB limit")
    if b"\0" in content:
        raise ContentParseError(f"{path}: NUL bytes are not allowed")
    try:
        text = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as error:
        raise ContentParseError(f"{path}: file must be UTF-8") from error
    metadata_data, body = _split_front_matter(text, path)
    if metadata_data is None:
        metadata_data = _derived_metadata(relative_path, body)
    try:
        metadata = LoreFrontMatter.model_validate(metadata_data)
        return LoreDocument(metadata=metadata, body=body, relative_path=relative_path)
    except ValueError as error:
        raise ContentParseError(f"{path}: front matter: {error}") from error


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, object] | None, str]:
    if not text.startswith("+++"):
        return None, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "+++":
        return None, text
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\n") == "+++":
            raw_metadata = "".join(lines[1:index])
            try:
                return tomllib.loads(raw_metadata), "".join(lines[index + 1 :])
            except tomllib.TOMLDecodeError as error:
                raise ContentParseError(f"{path}: front matter TOML: {error}") from error
    raise ContentParseError(f"{path}: front matter is missing closing +++ delimiter")


def _derived_metadata(relative_path: str, body: str) -> dict[str, object]:
    stem = relative_path.removesuffix(".md")
    derived_id = re.sub(r"[^a-z0-9_]+", "_", stem.lower().replace("/", "_"))
    derived_id = derived_id.strip("_") or "lore"
    if not derived_id[0].isalpha():
        derived_id = f"lore_{derived_id}"
    h1 = re.search(r"^#\s+(.+?)\s*$", body, flags=re.MULTILINE)
    title = h1.group(1) if h1 else Path(relative_path).stem.replace("_", " ").replace("-", " ").title()
    return {"id": derived_id[:64], "title": title, "kind": "lore", "priority": 0.5}
