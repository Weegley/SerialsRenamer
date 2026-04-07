#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SerialsRenamer.py

Production renamer/reorganizer for TV series folders.

By default this script APPLIES filesystem changes immediately per series
after confirmation.
Use --dry-run for preview-only mode.

======================================================================
Available template fields
======================================================================

These fields can be used in ALL templates:
    SERIES_FOLDER_TEMPLATE
    SEASON_FOLDER_TEMPLATE
    EPISODE_FILE_TEMPLATE
    SUBTITLE_FILE_TEMPLATE

1) {title}
   Main chosen series title according to --lang-priority.
   Example:
       "Блудливая Калифорния"

2) {series_title}
   Same as {title}. Alias for readability in templates.
   Example:
       "Californication"

3) {original_title}
   Original / alternative title from KP details, usually nameOriginal or nameEn.
   Example:
       "Californication"

4) {kp}
   Kinopoisk ID without prefix.
   Example:
       "394375"
   Usage:
       [kp{kp}]  -> [kp394375]

5) {tt}
   IMDb ID.
   Example:
       "tt0904208"
   Usage:
       [{tt}]    -> [tt0904208]

6) {year}
   Release year.
   Example:
       "2007"

7) {season}
   Season number as integer.
   Example:
       1
   Usage:
       {season:02d} -> 01

8) {episode}
   Episode number as integer.
   Example:
       7
   Usage:
       {episode:02d} -> 07

9) {lang}
   Subtitle language tag detected from filename/folder.
   Examples:
       "rus"
       "eng"

10) {subtype}
    Subtitle subtype tag detected from filename.
    Examples:
        "forced"
        "sdh"
        "full"

11) {ext}
    File extension including dot.
    Examples:
        ".mkv"
        ".mp4"
        ".srt"

======================================================================
Template settings examples
======================================================================

Default style:
    SERIES_FOLDER_TEMPLATE  = "{title} [kp{kp}][{tt}]"
    SEASON_FOLDER_TEMPLATE  = "Season {season:02d}"
    EPISODE_FILE_TEMPLATE   = "S{season:02d}E{episode:02d}{ext}"
    SUBTITLE_FILE_TEMPLATE  = "S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}"

Compact:
    SERIES_FOLDER_TEMPLATE  = "{title}"
    SEASON_FOLDER_TEMPLATE  = "S{season:02d}"
    EPISODE_FILE_TEMPLATE   = "S{season:02d}E{episode:02d}{ext}"

Verbose:
    EPISODE_FILE_TEMPLATE   = "{title} ({original_title}) {year} Сезон {season:02d} Серия {episode:02d}{ext}"

With IDs and year:
    SERIES_FOLDER_TEMPLATE  = "{title} ({year}) [kp{kp}][{tt}]"

Notes:
- Unknown values become empty strings.
- Empty (), [], {} are removed automatically after rendering.
- Forbidden filename chars are sanitized uniformly on all OSes:
  / \\ : * ? " < > |
- In every menu:
    0 = exit whole script
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Optional, List, Dict, Tuple, Any, Set
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from collections import defaultdict


# =========================
# User settings
# =========================
DEFAULT_API_KEY = "85d30ae5-d875-4c5f-900d-8e37bb20625e"
DEFAULT_CACHE_FILE = ".series_rename_cache.json"
DEFAULT_OPS_LOG = "SerialsRenamer.operations.log"
DEFAULT_LANG_PRIORITY = "any"   # ru | en | any
DEFAULT_MODE = "smart"          # smart | manual

MAX_PREVIEW_SEASONS = 3
MAX_PREVIEW_FILES_PER_SEASON = 3
MAX_PREVIEW_FALLBACK_FILES = 12

# =========================
# Template settings
# =========================
SERIES_FOLDER_TEMPLATE = "{title} [kp{kp}][{tt}]"
SEASON_FOLDER_TEMPLATE = "Season {season:02d}"
EPISODE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{ext}"
SUBTITLE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}"


VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}
SUB_EXTS = {".srt", ".ass", ".ssa", ".sub"}
IGNORE_EXTS = {".jpg", ".jpeg", ".png", ".nfo", ".log", ".txt"}

SERIES_TYPES = {"TV_SERIES", "MINI_SERIES"}

ALLOWED_TEMPLATE_FIELDS = {
    "title",
    "series_title",
    "original_title",
    "kp",
    "tt",
    "year",
    "season",
    "episode",
    "lang",
    "subtype",
    "ext",
}

LANG_TOKENS = {
    "rus": "rus",
    "ru": "rus",
    "russian": "rus",
    "eng": "eng",
    "en": "eng",
    "english": "eng",
}

SUBTYPE_TOKENS = {
    "forced": "forced",
    "full": "full",
    "sdh": "sdh",
}

SEASON_DIR_PATTERNS = [
    re.compile(r"^season[\s._-]*(\d{1,2})$", re.I),
    re.compile(r"^(\d{1,2})[.\s_-]*season$", re.I),
    re.compile(r"^s(\d{1,2})$", re.I),
    re.compile(r".*?[\s._-](\d{1,2})[\s._-]*-\s*.*$", re.I),
]

EP_PATTERNS = [
    re.compile(r"S(\d{1,2})[.\s_-]*E(\d{1,3})", re.I),
    re.compile(r"(\d{1,2})x(\d{1,3})", re.I),
    re.compile(r"\bE(\d{1,3})\b", re.I),
    re.compile(r"^(\d{1,3})\b", re.I),
]

ID_PATTERNS = {
    "kp": re.compile(r"\[kp(\d+)\]", re.I),
    "tt": re.compile(r"\[(tt\d+)\]", re.I),
}

TRASH_TOKENS = [
    "1080p", "720p", "2160p", "480p",
    "web-dl", "webrip", "bdrip", "hdrip", "dvdrip", "hdtvrip", "satrip",
    "x264", "x265", "h264", "hevc", "xvid",
    "ac3", "aac", "dd5", "nf", "amzn",
    "lostfilm", "selezen", "megapeer", "rgzsrutracker", "exkinoray",
    "densbk", "mrmittens", "uniongang", "elektri4ka", "scarabey", "scarfilm",
    "tvshows", "eniahd", "hqh", "do", "local", "dub", "mvo", "avc",
]


class UserAbort(Exception):
    pass


@dataclass
class MediaIDs:
    kp: Optional[str] = None
    tt: Optional[str] = None


@dataclass
class FileEntry:
    path: Path
    relpath: Path
    kind: str
    season: Optional[int] = None
    episode: Optional[int] = None
    lang: Optional[str] = None
    subtype: Optional[str] = None
    ext: str = ""


@dataclass
class SeriesGroup:
    source_dir: Path
    guessed_title: str
    ids: MediaIDs = field(default_factory=MediaIDs)
    files: List[FileEntry] = field(default_factory=list)
    resolved_title: Optional[str] = None
    resolved_original_title: Optional[str] = None
    resolved_year: Optional[str] = None
    season_hint: Optional[int] = None


@dataclass
class PlannedOp:
    src: Path
    dst: Path
    kind: str
    reason: str


class KPClient:
    def __init__(self, api_key: str, timeout: int = 20):
        self.api_key = api_key
        self.timeout = timeout

    def _get_json(self, url: str) -> dict:
        req = Request(url, headers={"X-API-KEY": self.api_key})
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def search(self, keyword: str) -> list:
        qs = urlencode({"keyword": keyword, "page": 1})
        url = f"https://kinopoiskapiunofficial.tech/api/v2.1/films/search-by-keyword?{qs}"
        data = self._get_json(url)
        return data.get("films", [])

    def details(self, film_id: int) -> dict:
        url = f"https://kinopoiskapiunofficial.tech/api/v2.2/films/{film_id}"
        return self._get_json(url)

    def try_details(self, film_id: int) -> Optional[dict]:
        try:
            return self.details(film_id)
        except (HTTPError, URLError, ValueError, json.JSONDecodeError):
            return None
        except Exception:
            return None


class FlexibleFormatter(Formatter):
    def format_field(self, value: Any, format_spec: str) -> str:
        if value is None or value == "":
            return ""
        try:
            return super().format_field(value, format_spec)
        except Exception:
            try:
                return format(value, format_spec)
            except Exception:
                return str(value)


FORMATTER = FlexibleFormatter()


def safe_input(prompt: str) -> str:
    try:
        value = input(prompt)
    except KeyboardInterrupt as e:
        raise UserAbort() from e

    if value.strip() == "0":
        raise UserAbort()

    return value


def normalize_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def sanitize_name_component(name: str) -> str:
    if not name:
        return "_"
    name = name.replace("/", " - ").replace("\\", " - ")
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = re.sub(r'[:*?"<>|]', "", name)
    name = normalize_spaces(name)
    name = name.rstrip(" .")
    return name or "_"


def sanitize_filename(filename: str) -> str:
    p = Path(filename)
    suffixes = "".join(p.suffixes)
    if suffixes:
        stem = filename[:-len(suffixes)]
    else:
        stem = filename
        suffixes = ""

    safe_stem = sanitize_name_component(stem)
    safe = (safe_stem + suffixes).rstrip(" .")
    return safe or "_"


def cleanup_rendered_template(s: str) -> str:
    s = re.sub(r"\[\s*\]", "", s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\{\s*\}", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.replace(" .", ".")
    s = re.sub(r"\.\.+", ".", s)
    s = s.strip(" .")
    return s or "_"


def validate_single_template(template_name: str, template_value: str) -> None:
    try:
        parsed = list(FORMATTER.parse(template_value))
    except ValueError as e:
        raise ValueError(f"{template_name}: invalid format syntax: {e}") from e

    unknown_fields = []
    for _, field_name, _, _ in parsed:
        if field_name is None or field_name == "":
            continue
        if field_name not in ALLOWED_TEMPLATE_FIELDS:
            unknown_fields.append(field_name)

    if unknown_fields:
        unique_unknown = ", ".join(sorted(set(unknown_fields)))
        allowed = ", ".join(sorted(ALLOWED_TEMPLATE_FIELDS))
        raise ValueError(
            f"{template_name}: unknown field(s): {unique_unknown}. "
            f"Allowed fields: {allowed}. Current template: {template_value}"
        )


def validate_templates() -> None:
    validate_single_template("SERIES_FOLDER_TEMPLATE", SERIES_FOLDER_TEMPLATE)
    validate_single_template("SEASON_FOLDER_TEMPLATE", SEASON_FOLDER_TEMPLATE)
    validate_single_template("EPISODE_FILE_TEMPLATE", EPISODE_FILE_TEMPLATE)
    validate_single_template("SUBTITLE_FILE_TEMPLATE", SUBTITLE_FILE_TEMPLATE)


def render_template(template: str, values: Dict[str, Any], is_filename: bool = False) -> str:
    rendered_parts = []
    for literal_text, field_name, format_spec, conversion in FORMATTER.parse(template):
        if literal_text:
            rendered_parts.append(literal_text)
        if field_name is None:
            continue

        value = values.get(field_name, "")
        if conversion and value not in ("", None):
            if conversion == "r":
                value = repr(value)
            elif conversion == "s":
                value = str(value)
            elif conversion == "a":
                value = ascii(value)

        rendered_parts.append(FORMATTER.format_field(value, format_spec))

    rendered = "".join(rendered_parts)
    rendered = re.sub(r"\.+", ".", rendered)
    rendered = re.sub(r"\[\.", "[", rendered)
    rendered = re.sub(r"\.\]", "]", rendered)
    rendered = re.sub(r"\(\.", "(", rendered)
    rendered = re.sub(r"\.\)", ")", rendered)
    rendered = cleanup_rendered_template(rendered)

    if is_filename:
        return sanitize_filename(rendered)
    return sanitize_name_component(rendered)


def strip_ids(name: str) -> Tuple[str, MediaIDs]:
    ids = MediaIDs()
    m = ID_PATTERNS["kp"].search(name)
    if m:
        ids.kp = m.group(1)
    m = ID_PATTERNS["tt"].search(name)
    if m:
        ids.tt = m.group(1)

    clean = ID_PATTERNS["kp"].sub("", name)
    clean = ID_PATTERNS["tt"].sub("", clean)
    clean = normalize_spaces(clean)
    return clean, ids


def title_cleanup(raw: str) -> str:
    s = raw.replace(".", " ").replace("_", " ")
    s = re.sub(r"\bS\d{1,2}[.\s_-]*E\d{1,3}\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d{1,2}x\d{1,3}\b", " ", s, flags=re.I)
    s = re.sub(r"\bseason[\s._-]*\d{1,2}\b", " ", s, flags=re.I)
    s = re.sub(r"\bs\d{1,2}\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d{4}\b", " ", s)

    for tok in TRASH_TOKENS:
        s = re.sub(rf"\b{re.escape(tok)}\b", " ", s, flags=re.I)

    s = re.sub(r"[-\[\]\(\)]", " ", s)
    return normalize_spaces(s)


def detect_season_from_dir(name: str) -> Optional[int]:
    for pat in SEASON_DIR_PATTERNS:
        m = pat.match(name.strip())
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None

    m = re.match(r"^(.*?)(\d{1,2})$", name.strip(), flags=re.I)
    if m:
        prefix, num = m.groups()
        if prefix and not re.search(r"\d{4}$", name.strip()):
            try:
                return int(num)
            except ValueError:
                return None

    return None


def detect_episode_info(stem: str, known_season: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
    for i, pat in enumerate(EP_PATTERNS):
        m = pat.search(stem)
        if not m:
            continue
        if i in (0, 1):
            return int(m.group(1)), int(m.group(2))
        if i == 2 and known_season is not None:
            return known_season, int(m.group(1))
        if i == 3 and known_season is not None:
            return known_season, int(m.group(1))
    return None, None


def detect_sub_meta(stem: str, parent_name: str) -> Tuple[Optional[str], Optional[str]]:
    low = f"{parent_name} {stem}".lower()
    lang = None
    subtype = None

    for token, code in LANG_TOKENS.items():
        if re.search(rf"\b{re.escape(token)}\b", low):
            lang = code
            break

    for token, code in SUBTYPE_TOKENS.items():
        if re.search(rf"\b{re.escape(token)}\b", low):
            subtype = code
            break

    return lang, subtype


def normalize_pairing_stem(stem: str) -> str:
    stem = stem.strip()
    stem = stem.rstrip(".")
    stem = re.sub(r"\s+", " ", stem)
    return stem.casefold()


def infer_series_root(start: Path, root: Path) -> Tuple[Path, Optional[int], str, MediaIDs]:
    parts = list(start.relative_to(root).parts)
    if not parts:
        return start, None, start.name, MediaIDs()

    season_idx = None
    season_hint = None
    for i, part in enumerate(parts):
        season = detect_season_from_dir(part)
        if season is not None:
            season_idx = i
            season_hint = season

    if season_idx is not None and season_idx > 0:
        series_dir = root.joinpath(*parts[:season_idx])
        series_name = parts[season_idx - 1]
        clean, ids = strip_ids(series_name)
        return series_dir, season_hint, title_cleanup(clean), ids

    first = parts[0]
    m = re.search(r"\bS(\d{1,2})\b", first, re.I)
    if m:
        season_hint = int(m.group(1))
        clean, ids = strip_ids(first)
        return root / first, season_hint, title_cleanup(clean), ids

    series_dir = root / parts[0]
    clean, ids = strip_ids(parts[0])
    return series_dir, None, title_cleanup(clean), ids


def filter_series_candidates(candidates: list) -> list:
    return [item for item in candidates if (item.get("type") or "") in SERIES_TYPES]


def sort_candidates(candidates: list, expected_type: str = "TV_SERIES") -> list:
    def score(item: dict) -> tuple:
        typ = item.get("type") or ""
        s1 = 0 if typ == expected_type else 1
        name = (item.get("nameRu") or item.get("nameEn") or "").strip()
        s2 = 0 if name else 1
        year = item.get("year") or ""
        s3 = 0 if year else 1
        return (s1, s2, s3, name.lower())
    return sorted(candidates, key=score)


def choose_display_title(details: dict, chosen: dict, guessed: str, lang_priority: str) -> str:
    name_ru = details.get("nameRu") or chosen.get("nameRu")
    name_en = details.get("nameEn") or chosen.get("nameEn")
    name_original = details.get("nameOriginal") or chosen.get("nameOriginal")

    if lang_priority == "ru":
        return name_ru or guessed
    if lang_priority == "en":
        return name_en or name_original or guessed
    return name_ru or name_en or name_original or guessed


def choose_original_title(details: dict, chosen: dict) -> Optional[str]:
    return (
        details.get("nameOriginal")
        or details.get("nameEn")
        or chosen.get("nameOriginal")
        or chosen.get("nameEn")
        or None
    )


def candidate_matches_lang(item: dict, lang_priority: str) -> bool:
    if (item.get("type") or "") not in SERIES_TYPES:
        return False
    if lang_priority == "ru":
        return bool(item.get("nameRu"))
    if lang_priority == "en":
        return bool(item.get("nameEn") or item.get("nameOriginal"))
    return True


def parse_manual_input(value: str) -> Tuple[str, str]:
    value = value.strip()
    m = re.fullmatch(r"kp[_ -]?(\d+)", value, re.I)
    if m:
        return "kp", m.group(1)
    m = re.fullmatch(r"(\d{5,10})", value)
    if m:
        return "kp", m.group(1)
    return "query", value


def try_pick_by_kp_id(kp: KPClient, kp_id: str) -> Optional[dict]:
    data = kp.try_details(int(kp_id))
    if not data:
        return None
    if (data.get("type") or "") not in SERIES_TYPES:
        return None

    return {
        "filmId": data.get("kinopoiskId") or int(kp_id),
        "nameRu": data.get("nameRu"),
        "nameEn": data.get("nameEn"),
        "nameOriginal": data.get("nameOriginal"),
        "type": data.get("type"),
        "year": data.get("year"),
        "_details": data,
    }


def _display_path(path: Path, base: Optional[Path] = None) -> str:
    if base is not None:
        try:
            return str(path.relative_to(base)).replace("\\", "/")
        except Exception:
            pass
    return path.name


def _relative_under(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except Exception:
        return path.name


def prompt_search_query_no_results() -> str:
    print()
    print("No matches found.")
    print("0) exit")
    print("1) skip")
    print("2) retry same search")
    print("Any other input = new search text or kp id")
    return safe_input("> ").strip()


def choose_from_results(query: str, results: list) -> Tuple[str, Optional[dict]]:
    print()
    print(f"Found matches for: {query}")
    for idx, item in enumerate(results, start=1):
        kp_id = item.get("filmId")
        name = item.get("nameRu") or item.get("nameEn") or "<unnamed>"
        year = item.get("year") or "?"
        typ = item.get("type") or "?"
        print(f"{idx}) {name} ({year}) [{typ}] [kp{kp_id}]")
    print("0) exit")
    print("98) skip")
    print("99) retry same search")
    print("Any other input = new search text or kp id")
    if len(results) == 1:
        print("Enter = choose 1")
    print()

    while True:
        choice = safe_input("Choose: ").strip()

        if choice == "" and len(results) == 1:
            return "chosen", results[0]

        if choice == "98":
            return "skip", None
        if choice == "99":
            return "retry", None
        if choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(results):
                return "chosen", results[n - 1]

        kind, value = parse_manual_input(choice)
        if kind == "kp":
            return f"kp:{value}", None
        if value:
            return "new_query", {"query": value}

        print("Invalid choice")


def interactive_search_loop(
    group: SeriesGroup,
    kp: KPClient,
    initial_query: str,
    lang_priority: str,
    mode: str,
) -> Optional[dict]:
    query = initial_query

    while True:
        print()
        print(f"Source dir   : {_display_path(group.source_dir)}")
        print(f"Search query : {query}")

        try:
            results = kp.search(query)
        except Exception as e:
            print(f"WARNING: KP search failed for {query}: {e}")
            results = []

        results = filter_series_candidates(results)
        results = sort_candidates(results, expected_type="TV_SERIES")
        top = results[:10]

        if mode == "smart":
            if len(top) == 1 and candidate_matches_lang(top[0], lang_priority):
                item = top[0]
                name = item.get("nameRu") or item.get("nameEn") or item.get("nameOriginal") or "<unnamed>"
                year = item.get("year") or "?"
                print(f"Auto-selected: {name} ({year}) [{item.get('type')}] [kp{item.get('filmId')}]")
                return item

        if not top:
            next_action = prompt_search_query_no_results()
            if not next_action:
                continue
            if next_action == "1":
                return None
            if next_action == "2":
                continue

            kind, value = parse_manual_input(next_action)
            if kind == "kp":
                item = try_pick_by_kp_id(kp, value)
                if item:
                    name = item.get("nameRu") or item.get("nameEn") or item.get("nameOriginal") or "<unnamed>"
                    year = item.get("year") or "?"
                    print(f"Selected by kp id: {name} ({year}) [{item.get('type')}] [kp{item.get('filmId')}]")
                    return item
                print(f"KP id not found or not a series: {value}")
                continue

            query = value
            continue

        action, chosen = choose_from_results(query, top)
        if action == "chosen":
            return chosen
        if action == "skip":
            return None
        if action == "retry":
            continue
        if action == "new_query":
            value = chosen["query"]
            kind, parsed = parse_manual_input(value)
            if kind == "kp":
                item = try_pick_by_kp_id(kp, parsed)
                if item:
                    name = item.get("nameRu") or item.get("nameEn") or item.get("nameOriginal") or "<unnamed>"
                    year = item.get("year") or "?"
                    print(f"Selected by kp id: {name} ({year}) [{item.get('type')}] [kp{item.get('filmId')}]")
                    return item
                print(f"KP id not found or not a series: {parsed}")
                continue

            query = parsed
            continue

        if action.startswith("kp:"):
            kp_id = action.split(":", 1)[1]
            item = try_pick_by_kp_id(kp, kp_id)
            if item:
                name = item.get("nameRu") or item.get("nameEn") or item.get("nameOriginal") or "<unnamed>"
                year = item.get("year") or "?"
                print(f"Selected by kp id: {name} ({year}) [{item.get('type')}] [kp{item.get('filmId')}]")
                return item
            print(f"KP id not found or not a series: {kp_id}")
            continue


def build_template_values(
    series_title: str,
    original_title: Optional[str],
    ids: MediaIDs,
    year: Optional[str],
    season: Optional[int] = None,
    episode: Optional[int] = None,
    lang: Optional[str] = None,
    subtype: Optional[str] = None,
    ext: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "title": series_title or "",
        "series_title": series_title or "",
        "original_title": original_title or "",
        "kp": ids.kp or "",
        "tt": ids.tt or "",
        "year": year or "",
        "season": season if season is not None else "",
        "episode": episode if episode is not None else "",
        "lang": lang or "",
        "subtype": subtype or "",
        "ext": ext or "",
    }


def render_series_folder_name(series_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str]) -> str:
    values = build_template_values(series_title, original_title, ids, year)
    return render_template(SERIES_FOLDER_TEMPLATE, values, is_filename=False)


def render_season_folder_name(series_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], season: int) -> str:
    values = build_template_values(series_title, original_title, ids, year, season=season)
    return render_template(SEASON_FOLDER_TEMPLATE, values, is_filename=False)


def render_episode_file_name(
    series_title: str,
    original_title: Optional[str],
    ids: MediaIDs,
    year: Optional[str],
    season: int,
    episode: int,
    ext: str,
) -> str:
    values = build_template_values(
        series_title,
        original_title,
        ids,
        year,
        season=season,
        episode=episode,
        ext=ext.lower(),
    )
    return render_template(EPISODE_FILE_TEMPLATE, values, is_filename=True)


def render_subtitle_file_name(
    series_title: str,
    original_title: Optional[str],
    ids: MediaIDs,
    year: Optional[str],
    season: int,
    episode: int,
    ext: str,
    lang: Optional[str],
    subtype: Optional[str],
) -> str:
    values = build_template_values(
        series_title,
        original_title,
        ids,
        year,
        season=season,
        episode=episode,
        lang=lang,
        subtype=subtype,
        ext=ext.lower(),
    )
    return render_template(SUBTITLE_FILE_TEMPLATE, values, is_filename=True)


def scan_tree(root: Path) -> Dict[Path, SeriesGroup]:
    groups: Dict[Path, SeriesGroup] = {}

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        ext = path.suffix.lower()
        rel = path.relative_to(root)

        if ext in VIDEO_EXTS:
            kind = "video"
        elif ext in SUB_EXTS:
            kind = "sub"
        elif ext in IGNORE_EXTS:
            kind = "other"
        else:
            kind = "other"

        series_dir, season_hint, guessed_title, ids = infer_series_root(path.parent, root)

        if series_dir not in groups:
            groups[series_dir] = SeriesGroup(
                source_dir=series_dir,
                guessed_title=guessed_title,
                ids=ids,
                season_hint=season_hint,
            )

        stem = path.stem
        season, episode = detect_episode_info(stem, season_hint)

        if season is None and path.parent == series_dir:
            season = 1

        lang = subtype = None
        if kind == "sub":
            lang, subtype = detect_sub_meta(stem, path.parent.name)

        groups[series_dir].files.append(
            FileEntry(
                path=path,
                relpath=rel,
                kind=kind,
                season=season,
                episode=episode,
                lang=lang,
                subtype=subtype,
                ext=ext,
            )
        )

    return groups


def resolve_series(
    group: SeriesGroup,
    kp: KPClient,
    cache: dict,
    lang_priority: str,
    mode: str,
) -> Tuple[str, MediaIDs, Optional[str], Optional[str]]:
    cache_key = group.guessed_title.lower()

    if cache_key in cache:
        item = cache[cache_key]
        return (
            item["title"],
            MediaIDs(item.get("kp"), item.get("tt")),
            item.get("year"),
            item.get("original_title"),
        )

    if group.ids.kp:
        title = group.guessed_title
        ids = MediaIDs(kp=group.ids.kp, tt=group.ids.tt)
        year = None
        original_title = None
        if not ids.tt or not year:
            try:
                data = kp.details(int(ids.kp))
                ids.tt = data.get("imdbId") or None
                year = str(data.get("year") or "") or None
                title = choose_display_title(data, {}, title, lang_priority)
                original_title = choose_original_title(data, {})
            except Exception as e:
                print(f"WARNING: failed to enrich kp{ids.kp}: {e}")

        cache[cache_key] = {
            "title": title,
            "kp": ids.kp,
            "tt": ids.tt,
            "year": year,
            "original_title": original_title,
        }
        return title, ids, year, original_title

    if group.ids.tt:
        title = group.guessed_title
        ids = MediaIDs(kp=None, tt=group.ids.tt)
        cache[cache_key] = {
            "title": title,
            "kp": ids.kp,
            "tt": ids.tt,
            "year": None,
            "original_title": None,
        }
        return title, ids, None, None

    chosen = interactive_search_loop(group, kp, group.guessed_title, lang_priority, mode)
    if not chosen:
        return group.guessed_title, group.ids, None, None

    kp_id = str(chosen["filmId"])
    details = chosen.get("_details")
    if not details:
        try:
            details = kp.details(int(kp_id))
        except Exception as e:
            print(f"WARNING: KP details failed for {kp_id}: {e}")
            details = {}

    title = choose_display_title(details, chosen, group.guessed_title, lang_priority)
    original_title = choose_original_title(details, chosen)
    ids = MediaIDs(kp=kp_id, tt=details.get("imdbId") or None)
    year = str(details.get("year") or "") or None

    cache[cache_key] = {
        "title": title,
        "kp": ids.kp,
        "tt": ids.tt,
        "year": year,
        "original_title": original_title,
    }
    return title, ids, year, original_title


def find_paired_subtitles(
    group: SeriesGroup,
    video_entry: FileEntry,
    used_subs: Set[Path],
) -> List[FileEntry]:
    matches: List[FileEntry] = []
    video_stem = normalize_pairing_stem(video_entry.path.stem)
    for fe in group.files:
        if fe.kind != "sub":
            continue
        if fe.path in used_subs:
            continue
        if fe.path.parent != video_entry.path.parent:
            continue
        if normalize_pairing_stem(fe.path.stem) == video_stem:
            matches.append(fe)
    return sorted(matches, key=lambda x: x.path.name.lower())


def build_fallback_ops(
    group: SeriesGroup,
    series_target_dir: Path,
    resolved_title: str,
    original_title: Optional[str],
    ids: MediaIDs,
    year: Optional[str],
    existing_ops: List[PlannedOp],
) -> List[PlannedOp]:
    fallback_ops: List[PlannedOp] = []
    used_targets: set[Path] = {op.dst for op in existing_ops}
    used_subs: set[Path] = set()

    fallback_candidates: Dict[Tuple[Path, int], List[FileEntry]] = defaultdict(list)

    for fe in group.files:
        if fe.kind != "video":
            continue
        if fe.episode is not None:
            continue

        season = fe.season
        if season is None:
            season = detect_season_from_dir(fe.path.parent.name)
        if season is None and fe.path.parent == group.source_dir:
            season = 1

        if season is None:
            continue

        fallback_candidates[(fe.path.parent, season)].append(fe)

    for (src_parent, season), files in sorted(
        fallback_candidates.items(),
        key=lambda item: (str(item[0][0]).lower(), item[0][1]),
    ):
        files_sorted = sorted(files, key=lambda f: f.path.name.lower())
        next_episode = 1

        for fe in files_sorted:
            season_dir = series_target_dir / render_season_folder_name(
                resolved_title,
                original_title,
                ids,
                year,
                season,
            )

            while True:
                new_video_name = render_episode_file_name(
                    resolved_title,
                    original_title,
                    ids,
                    year,
                    season,
                    next_episode,
                    fe.ext,
                )
                video_target = season_dir / new_video_name
                if video_target not in used_targets:
                    break
                next_episode += 1

            if fe.path != video_target:
                fallback_ops.append(
                    PlannedOp(fe.path, video_target, "move", "fallback sorted source files")
                )
                used_targets.add(video_target)

            paired_subs = find_paired_subtitles(group, fe, used_subs)
            for sub in paired_subs:
                new_sub_name = render_subtitle_file_name(
                    resolved_title,
                    original_title,
                    ids,
                    year,
                    season,
                    next_episode,
                    sub.ext,
                    sub.lang,
                    sub.subtype,
                )
                sub_target = season_dir / new_sub_name
                if sub_target in used_targets:
                    continue
                if sub.path != sub_target:
                    fallback_ops.append(
                        PlannedOp(sub.path, sub_target, "move", "fallback paired subtitle")
                    )
                    used_targets.add(sub_target)
                    used_subs.add(sub.path)

            next_episode += 1

    return fallback_ops


def plan_group(
    root: Path,
    group: SeriesGroup,
    resolved_title: str,
    original_title: Optional[str],
    ids: MediaIDs,
    year: Optional[str],
) -> List[PlannedOp]:
    ops: List[PlannedOp] = []

    series_folder = render_series_folder_name(resolved_title, original_title, ids, year)
    series_target_dir = root / series_folder

    planned_media_ops = 0

    for fe in group.files:
        if fe.kind not in {"video", "sub"}:
            continue
        if not fe.season or not fe.episode:
            continue

        season_dir = series_target_dir / render_season_folder_name(
            resolved_title,
            original_title,
            ids,
            year,
            fe.season,
        )

        if fe.kind == "video":
            new_name = render_episode_file_name(
                resolved_title,
                original_title,
                ids,
                year,
                fe.season,
                fe.episode,
                fe.ext,
            )
        else:
            new_name = render_subtitle_file_name(
                resolved_title,
                original_title,
                ids,
                year,
                fe.season,
                fe.episode,
                fe.ext,
                fe.lang,
                fe.subtype,
            )

        target = season_dir / new_name
        if fe.path != target:
            ops.append(PlannedOp(fe.path, target, "move", "normalize episode/subtitle placement"))
            planned_media_ops += 1

    fallback_ops = build_fallback_ops(
        group=group,
        series_target_dir=series_target_dir,
        resolved_title=resolved_title,
        original_title=original_title,
        ids=ids,
        year=year,
        existing_ops=ops,
    )
    ops.extend(fallback_ops)
    planned_media_ops += len(fallback_ops)

    if planned_media_ops == 0 and group.source_dir != series_target_dir:
        ops.append(PlannedOp(group.source_dir, series_target_dir, "rename", "normalize series folder"))

    return ops


def _season_source_label(src: Path, series_root: Path) -> str:
    try:
        rel_parent = src.parent.relative_to(series_root)
        if rel_parent.parts:
            return str(rel_parent).replace("\\", "/")
    except Exception:
        pass
    return "."


def _season_target_label(dst: Path, series_target_dir: Path) -> str:
    try:
        rel_parent = dst.parent.relative_to(series_target_dir)
        if rel_parent.parts:
            return str(rel_parent).replace("\\", "/")
    except Exception:
        pass
    return "."


def build_tree_preview_detailed(
    root: Path,
    ops: List[PlannedOp],
    source_series_dir: Path,
) -> Dict[str, Dict[str, List[Tuple[str, str, str]]]]:
    preview: Dict[str, Dict[str, List[Tuple[str, str, str]]]] = defaultdict(lambda: defaultdict(list))

    target_series_name = None
    target_series_dir = None

    for op in ops:
        rel = op.dst.relative_to(root)
        if len(rel.parts) >= 1:
            target_series_name = rel.parts[0]
            target_series_dir = root / target_series_name
            break

    if target_series_name is None or target_series_dir is None:
        return preview

    for op in ops:
        if op.kind == "rename":
            preview[target_series_name]
            continue

        if op.kind != "move":
            continue

        src_season = _season_source_label(op.src, source_series_dir)
        dst_season = _season_target_label(op.dst, target_series_dir)
        season_key = f"[{src_season}] -> [{dst_season}]"
        preview[target_series_name][season_key].append((op.src.name, op.dst.name, op.reason))

    for series in preview:
        for season in preview[series]:
            unique_items = []
            seen = set()
            for item in preview[series][season]:
                if item not in seen:
                    seen.add(item)
                    unique_items.append(item)
            preview[series][season] = unique_items

    return preview


def print_tree_preview(root: Path, ops: List[PlannedOp], source_series_dir: Path) -> None:
    preview = build_tree_preview_detailed(root, ops, source_series_dir)
    if not preview:
        print("Already normalized: no moves needed")
        return

    print("Planned tree:")
    for series in sorted(preview):
        print(f"  {series}/")
        season_names = sorted(preview[series])
        shown_seasons = season_names[:MAX_PREVIEW_SEASONS]

        for season in shown_seasons:
            print(f"    {season}")
            files = preview[series][season]
            shown_files = files[:MAX_PREVIEW_FILES_PER_SEASON]
            for src_name, dst_name, reason in shown_files:
                suffix = ""
                if reason == "fallback sorted source files":
                    suffix = " [fallback]"
                elif reason == "fallback paired subtitle":
                    suffix = " [paired-sub]"
                print(f"      {src_name} -> {dst_name}{suffix}")
            if len(files) > MAX_PREVIEW_FILES_PER_SEASON:
                print("      ...")

        if len(season_names) > MAX_PREVIEW_SEASONS:
            print("    ...")


def print_fallback_preview(ops: List[PlannedOp], source_series_dir: Path, root: Path) -> None:
    fallback_ops = [
        op for op in ops
        if op.reason in {"fallback sorted source files", "fallback paired subtitle"}
    ]
    if not fallback_ops:
        return

    target_series_dir = None
    for op in fallback_ops:
        try:
            rel = op.dst.relative_to(root)
            if len(rel.parts) >= 1:
                target_series_dir = root / rel.parts[0]
                break
        except Exception:
            continue

    if target_series_dir is None:
        return

    print()
    print("Fallback assignments:")
    shown = 0
    for op in fallback_ops:
        src_rel = _relative_under(source_series_dir, op.src)
        dst_rel = _relative_under(target_series_dir, op.dst)
        print(f"  {src_rel} -> {dst_rel}")
        shown += 1
        if shown >= MAX_PREVIEW_FALLBACK_FILES and len(fallback_ops) > shown:
            print("  ...")
            break


def confirm_series_plan(root: Path, group: SeriesGroup, resolved_title: str, ids: MediaIDs, ops: List[PlannedOp]) -> str:
    print()
    print("------------------------------------------------------------")
    print(f"Source dir   : {_display_path(group.source_dir)}")
    print(f"Resolved     : {resolved_title}")
    print(f"IDs          : kp={ids.kp} tt={ids.tt}")
    print_tree_preview(root, ops, group.source_dir)
    print_fallback_preview(ops, group.source_dir, root)
    print()
    print("0) exit")
    print("1) accept")
    print("2) reject")
    print("3) re-select match")
    print("4) skip")
    print("Enter = accept")
    while True:
        choice = safe_input("> ").strip()
        if choice == "":
            return "1"
        if choice in {"1", "2", "3", "4"}:
            return choice
        print("Invalid choice")


def print_series_summary(applied: int, errors: int, removed_dirs: int, kept_dirs: int, dry_run: bool) -> None:
    mode = "DRY" if dry_run else "APPLY"
    print(f"{mode}: ops={applied}, removed_empty_dirs={removed_dirs}, kept_nonempty_dirs={kept_dirs}, errors={errors}")


def log_line(log_path: Path, message: str) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def _build_series_log_context(ops: List[PlannedOp], source_series_dir: Path, root: Path) -> Tuple[str, Path]:
    target_series_name = source_series_dir.name
    target_series_dir = root / target_series_name

    for op in ops:
        try:
            rel = op.dst.relative_to(root)
            if len(rel.parts) >= 1:
                target_series_name = rel.parts[0]
                target_series_dir = root / target_series_name
                break
        except Exception:
            continue

    return target_series_name, target_series_dir


def log_series_header(log_path: Path, source_series_dir: Path, ops: List[PlannedOp], root: Path) -> Tuple[Path, str]:
    target_series_name, target_series_dir = _build_series_log_context(ops, source_series_dir, root)
    log_line(log_path, "============================================================")
    log_line(log_path, f"SERIES  {source_series_dir.name}  ->  {target_series_name}")
    log_line(log_path, "")
    return target_series_dir, target_series_name


def apply_ops(
    ops: List[PlannedOp],
    log_path: Path,
    dry_run: bool,
    source_series_dir: Path,
    root: Path,
) -> Tuple[int, int, Path]:
    errors = 0
    applied = 0

    target_series_dir, _ = log_series_header(log_path, source_series_dir, ops, root)

    for op in ops:
        try:
            if op.kind == "rename":
                if not op.src.exists():
                    raise FileNotFoundError(f"source not found: {op.src}")

                if op.dst.exists():
                    if op.src.resolve() == op.dst.resolve():
                        continue
                    raise FileExistsError(f"destination already exists: {op.dst}")

                src_rel = _relative_under(root, op.src)
                dst_rel = _relative_under(root, op.dst)

                if dry_run:
                    log_line(log_path, f"RENAME {src_rel}  =>  {dst_rel}")
                    applied += 1
                else:
                    op.dst.parent.mkdir(parents=True, exist_ok=True)
                    op.src.rename(op.dst)
                    log_line(log_path, f"RENAME {src_rel}  =>  {dst_rel}")
                    applied += 1

            elif op.kind == "move":
                if not op.src.exists():
                    raise FileNotFoundError(f"source not found: {op.src}")

                if op.dst.exists():
                    try:
                        if op.src.resolve() == op.dst.resolve():
                            continue
                    except Exception:
                        pass
                    raise FileExistsError(f"destination already exists: {op.dst}")

                src_rel = _relative_under(source_series_dir, op.src)
                dst_rel = _relative_under(target_series_dir, op.dst)

                op_word = "MOVE"
                if op.reason == "fallback sorted source files":
                    op_word = "FALLBK"
                elif op.reason == "fallback paired subtitle":
                    op_word = "PAIRSB"

                if dry_run:
                    log_line(log_path, f"{op_word:<6} {src_rel}  =>  {dst_rel}")
                    applied += 1
                else:
                    op.dst.parent.mkdir(parents=True, exist_ok=True)
                    op.src.rename(op.dst)
                    log_line(log_path, f"{op_word:<6} {src_rel}  =>  {dst_rel}")
                    applied += 1

            else:
                continue

        except Exception as e:
            errors += 1
            log_line(log_path, f"ERROR  {op.kind}  {op.src.name}  ::  {e}")

    return applied, errors, target_series_dir


def prune_empty_dirs(start_dir: Path, stop_dir: Path, log_path: Path, dry_run: bool) -> Tuple[int, int, int]:
    removed = 0
    kept_nonempty = 0
    errors = 0

    if not start_dir.exists():
        return removed, kept_nonempty, errors

    dirs = sorted(
        [p for p in start_dir.rglob("*") if p.is_dir()],
        key=lambda p: len(p.parts),
        reverse=True,
    )
    dirs.append(start_dir)

    for d in dirs:
        try:
            if d.resolve() == stop_dir.resolve():
                continue
        except Exception:
            if d == stop_dir:
                continue

        try:
            rel_dir = _relative_under(stop_dir, d)

            if any(d.iterdir()):
                kept_nonempty += 1
                log_line(log_path, f"KEEPDIR {rel_dir}  ::  not empty")
                continue

            if dry_run:
                log_line(log_path, f"DELDIR {rel_dir}")
                removed += 1
            else:
                d.rmdir()
                log_line(log_path, f"DELDIR {rel_dir}")
                removed += 1

        except Exception as e:
            errors += 1
            log_line(log_path, f"ERROR  DELDIR  {d.name}  ::  {e}")

    return removed, kept_nonempty, errors


def save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize TV series tree. Applies changes immediately per series; use --dry-run to preview only.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("root", nargs="?", help="Root path to Serials")
    parser.add_argument("--cache", default=DEFAULT_CACHE_FILE, help="Cache json path")
    parser.add_argument("--ops-log", default=DEFAULT_OPS_LOG, help="Operations log file path")
    parser.add_argument(
        "--lang-priority",
        choices=["ru", "en", "any"],
        default=DEFAULT_LANG_PRIORITY,
        help="Preferred title language for final folder names and auto-match checks",
    )
    parser.add_argument(
        "--mode",
        choices=["smart", "manual"],
        default=DEFAULT_MODE,
        help="smart: auto-accept one fitting candidate; manual: always confirm",
    )
    parser.add_argument(
        "--dry-first",
        action="store_true",
        help="Show resulting tree for each series and ask confirmation before including its plan",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify filesystem; only print/log planned operations",
    )
    return parser


def main() -> int:
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()

    if not args.root:
        parser.print_help()
        return 1

    root = Path(args.root).resolve()
    cache_path = Path(args.cache).resolve()
    ops_log_path = Path(args.ops_log).resolve()

    if not root.is_dir():
        print(f"ERROR: root not found: {root}")
        return 1

    try:
        validate_templates()
    except ValueError as e:
        print(f"ERROR: template validation failed: {e}")
        return 1

    kp = KPClient(DEFAULT_API_KEY)
    cache = load_cache(cache_path)

    groups = scan_tree(root)

    total_applied = 0
    total_removed_dirs = 0
    total_kept_dirs = 0
    total_errors = 0
    processed_groups = 0

    log_line(ops_log_path, "============================================================")
    log_line(ops_log_path, f"START root={root} dry_run={args.dry_run}")

    try:
        print(f"Found groups: {len(groups)}")
        print()

        for group in sorted(groups.values(), key=lambda g: str(g.source_dir).lower()):
            while True:
                print("============================================================")
                print(f"Source dir   : {_display_path(group.source_dir, root)}")
                print(f"Guessed title: {group.guessed_title}")
                print(f"Files        : {len(group.files)}")
                if group.ids.kp or group.ids.tt:
                    print(f"Existing IDs : kp={group.ids.kp} tt={group.ids.tt}")

                resolved_title, ids, year, original_title = resolve_series(
                    group=group,
                    kp=kp,
                    cache=cache,
                    lang_priority=args.lang_priority,
                    mode=args.mode,
                )
                group.resolved_title = resolved_title
                group.ids = ids
                group.resolved_year = year
                group.resolved_original_title = original_title

                print(f"Resolved     : {resolved_title}")
                print(f"IDs          : kp={ids.kp} tt={ids.tt}")

                ops = plan_group(root, group, resolved_title, original_title, ids, year)

                if not args.dry_first:
                    applied, errors, _target_series_dir = apply_ops(
                        ops, ops_log_path, args.dry_run, group.source_dir, root
                    )
                    removed_dirs, kept_dirs, prune_errors = prune_empty_dirs(
                        group.source_dir, root, ops_log_path, args.dry_run
                    )

                    total_applied += applied
                    total_removed_dirs += removed_dirs
                    total_kept_dirs += kept_dirs
                    total_errors += errors + prune_errors
                    processed_groups += 1

                    log_line(
                        ops_log_path,
                        f"SUMMARY ops={applied} removed_dirs={removed_dirs} kept_dirs={kept_dirs} errors={errors + prune_errors}",
                    )
                    log_line(ops_log_path, "")

                    print_series_summary(applied, errors + prune_errors, removed_dirs, kept_dirs, args.dry_run)
                    if applied == 0 and errors == 0 and removed_dirs == 0:
                        print("Already normalized: no moves needed")
                    if kept_dirs:
                        print("Note: some source directories were kept because they are not empty.")
                    break

                decision = confirm_series_plan(root, group, resolved_title, ids, ops)
                if decision == "1":
                    applied, errors, _target_series_dir = apply_ops(
                        ops, ops_log_path, args.dry_run, group.source_dir, root
                    )
                    removed_dirs, kept_dirs, prune_errors = prune_empty_dirs(
                        group.source_dir, root, ops_log_path, args.dry_run
                    )

                    total_applied += applied
                    total_removed_dirs += removed_dirs
                    total_kept_dirs += kept_dirs
                    total_errors += errors + prune_errors
                    processed_groups += 1

                    log_line(
                        ops_log_path,
                        f"SUMMARY ops={applied} removed_dirs={removed_dirs} kept_dirs={kept_dirs} errors={errors + prune_errors}",
                    )
                    log_line(ops_log_path, "")

                    print_series_summary(applied, errors + prune_errors, removed_dirs, kept_dirs, args.dry_run)
                    if applied == 0 and errors == 0 and removed_dirs == 0:
                        print("Already normalized: no moves needed")
                    if kept_dirs:
                        print("Note: some source directories were kept because they are not empty.")
                    break

                if decision == "2":
                    processed_groups += 1
                    break
                if decision == "4":
                    processed_groups += 1
                    break
                if decision == "3":
                    cache_key = group.guessed_title.lower()
                    if cache_key in cache:
                        del cache[cache_key]
                    continue

    except UserAbort:
        print()
        print("Exit requested. Stopping cleanly.")

    finally:
        save_cache(cache_path, cache)
        log_line(
            ops_log_path,
            f"END processed_groups={processed_groups} applied={total_applied} removed_dirs={total_removed_dirs} kept_dirs={total_kept_dirs} errors={total_errors}",
        )

    print()
    print(f"Cache saved: {cache_path}")
    print(f"Operations log: {ops_log_path}")
    if args.dry_run:
        print("Dry-run complete.")
    else:
        print("Apply complete.")
    print(f"Processed groups: {processed_groups}")
    print(f"Applied operations: {total_applied}")
    print(f"Removed empty dirs: {total_removed_dirs}")
    print(f"Kept non-empty dirs: {total_kept_dirs}")

    if total_errors:
        print(f"Finished with {total_errors} error(s). Check log.")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())