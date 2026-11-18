"""Offline, same-face font discovery. Never substitute a different family."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import os
import re
import sys

from fontTools.ttLib import TTFont, TTCollection


def normalize(name: str) -> str:
    name = re.sub(r"^[A-Z]{6}\+", "", name)
    name = re.sub(r"#([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), name)
    return "".join(c for c in name.casefold() if c.isalnum())


@dataclass(frozen=True)
class Identity:
    aliases: frozenset[str]
    family: str
    weight: int
    italic: bool


def identity(tt: TTFont) -> Identity:
    table = tt["name"]
    names = {record.toUnicode() for record in table.names if record.nameID in (1, 4, 6, 16)}
    family = table.getDebugName(16) or table.getDebugName(1) or ""
    weight = tt["OS/2"].usWeightClass if "OS/2" in tt else (700 if tt["head"].macStyle & 1 else 400)
    italic = bool(tt["head"].macStyle & 2) or ("post" in tt and tt["post"].italicAngle != 0)
    # Many PDF producers call the regular face simply "Arimo".
    aliases = {normalize(n) for n in names if n}
    if weight == 400 and not italic:
        aliases.update(normalize(n + "Regular") for n in names if n)
    return Identity(frozenset(aliases), family, weight, italic)


@lru_cache(maxsize=128)
def buffer_identity(data: bytes) -> Identity | None:
    try:
        with TTFont(BytesIO(data), lazy=True) as font:
            return identity(font)
    except Exception:
        return None


def matches(candidate: Identity, requested: str, flags=0, reference: Identity | None = None) -> bool:
    if reference:
        names_match = bool(candidate.aliases & reference.aliases)
        return names_match and candidate.weight == reference.weight and candidate.italic == reference.italic
    target = normalize(requested)
    # A PDF subset suffix used by ReportLab is not a different font face.
    target_without_index = normalize(re.sub(r"-\d+$", "", requested))
    bold = bool(flags & 16) or "bold" in target  # PyMuPDF span flags: bold = 16.
    italic = bool(flags & 2) or "italic" in target or "oblique" in target
    return (target in candidate.aliases or target_without_index in candidate.aliases) and \
        (candidate.weight >= 600) == bold and candidate.italic == italic


@dataclass(frozen=True)
class LocalFace:
    path: Path
    index: int
    identity: Identity
    source: str

    def read(self):
        # Export the selected TTC face, rather than always loading face zero.
        with TTFont(str(self.path), fontNumber=self.index, recalcTimestamp=False) as tt:
            if "fvar" in tt:
                # Only instantiate the default instance; do not guess a style.
                from fontTools.varLib.instancer import instantiateVariableFont
                tt = instantiateVariableFont(tt, {a.axisTag: a.defaultValue for a in tt["fvar"].axes}, inplace=True)
            result = BytesIO()
            tt.save(result)
            return result.getvalue()


def bundled_font_dir():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets" / "fonts"


@lru_cache(maxsize=1)
def local_faces() -> tuple[LocalFace, ...]:
    roots = [(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", "本机同款字体")]
    if os.environ.get("LOCALAPPDATA"):
        roots.append((Path(os.environ["LOCALAPPDATA"]) / "Microsoft/Windows/Fonts", "本机同款字体"))
    roots.append((bundled_font_dir(), "内置同款字体"))
    result = []
    for root, source in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in (".ttf", ".otf", ".ttc", ".otc"):
                continue
            try:
                if path.suffix.lower() in (".ttc", ".otc"):
                    collection = TTCollection(str(path), lazy=True)
                    try:
                        for index, tt in enumerate(collection.fonts):
                            result.append(LocalFace(path, index, identity(tt), source))
                    finally:
                        collection.close()
                else:
                    with TTFont(str(path), lazy=True) as tt:
                        result.append(LocalFace(path, 0, identity(tt), source))
            except Exception:
                continue
    return tuple(result)
