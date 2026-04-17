#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SerialsRenamer.py

Production renamer/reorganizer for TV series folders.

By default this script APPLIES filesystem changes immediately per series
after confirmation.
Use --dry-run for preview-only mode.

Canonical output ID formats:
- [kp-1234567]
- [tmdbid-123456]
- [imdbid-tt1234567]
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Optional, List, Dict, Tuple, Any, Set
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from collections import defaultdict


DEFAULT_KP_API_KEY = "85d30ae5-d875-4c5f-900d-8e37bb20625e"
DEFAULT_TMDB_BEARER = "INSERT_YOUR_TMDB_BEARER_TOKEN_HERE"
DEFAULT_CACHE_FILE = ".series_rename_cache.json"
# Clear or replace the cache when testing new localization / template behavior.
DEFAULT_OPS_LOG = "SerialsRenamer.operations.log"
DEFAULT_MODE = "smart"
DEFAULT_METADATA_PROFILE = "ru"

MAX_PREVIEW_SEASONS = 3
MAX_PREVIEW_FILES_PER_SEASON = 3
MAX_PREVIEW_FALLBACK_FILES = 12

# Conservative defaults for everyday library use. Add extra localized fields only when needed.
#
# Template fields
#
# Primary fields:
#   {title}
#       Primary display title for the active metadata profile.
#       - ru profile: usually the Russian title
#       - intl profile: usually the English / international title
#
#   {original_title}
#       Original or provider-original title, when available.
#
#   {title_local}
#       Localized title for the active profile context.
#
# Localized title fields:
#   {title_ru}, {title_en}, {title_de}, {title_fr}, {title_ko}, ...
#       Localized titles from TMDb translations, when available.
#       Regional variants are also supported, for example:
#       {title_pt_BR}, {title_pt_PT}, {title_zh_CN}, {title_zh_TW}, {title_es_MX}
#
# Other supported fields:
#   {kp}      Kinopoisk id without prefix
#   {tmdb}    TMDb id without prefix
#   {tt}      IMDb id including tt-prefix
#   {year}    Series year
#   {season}  Season number
#   {episode} Episode number
#   {lang}    Subtitle language token
#   {subtype} Subtitle subtype token
#   {ext}     File extension
#
# Deduplication rules
#
# {title} is always the primary field.
# Before rendering:
#   - if {original_title} is equal to {title}, it is cleared
#   - if any {title_XX} is equal to {title}, it is cleared
#   - if secondary fields duplicate each other, only the first unique value is kept
#     and later duplicates are cleared
#
# Deduplication uses normalized title keys:
#   - case-insensitive
#   - repeated spaces ignored
#   - separator / punctuation differences normalized
#
# Missing values
#
# If a field is empty or unavailable, it renders as an empty string.
# Empty brackets / parentheses and extra spaces are cleaned automatically.
#
# Profile behavior
#
# ru profile:
#   - primary source: Kinopoisk
#   - enrichment: TMDb
#   - default primary title language: Russian
#
# intl profile:
#   - primary source: TMDb
#   - default primary title language: English
#
# Notes
#
# - Not every series has translations for every language.
# - Localized title availability depends on TMDb translations for that specific show.
# - When testing localization changes, use a fresh cache file or clear the existing
#   cache to avoid stale metadata.
#
# Common language field examples
#
#   ru     - Russian
#   en     - English
#   de     - German
#   fr     - French
#   es     - Spanish
#   it     - Italian
#   pt     - Portuguese
#   pt_BR  - Portuguese (Brazil)
#   pt_PT  - Portuguese (Portugal)
#   uk     - Ukrainian
#   pl     - Polish
#   cs     - Czech
#   hu     - Hungarian
#   tr     - Turkish
#   nl     - Dutch
#   sv     - Swedish
#   da     - Danish
#   fi     - Finnish
#   ro     - Romanian
#   bg     - Bulgarian
#   el     - Greek
#   he     - Hebrew
#   ar     - Arabic
#   fa     - Persian
#   zh     - Chinese
#   zh_CN  - Chinese (China)
#   zh_TW  - Chinese (Taiwan)
#   ja     - Japanese
#   ko     - Korean
#   vi     - Vietnamese
#   th     - Thai
#   id     - Indonesian
#   ms     - Malay
#   hi     - Hindi
#   ka     - Georgian
#   lt     - Lithuanian
#   lv     - Latvian
#   et     - Estonian
#   bs     - Bosnian
#   sr     - Serbian
#   hr     - Croatian
#   sk     - Slovak
#   sl     - Slovenian
#
# Example defaults
#
# ru:
#   RU_SERIES_FOLDER_TEMPLATE = "{title} ({original_title}) ({year}) [kp-{kp}][tmdbid-{tmdb}][imdbid-{tt}]"
#   -> Блудливая Калифорния (Californication) (2007) [kp-394375][tmdbid-1215][imdbid-tt0904208]
#
# intl:
#   INTL_SERIES_FOLDER_TEMPLATE = "{title} ({original_title}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"
#   -> Californication (2007) [tmdbid-1215][imdbid-tt0904208]
#
# intl with a localized extra title:
#   "{title} ({title_ru}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"
#   -> Californication (Блудливая Калифорния) (2007) [tmdbid-1215][imdbid-tt0904208]
#
# Duplicate values are removed automatically:
#   - if {original_title} == {title}, {original_title} is cleared
#   - if {title_ru} == {title}, {title_ru} is cleared
#   - if secondary fields duplicate each other, only the first unique value is kept


RU_SERIES_FOLDER_TEMPLATE = "{title} ({original_title}) ({year}) [kp-{kp}][tmdbid-{tmdb}][imdbid-{tt}]"
INTL_SERIES_FOLDER_TEMPLATE = "{title} ({original_title}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"

RU_SEASON_FOLDER_TEMPLATE = "Season {season:02d}"
INTL_SEASON_FOLDER_TEMPLATE = "Season {season:02d}"

RU_EPISODE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{ext}"
INTL_EPISODE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{ext}"

RU_SUBTITLE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{sub_suffix}{ext}"
INTL_SUBTITLE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{sub_suffix}{ext}"


VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"}
SUB_EXTS = {".srt", ".ass", ".ssa", ".sub"}
IGNORE_EXTS = {".jpg", ".jpeg", ".png", ".nfo", ".log", ".txt"}

SERIES_TYPES = {"TV_SERIES", "MINI_SERIES"}

ALLOWED_TEMPLATE_FIELDS = {
    "title", "series_title", "original_title", "title_local",
    "kp", "tt", "tmdb", "year", "season", "episode", "lang", "subtype", "sub_suffix", "ext",
}

LANG_FIELD_PATTERN = re.compile(r"^title_[A-Za-z]{2,3}(?:_[A-Za-z]{2,4})?$")

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
    tmdb: Optional[str] = None


@dataclass
class FileEntry:
    path: Path
    relpath: Path
    kind: str
    season: Optional[int] = None
    episode: Optional[int] = None
    lang: Optional[str] = None
    subtype: Optional[str] = None
    sub_suffix: Optional[str] = None
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
    localized_titles: Dict[str, str] = field(default_factory=dict)
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
        except Exception:
            return None


class TMDbClient:
    def __init__(self, bearer_token: str, timeout: int = 20):
        self.bearer_token = bearer_token
        self.timeout = timeout

    def _get_json(self, url: str) -> dict:
        req = Request(url, headers={
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        })
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
            except Exception:
                payload = None
            if isinstance(payload, dict):
                status_code = payload.get("status_code")
                status_message = payload.get("status_message")
                if status_code or status_message:
                    raise RuntimeError(f"TMDb API error {status_code}: {status_message}") from None
            raise RuntimeError(f"TMDb request failed: HTTP {e.code}") from None
        if isinstance(data, dict) and data.get("success") is False and (data.get("status_code") or data.get("status_message")):
            status_code = data.get("status_code")
            status_message = data.get("status_message")
            raise RuntimeError(f"TMDb API error {status_code}: {status_message}")
        return data

    def search_tv(self, query: str, language: str = "en-US", year: Optional[str] = None, page: int = 1) -> list:
        params = {"query": query, "language": language, "page": page}
        if year and str(year).isdigit():
            params["first_air_date_year"] = str(year)
        qs = urlencode(params, quote_via=quote)
        url = f"https://api.themoviedb.org/3/search/tv?{qs}"
        data = self._get_json(url)
        return data.get("results", [])

    def tv_external_ids(self, tv_id: int) -> dict:
        return self._get_json(f"https://api.themoviedb.org/3/tv/{tv_id}/external_ids")

    def tv_details(self, tv_id: int, language: str = "en-US") -> dict:
        qs = urlencode({"language": language})
        return self._get_json(f"https://api.themoviedb.org/3/tv/{tv_id}?{qs}")

    def tv_translations(self, tv_id: int) -> dict:
        return self._get_json(f"https://api.themoviedb.org/3/tv/{tv_id}/translations")

    def try_tv_external_ids(self, tv_id: int) -> Optional[dict]:
        try:
            return self.tv_external_ids(tv_id)
        except Exception:
            return None

    def try_tv_details(self, tv_id: int, language: str = "en-US") -> Optional[dict]:
        try:
            return self.tv_details(tv_id, language)
        except Exception:
            return None

    def try_tv_translations(self, tv_id: int) -> Optional[dict]:
        try:
            return self.tv_translations(tv_id)
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


def normalize_title_key(s: str) -> str:
    s = s.casefold()
    return re.sub(r"[\W_]+", "", s, flags=re.UNICODE)


def safe_year(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if re.fullmatch(r"\d{4}", s) else None


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
    stem = filename[:-len(suffixes)] if suffixes else filename
    safe_stem = sanitize_name_component(stem)
    safe = (safe_stem + suffixes).rstrip(" .")
    return safe or "_"


def cleanup_rendered_template(s: str) -> str:
    s = re.sub(r"\[(?:kp-|tmdbid-|imdbid-)?\]", "", s)
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
        if field_name in (None, ""):
            continue
        if field_name not in ALLOWED_TEMPLATE_FIELDS and not LANG_FIELD_PATTERN.fullmatch(field_name):
            unknown_fields.append(field_name)
    if unknown_fields:
        allowed = ", ".join(sorted(ALLOWED_TEMPLATE_FIELDS))
        raise ValueError(
            f"{template_name}: unknown field(s): {', '.join(sorted(set(unknown_fields)))}. "
            f"Allowed fields: {allowed}. Current template: {template_value}"
        )


def validate_templates() -> None:
    for prefix, series_template, season_template, episode_template, subtitle_template in [
        ("RU", RU_SERIES_FOLDER_TEMPLATE, RU_SEASON_FOLDER_TEMPLATE, RU_EPISODE_FILE_TEMPLATE, RU_SUBTITLE_FILE_TEMPLATE),
        ("INTL", INTL_SERIES_FOLDER_TEMPLATE, INTL_SEASON_FOLDER_TEMPLATE, INTL_EPISODE_FILE_TEMPLATE, INTL_SUBTITLE_FILE_TEMPLATE),
    ]:
        validate_single_template(f"{prefix}_SERIES_FOLDER_TEMPLATE", series_template)
        validate_single_template(f"{prefix}_SEASON_FOLDER_TEMPLATE", season_template)
        validate_single_template(f"{prefix}_EPISODE_FILE_TEMPLATE", episode_template)
        validate_single_template(f"{prefix}_SUBTITLE_FILE_TEMPLATE", subtitle_template)


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
    rendered = cleanup_rendered_template(rendered)
    if is_filename:
        return sanitize_filename(rendered)
    return sanitize_name_component(rendered)


def strip_ids(name: str) -> Tuple[str, MediaIDs]:
    ids = MediaIDs()
    m = re.search(r"\[kp-?(\d+)\]", name, re.I)
    if m:
        ids.kp = m.group(1)
    m = re.search(r"\[(?:tmdbid-|tmdb-?|tmdb)(\d+)\]", name, re.I)
    if m:
        ids.tmdb = m.group(1)
    m = re.search(r"\[(?:imdbid(?:=|-)?|)(tt\d+)\]", name, re.I)
    if m:
        ids.tt = m.group(1)
    clean = re.sub(r"\[kp-?\d+\]", "", name, flags=re.I)
    clean = re.sub(r"\[(?:tmdbid-|tmdb-?|tmdb)\d+\]", "", clean, flags=re.I)
    clean = re.sub(r"\[(?:imdbid(?:=|-)?|)tt\d+\]", "", clean, flags=re.I)
    clean = re.sub(r"\[[^\]]*\]", "", clean)
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
        if known_season is not None:
            return known_season, int(m.group(1))
    return None, None


def detect_sub_meta(stem: str, parent_name: str) -> Tuple[Optional[str], Optional[str]]:
    low = f"{parent_name} {stem}".lower()
    low_sep = re.sub(r"[._-]+", " ", low)
    lang = None
    subtype = None
    for token, code in LANG_TOKENS.items():
        if re.search(rf"\b{re.escape(token)}\b", low_sep):
            lang = code
            break
    for token, code in SUBTYPE_TOKENS.items():
        if re.search(rf"\b{re.escape(token)}\b", low_sep):
            subtype = code
            break
    return lang, subtype


def normalize_pairing_stem(stem: str) -> str:
    stem = stem.strip()
    stem = stem.rstrip(".")
    stem = re.sub(r"\s+", " ", stem)
    return stem.casefold()


def normalize_subtitle_suffix(suffix: Optional[str]) -> str:
    suffix = str(suffix or "").strip()
    if not suffix:
        return ""
    suffix = suffix.replace(" ", ".").replace("_", ".").replace("-", ".")
    suffix = re.sub(r"\.+", ".", suffix)
    if not suffix.startswith("."):
        suffix = "." + suffix
    return suffix.rstrip(".")


def extract_subtitle_suffix(subtitle_stem: str, video_stem: str) -> Optional[str]:
    sub_clean = subtitle_stem.strip().rstrip(".")
    video_clean = video_stem.strip().rstrip(".")
    if not sub_clean or not video_clean:
        return None
    sub_cf = sub_clean.casefold()
    video_cf = video_clean.casefold()

    if sub_cf == video_cf:
        return ""

    if not sub_cf.startswith(video_cf):
        return None

    suffix = sub_clean[len(video_clean):]
    if not suffix:
        return ""

    if suffix[0] not in "._- ":
        return None

    return normalize_subtitle_suffix(suffix)


def find_matching_video_stem(group: "SeriesGroup", sub_entry: FileEntry) -> Optional[str]:
    if sub_entry.season is None or sub_entry.episode is None:
        return None
    candidates: List[str] = []
    for fe in group.files:
        if fe.kind != "video":
            continue
        if fe.path.parent != sub_entry.path.parent:
            continue
        if fe.season == sub_entry.season and fe.episode == sub_entry.episode:
            candidates.append(fe.path.stem)
    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    return candidates[0]


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


def tmdb_result_year(item: dict) -> Optional[str]:
    first_air = str(item.get("first_air_date") or "").strip()
    m = re.match(r"(\d{4})", first_air)
    return m.group(1) if m else None


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
    return details.get("nameOriginal") or details.get("nameEn") or chosen.get("nameOriginal") or chosen.get("nameEn") or None


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
    m = re.fullmatch(r"tmdb[_ -]?(\d+)", value, re.I)
    if m:
        return "tmdb", m.group(1)
    m = re.fullmatch(r"(\d{5,10})", value)
    if m:
        return "kp", m.group(1)
    return "query", value


def try_pick_by_kp_id(kp: KPClient, kp_id: str) -> Optional[dict]:
    data = kp.try_details(int(kp_id))
    if not data or (data.get("type") or "") not in SERIES_TYPES:
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


def score_tmdb_match(item: dict, query: str, year: Optional[str]) -> Tuple[int, int, int, int]:
    q = normalize_title_key(query)
    names = [str(item.get("name") or ""), str(item.get("original_name") or "")]
    keys = [normalize_title_key(x) for x in names if x]
    year_match = 0 if (year and tmdb_result_year(item) == str(year)) else 1
    exact = 0 if q and q in keys else 1
    contains = 0 if q and any(q in k or k in q for k in keys if k) else 1
    popularity_penalty = -int(float(item.get("popularity") or 0) * 1000)
    return (exact, contains, year_match, popularity_penalty)


def enrich_from_tmdb_ru(tmdb: TMDbClient, resolved_title: str, original_title: Optional[str], year: Optional[str], ids: MediaIDs) -> MediaIDs:
    if ids.tmdb and ids.tt:
        return ids
    candidates: List[Tuple[Tuple[int, int, int, int], dict]] = []
    queries = []
    if resolved_title:
        queries.append((resolved_title, "ru-RU"))
    if original_title and normalize_title_key(original_title) != normalize_title_key(resolved_title or ""):
        queries.append((original_title, "en-US"))
    seen = set()
    for query, language in queries:
        key = (query, language)
        if key in seen:
            continue
        seen.add(key)
        try:
            results = tmdb.search_tv(query, language=language, year=year, page=1)
        except Exception:
            results = []
        for item in results[:10]:
            candidates.append((score_tmdb_match(item, query, year), item))
    if not candidates:
        return ids
    candidates.sort(key=lambda x: x[0])
    best = candidates[0][1]
    ids.tmdb = ids.tmdb or str(best.get("id"))
    if not ids.tt and ids.tmdb:
        ext = tmdb.try_tv_external_ids(int(ids.tmdb))
        if ext:
            ids.tt = ext.get("imdb_id") or ids.tt
    return ids


def choose_tmdb_display_title(details: dict, lang_priority: str, guessed: str) -> str:
    localized = details.get("name")
    original = details.get("original_name")
    if lang_priority == "en":
        return localized or original or guessed
    if lang_priority == "ru":
        return localized or original or guessed
    return localized or original or guessed


def interactive_search_loop_tmdb(group: SeriesGroup, tmdb: TMDbClient, initial_query: str, lang_priority: str, mode: str) -> Optional[dict]:
    query = initial_query
    language = "en-US" if lang_priority == "en" else "ru-RU"
    while True:
        print()
        print(f"Source dir   : {group.source_dir.name}")
        print(f"TMDb query   : {query}")
        try:
            results = tmdb.search_tv(query, language=language, year=None, page=1)
        except Exception as e:
            print(f"WARNING: TMDb search failed for {query}: {e}")
            results = []
        top = results[:10]
        if mode == "smart" and len(top) == 1:
            item = top[0]
            name = item.get("name") or item.get("original_name") or "<unnamed>"
            year = tmdb_result_year(item) or "?"
            print(f"Auto-selected: {name} ({year}) [tmdb{item.get('id')}]")
            return item
        if not top:
            print()
            print("No matches found.")
            print("0) exit")
            print("1) skip")
            print("2) retry same search")
            print("Any other input = new search text or tmdb id")
            next_action = safe_input("> ").strip()
            if not next_action:
                continue
            if next_action == "1":
                return None
            if next_action == "2":
                continue
            kind, value = parse_manual_input(next_action)
            if kind == "tmdb":
                details = tmdb.try_tv_details(int(value), language=language)
                if details:
                    details["_external_ids"] = tmdb.try_tv_external_ids(int(value)) or {}
                    return details
                print(f"TMDb id not found: {value}")
                continue
            query = value
            continue
        print()
        print(f"Found TMDb matches for: {query}")
        for idx, item in enumerate(top, start=1):
            tmdb_id = item.get("id")
            name = item.get("name") or item.get("original_name") or "<unnamed>"
            original_name = item.get("original_name") or ""
            year = tmdb_result_year(item) or "?"
            suffix = f" / {original_name}" if original_name and original_name != name else ""
            print(f"{idx}) {name}{suffix} ({year}) [tmdb{tmdb_id}]")
        print("0) exit")
        print("98) skip")
        print("99) retry same search")
        print("Any other input = new search text or tmdb id")
        if len(top) == 1:
            print("Enter = choose 1")
        print()
        while True:
            choice = safe_input("Choose: ").strip()
            if choice == "" and len(top) == 1:
                return top[0]
            if choice == "98":
                return None
            if choice == "99":
                break
            if choice.isdigit():
                n = int(choice)
                if 1 <= n <= len(top):
                    return top[n - 1]
            kind, value = parse_manual_input(choice)
            if kind == "tmdb":
                details = tmdb.try_tv_details(int(value), language=language)
                if details:
                    details["_external_ids"] = tmdb.try_tv_external_ids(int(value)) or {}
                    return details
                print(f"TMDb id not found: {value}")
                continue
            if value:
                query = value
                break
            print("Invalid choice")


def get_profile_templates(metadata_profile: str) -> Dict[str, str]:
    if metadata_profile == "intl":
        return {
            "series": INTL_SERIES_FOLDER_TEMPLATE,
            "season": INTL_SEASON_FOLDER_TEMPLATE,
            "episode": INTL_EPISODE_FILE_TEMPLATE,
            "subtitle": INTL_SUBTITLE_FILE_TEMPLATE,
        }
    return {
        "series": RU_SERIES_FOLDER_TEMPLATE,
        "season": RU_SEASON_FOLDER_TEMPLATE,
        "episode": RU_EPISODE_FILE_TEMPLATE,
        "subtitle": RU_SUBTITLE_FILE_TEMPLATE,
    }


def effective_lang_priority(metadata_profile: str) -> str:
    return "en" if metadata_profile == "intl" else "ru"


def normalize_lang_field_code(code: str) -> str:
    return str(code or "").replace("-", "_")


def merge_localized_titles(*sources: Optional[Dict[str, Optional[str]]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for src in sources:
        if not src:
            continue
        for key, value in src.items():
            key_norm = normalize_lang_field_code(key)
            value_norm = normalize_spaces(str(value or ""))
            if key_norm and value_norm and key_norm not in result:
                result[key_norm] = value_norm
    return result


def localized_titles_from_kp(details: dict, chosen: Optional[dict] = None) -> Dict[str, str]:
    chosen = chosen or {}
    ru = details.get("nameRu") or chosen.get("nameRu")
    en = details.get("nameEn") or details.get("nameOriginal") or chosen.get("nameEn") or chosen.get("nameOriginal")
    return merge_localized_titles({"ru": ru, "en": en})


def localized_titles_from_tmdb_details(details: dict, language: str) -> Dict[str, str]:
    language = str(language or "")
    lang_tag = language.split(",")[0] if language else ""
    lang_norm = normalize_lang_field_code(lang_tag)
    lang_short = normalize_lang_field_code(lang_tag.split("-")[0]) if lang_tag else ""
    localized_name = details.get("name")
    original_name = details.get("original_name")
    result: Dict[str, str] = {}
    if localized_name and lang_norm:
        result[lang_norm] = localized_name
        if lang_short:
            result.setdefault(lang_short, localized_name)
    if original_name:
        result.setdefault("en", original_name)
    return merge_localized_titles(result)


def fetch_tmdb_localized_titles(tmdb: TMDbClient, tmdb_id: Optional[str], languages: List[str]) -> Dict[str, str]:
    if not tmdb_id:
        return {}
    titles: Dict[str, str] = {}
    translations = tmdb.try_tv_translations(int(tmdb_id)) or {}
    for item in translations.get("translations") or []:
        data = item.get("data") or {}
        name = normalize_spaces(str(data.get("name") or ""))
        if not name:
            continue
        lang = normalize_lang_field_code(item.get("iso_639_1") or "")
        region = normalize_lang_field_code(item.get("iso_3166_1") or "")
        if lang:
            titles = merge_localized_titles(titles, {lang: name})
            if region:
                titles = merge_localized_titles(titles, {f"{lang}_{region}": name})
    for language in languages:
        try:
            details = tmdb.try_tv_details(int(tmdb_id), language=language)
        except Exception:
            details = None
        if not details:
            continue
        titles = merge_localized_titles(titles, localized_titles_from_tmdb_details(details, language))
    return titles


def build_template_values(series_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], localized_titles: Optional[Dict[str, str]] = None, title_local: Optional[str] = None, season: Optional[int] = None, episode: Optional[int] = None, lang: Optional[str] = None, subtype: Optional[str] = None, sub_suffix: Optional[str] = None, ext: Optional[str] = None) -> Dict[str, Any]:
    main_title = normalize_spaces(series_title or "")
    main_key = normalize_title_key(main_title)

    values = {
        "title": main_title,
        "series_title": main_title,
        "original_title": "",
        "title_local": "",
        "kp": ids.kp or "",
        "tt": ids.tt or "",
        "tmdb": ids.tmdb or "",
        "year": year or "",
        "season": season if season is not None else "",
        "episode": episode if episode is not None else "",
        "lang": lang or "",
        "subtype": subtype or "",
        "sub_suffix": normalize_subtitle_suffix(sub_suffix),
        "ext": ext or "",
    }

    seen_keys = set()
    if main_key:
        seen_keys.add(main_key)

    def dedupe_text(value: Optional[str]) -> str:
        value_clean = normalize_spaces(value or "")
        if not value_clean:
            return ""
        value_key = normalize_title_key(value_clean)
        if value_key and value_key in seen_keys:
            return ""
        if value_key:
            seen_keys.add(value_key)
        return value_clean

    values["original_title"] = dedupe_text(original_title)
    values["title_local"] = dedupe_text(title_local or series_title)

    for code, value in (localized_titles or {}).items():
        field_name = f"title_{normalize_lang_field_code(code)}"
        if not LANG_FIELD_PATTERN.fullmatch(field_name):
            continue
        values[field_name] = dedupe_text(value)

    return values


def render_series_folder_name(metadata_profile: str, series_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], localized_titles: Optional[Dict[str, str]] = None, title_local: Optional[str] = None) -> str:
    template = get_profile_templates(metadata_profile)["series"]
    return render_template(template, build_template_values(series_title, original_title, ids, year, localized_titles=localized_titles, title_local=title_local), False)


def render_season_folder_name(metadata_profile: str, series_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], season: int, localized_titles: Optional[Dict[str, str]] = None, title_local: Optional[str] = None) -> str:
    template = get_profile_templates(metadata_profile)["season"]
    return render_template(template, build_template_values(series_title, original_title, ids, year, localized_titles=localized_titles, title_local=title_local, season=season), False)


def render_episode_file_name(metadata_profile: str, series_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], season: int, episode: int, ext: str, localized_titles: Optional[Dict[str, str]] = None, title_local: Optional[str] = None) -> str:
    template = get_profile_templates(metadata_profile)["episode"]
    return render_template(template, build_template_values(series_title, original_title, ids, year, localized_titles=localized_titles, title_local=title_local, season=season, episode=episode, ext=ext.lower()), True)


def render_subtitle_file_name(metadata_profile: str, series_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], season: int, episode: int, ext: str, lang: Optional[str], subtype: Optional[str], sub_suffix: Optional[str] = None, localized_titles: Optional[Dict[str, str]] = None, title_local: Optional[str] = None) -> str:
    template = get_profile_templates(metadata_profile)["subtitle"]
    return render_template(
        template,
        build_template_values(
            series_title,
            original_title,
            ids,
            year,
            localized_titles=localized_titles,
            title_local=title_local,
            season=season,
            episode=episode,
            lang=lang,
            subtype=subtype,
            sub_suffix=sub_suffix,
            ext=ext.lower(),
        ),
        True,
    )


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
            groups[series_dir] = SeriesGroup(source_dir=series_dir, guessed_title=guessed_title, ids=ids, season_hint=season_hint)
        stem = path.stem
        season, episode = detect_episode_info(stem, season_hint)
        if season is None and path.parent == series_dir:
            season = 1
        lang = subtype = None
        if kind == "sub":
            lang, subtype = detect_sub_meta(stem, path.parent.name)
        groups[series_dir].files.append(FileEntry(path=path, relpath=rel, kind=kind, season=season, episode=episode, lang=lang, subtype=subtype, sub_suffix=None, ext=ext))
    return groups


def resolve_series_ru(group: SeriesGroup, kp: KPClient, tmdb: TMDbClient, cache: dict, lang_priority: str, mode: str) -> Tuple[str, MediaIDs, Optional[str], Optional[str], Dict[str, str]]:
    cache_key = f"ru::{group.guessed_title.lower()}"
    if cache_key in cache:
        item = cache[cache_key]
        return item["title"], MediaIDs(item.get("kp"), item.get("tt"), item.get("tmdb")), item.get("year"), item.get("original_title"), item.get("localized_titles") or {}
    if group.ids.kp:
        title = group.guessed_title
        ids = MediaIDs(kp=group.ids.kp, tt=group.ids.tt, tmdb=group.ids.tmdb)
        year = None
        original_title = None
        data = kp.try_details(int(ids.kp))
        localized_titles = {}
        if data:
            year = safe_year(data.get("year"))
            title = choose_display_title(data, {}, title, lang_priority)
            original_title = choose_original_title(data, {})
            ids.tt = data.get("imdbId") or ids.tt
            localized_titles = localized_titles_from_kp(data, {})
        ids = enrich_from_tmdb_ru(tmdb, title, original_title, year, ids)
        localized_titles = merge_localized_titles(localized_titles, fetch_tmdb_localized_titles(tmdb, ids.tmdb, ["ru-RU", "en-US"]))
        cache[cache_key] = {"title": title, "kp": ids.kp, "tt": ids.tt, "tmdb": ids.tmdb, "year": year, "original_title": original_title, "localized_titles": localized_titles}
        return title, ids, year, original_title, localized_titles
    chosen = interactive_search_loop_kp(group, kp, group.guessed_title, lang_priority, mode)
    if not chosen:
        ids = MediaIDs(group.ids.kp, group.ids.tt, group.ids.tmdb)
        title = group.guessed_title
        year = None
        original_title = None
        ids = enrich_from_tmdb_ru(tmdb, title, original_title, year, ids)
        localized_titles = fetch_tmdb_localized_titles(tmdb, ids.tmdb, ["ru-RU", "en-US"])
        return title, ids, year, original_title, localized_titles
    kp_id = str(chosen["filmId"])
    details = chosen.get("_details") or kp.try_details(int(kp_id)) or {}
    title = choose_display_title(details, chosen, group.guessed_title, lang_priority)
    original_title = choose_original_title(details, chosen)
    ids = MediaIDs(kp=kp_id, tt=details.get("imdbId") or None, tmdb=group.ids.tmdb)
    year = safe_year(details.get("year"))
    ids = enrich_from_tmdb_ru(tmdb, title, original_title, year, ids)
    localized_titles = merge_localized_titles(localized_titles_from_kp(details, chosen), fetch_tmdb_localized_titles(tmdb, ids.tmdb, ["ru-RU", "en-US"]))
    cache[cache_key] = {"title": title, "kp": ids.kp, "tt": ids.tt, "tmdb": ids.tmdb, "year": year, "original_title": original_title, "localized_titles": localized_titles}
    return title, ids, year, original_title, localized_titles


def resolve_series_intl(group: SeriesGroup, tmdb: TMDbClient, cache: dict, lang_priority: str, mode: str) -> Tuple[str, MediaIDs, Optional[str], Optional[str], Dict[str, str]]:
    cache_key = f"intl::{group.guessed_title.lower()}"
    if cache_key in cache:
        item = cache[cache_key]
        return item["title"], MediaIDs(item.get("kp"), item.get("tt"), item.get("tmdb")), item.get("year"), item.get("original_title"), item.get("localized_titles") or {}
    if group.ids.tmdb:
        ids = MediaIDs(kp=None, tt=group.ids.tt, tmdb=group.ids.tmdb)
        details = tmdb.try_tv_details(int(ids.tmdb), language="en-US") or {}
        ext = tmdb.try_tv_external_ids(int(ids.tmdb)) or {}
        title = choose_tmdb_display_title(details, lang_priority, group.guessed_title)
        original_title = details.get("original_name") or None
        year = tmdb_result_year(details)
        ids.tt = ext.get("imdb_id") or ids.tt
        localized_titles = merge_localized_titles(localized_titles_from_tmdb_details(details, "en-US"), fetch_tmdb_localized_titles(tmdb, ids.tmdb, ["en-US", "ru-RU"]))
        cache[cache_key] = {"title": title, "kp": ids.kp, "tt": ids.tt, "tmdb": ids.tmdb, "year": year, "original_title": original_title, "localized_titles": localized_titles}
        return title, ids, year, original_title, localized_titles
    chosen = interactive_search_loop_tmdb(group, tmdb, group.guessed_title, lang_priority, mode)
    if not chosen:
        return group.guessed_title, MediaIDs(group.ids.kp, group.ids.tt, group.ids.tmdb), None, None, {}
    tmdb_id = str(chosen.get("id"))
    details = chosen
    ext = details.get("_external_ids")
    if ext is None:
        ext = tmdb.try_tv_external_ids(int(tmdb_id)) or {}
    title = choose_tmdb_display_title(details, lang_priority, group.guessed_title)
    original_title = details.get("original_name") or None
    year = tmdb_result_year(details)
    ids = MediaIDs(kp=None, tt=ext.get("imdb_id") or group.ids.tt, tmdb=tmdb_id)
    localized_titles = merge_localized_titles(localized_titles_from_tmdb_details(details, "en-US"), fetch_tmdb_localized_titles(tmdb, ids.tmdb, ["en-US", "ru-RU"]))
    cache[cache_key] = {"title": title, "kp": ids.kp, "tt": ids.tt, "tmdb": ids.tmdb, "year": year, "original_title": original_title, "localized_titles": localized_titles}
    return title, ids, year, original_title, localized_titles


def resolve_series(group: SeriesGroup, kp: KPClient, tmdb: TMDbClient, cache: dict, metadata_profile: str, lang_priority: str, mode: str) -> Tuple[str, MediaIDs, Optional[str], Optional[str], Dict[str, str]]:
    if metadata_profile == "intl":
        return resolve_series_intl(group, tmdb, cache, lang_priority, mode)
    return resolve_series_ru(group, kp, tmdb, cache, lang_priority, mode)


def interactive_search_loop_kp(group: SeriesGroup, kp: KPClient, initial_query: str, lang_priority: str, mode: str) -> Optional[dict]:
    query = initial_query
    while True:
        print()
        print(f"Source dir   : {group.source_dir.name}")
        print(f"Search query : {query}")
        try:
            results = kp.search(query)
        except Exception as e:
            print(f"WARNING: KP search failed for {query}: {e}")
            results = []
        results = filter_series_candidates(results)
        results = sort_candidates(results, expected_type="TV_SERIES")
        top = results[:10]
        if mode == "smart" and len(top) == 1 and candidate_matches_lang(top[0], lang_priority):
            item = top[0]
            name = item.get("nameRu") or item.get("nameEn") or item.get("nameOriginal") or "<unnamed>"
            year = item.get("year") or "?"
            print(f"Auto-selected: {name} ({year}) [{item.get('type')}] [kp{item.get('filmId')}]")
            return item
        if not top:
            print()
            print("No matches found.")
            print("0) exit")
            print("1) skip")
            print("2) retry same search")
            print("Any other input = new search text or kp id")
            next_action = safe_input("> ").strip()
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
        print()
        print(f"Found matches for: {query}")
        for idx, item in enumerate(top, start=1):
            kp_id = item.get("filmId")
            name = item.get("nameRu") or item.get("nameEn") or "<unnamed>"
            year = item.get("year") or "?"
            typ = item.get("type") or "?"
            print(f"{idx}) {name} ({year}) [{typ}] [kp{kp_id}]")
        print("0) exit")
        print("98) skip")
        print("99) retry same search")
        print("Any other input = new search text or kp id")
        if len(top) == 1:
            print("Enter = choose 1")
        print()
        while True:
            choice = safe_input("Choose: ").strip()
            if choice == "" and len(top) == 1:
                return top[0]
            if choice == "98":
                return None
            if choice == "99":
                break
            if choice.isdigit():
                n = int(choice)
                if 1 <= n <= len(top):
                    return top[n - 1]
            kind, value = parse_manual_input(choice)
            if kind == "kp":
                item = try_pick_by_kp_id(kp, value)
                if item:
                    name = item.get("nameRu") or item.get("nameEn") or item.get("nameOriginal") or "<unnamed>"
                    year = item.get("year") or "?"
                    print(f"Selected by kp id: {name} ({year}) [{item.get('type')}] [kp{item.get('filmId')}]")
                    return item
                print(f"KP id not found or not a series: {value}")
                continue
            if value:
                query = value
                break
            print("Invalid choice")


def find_paired_subtitles(group: SeriesGroup, video_entry: FileEntry, used_subs: Set[Path]) -> List[FileEntry]:
    matches: List[FileEntry] = []
    for fe in group.files:
        if fe.kind != "sub" or fe.path in used_subs or fe.path.parent != video_entry.path.parent:
            continue
        suffix = extract_subtitle_suffix(fe.path.stem, video_entry.path.stem)
        if suffix is None:
            continue
        fe.sub_suffix = suffix
        matches.append(fe)
    return sorted(matches, key=lambda x: x.path.name.lower())


def build_fallback_ops(group: SeriesGroup, series_target_dir: Path, resolved_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], existing_ops: List[PlannedOp], metadata_profile: str) -> List[PlannedOp]:
    fallback_ops: List[PlannedOp] = []
    used_targets: set[Path] = {op.dst for op in existing_ops}
    used_subs: set[Path] = set()
    fallback_candidates: Dict[Tuple[Path, int], List[FileEntry]] = defaultdict(list)
    for fe in group.files:
        if fe.kind != "video" or fe.episode is not None:
            continue
        season = fe.season or detect_season_from_dir(fe.path.parent.name)
        if season is None and fe.path.parent == group.source_dir:
            season = 1
        if season is None:
            continue
        fallback_candidates[(fe.path.parent, season)].append(fe)
    for (src_parent, season), files in sorted(fallback_candidates.items(), key=lambda item: (str(item[0][0]).lower(), item[0][1])):
        files_sorted = sorted(files, key=lambda f: f.path.name.lower())
        next_episode = 1
        for fe in files_sorted:
            season_dir = series_target_dir / render_season_folder_name(metadata_profile, resolved_title, original_title, ids, year, season, localized_titles=group.localized_titles, title_local=resolved_title)
            while True:
                new_video_name = render_episode_file_name(metadata_profile, resolved_title, original_title, ids, year, season, next_episode, fe.ext, localized_titles=group.localized_titles, title_local=resolved_title)
                video_target = season_dir / new_video_name
                if video_target not in used_targets:
                    break
                next_episode += 1
            if fe.path != video_target:
                fallback_ops.append(PlannedOp(fe.path, video_target, "move", "fallback sorted source files"))
                used_targets.add(video_target)
            for sub in find_paired_subtitles(group, fe, used_subs):
                new_sub_name = render_subtitle_file_name(metadata_profile, resolved_title, original_title, ids, year, season, next_episode, sub.ext, sub.lang, sub.subtype, sub.sub_suffix, localized_titles=group.localized_titles, title_local=resolved_title)
                sub_target = season_dir / new_sub_name
                if sub_target in used_targets:
                    continue
                if sub.path != sub_target:
                    fallback_ops.append(PlannedOp(sub.path, sub_target, "move", "fallback paired subtitle"))
                    used_targets.add(sub_target)
                    used_subs.add(sub.path)
            next_episode += 1
    return fallback_ops


def plan_group(root: Path, group: SeriesGroup, resolved_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], metadata_profile: str) -> List[PlannedOp]:
    ops: List[PlannedOp] = []
    series_folder = render_series_folder_name(metadata_profile, resolved_title, original_title, ids, year, localized_titles=group.localized_titles, title_local=resolved_title)
    series_target_dir = root / series_folder
    planned_media_ops = 0
    for fe in group.files:
        if fe.kind not in {"video", "sub"} or not fe.season or not fe.episode:
            continue
        season_dir = series_target_dir / render_season_folder_name(metadata_profile, resolved_title, original_title, ids, year, fe.season, localized_titles=group.localized_titles, title_local=resolved_title)
        if fe.kind == "video":
            new_name = render_episode_file_name(metadata_profile, resolved_title, original_title, ids, year, fe.season, fe.episode, fe.ext, localized_titles=group.localized_titles, title_local=resolved_title)
        else:
            if fe.sub_suffix is None:
                video_stem = find_matching_video_stem(group, fe)
                if video_stem:
                    fe.sub_suffix = extract_subtitle_suffix(fe.path.stem, video_stem)
                if fe.sub_suffix is None:
                    fe.sub_suffix = ""
            new_name = render_subtitle_file_name(metadata_profile, resolved_title, original_title, ids, year, fe.season, fe.episode, fe.ext, fe.lang, fe.subtype, fe.sub_suffix, localized_titles=group.localized_titles, title_local=resolved_title)
        target = season_dir / new_name
        if fe.path != target:
            ops.append(PlannedOp(fe.path, target, "move", "normalize episode/subtitle placement"))
            planned_media_ops += 1
    fallback_ops = build_fallback_ops(group, series_target_dir, resolved_title, original_title, ids, year, ops, metadata_profile)
    ops.extend(fallback_ops)
    planned_media_ops += len(fallback_ops)
    if planned_media_ops == 0 and group.source_dir != series_target_dir:
        ops.append(PlannedOp(group.source_dir, series_target_dir, "rename", "normalize series folder"))
    return ops


def plan_series_folder_update(root: Path, group: SeriesGroup, resolved_title: str, original_title: Optional[str], ids: MediaIDs, year: Optional[str], metadata_profile: str) -> List[PlannedOp]:
    desired = root / render_series_folder_name(metadata_profile, resolved_title, original_title, ids, year, localized_titles=group.localized_titles, title_local=resolved_title)
    if group.source_dir == desired:
        return []
    return [PlannedOp(group.source_dir, desired, "rename", "update series folder metadata")]


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


def build_tree_preview_detailed(root: Path, ops: List[PlannedOp], source_series_dir: Path) -> Dict[str, Dict[str, List[Tuple[str, str, str]]]]:
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
    fallback_ops = [op for op in ops if op.reason in {"fallback sorted source files", "fallback paired subtitle"}]
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
    print(f"Source dir   : {group.source_dir.name}")
    print(f"Resolved     : {resolved_title}")
    print(f"IDs          : kp={ids.kp} tmdb={ids.tmdb} tt={ids.tt}")
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


def confirm_series_folder_update(group: SeriesGroup, resolved_title: str, ids: MediaIDs, current_dir: Path, new_dir: Path) -> str:
    print()
    print("------------------------------------------------------------")
    print(f"Source dir   : {current_dir.name}")
    print(f"Resolved     : {resolved_title}")
    print(f"IDs          : kp={ids.kp} tmdb={ids.tmdb} tt={ids.tt}")
    if current_dir == new_dir:
        print("Already normalized: no moves needed")
    else:
        print("Series folder update:")
        print(f"  {current_dir.name}")
        print(f"    -> {new_dir.name}")
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


_LOG_WRITE_WARNING_SHOWN = False


def log_line(log_path: Path, message: str) -> None:
    global _LOG_WRITE_WARNING_SHOWN
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message + "\n")
    except KeyboardInterrupt:
        raise
    except OSError as e:
        if not _LOG_WRITE_WARNING_SHOWN:
            _LOG_WRITE_WARNING_SHOWN = True
            print(f"WARNING: unable to write operations log: {e}", file=sys.stderr)


def _relative_under(base: Path, path: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except Exception:
        return path.name


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


def apply_ops(ops: List[PlannedOp], log_path: Path, dry_run: bool, source_series_dir: Path, root: Path) -> Tuple[int, int, Path]:
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
                else:
                    op.dst.parent.mkdir(parents=True, exist_ok=True)
                    op.src.rename(op.dst)
                    log_line(log_path, f"{op_word:<6} {src_rel}  =>  {dst_rel}")
                applied += 1
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
    dirs = sorted([p for p in start_dir.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True)
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


def try_save_cache(cache_path: Path, cache: dict) -> Optional[str]:
    try:
        save_cache(cache_path, cache)
        return None
    except KeyboardInterrupt:
        raise
    except OSError as e:
        return str(e)


def load_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def validate_tmdb_bearer_or_exit() -> Optional[str]:
    token = str(DEFAULT_TMDB_BEARER or "").strip()
    if not token or token == "INSERT_YOUR_TMDB_BEARER_TOKEN_HERE":
        return "TMDb bearer token is not configured. Set DEFAULT_TMDB_BEARER in the script settings."
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize TV series tree. Applies changes immediately per series; use --dry-run to preview only.",
    )
    parser.add_argument("root", nargs="?", help="Root path to Serials")
    parser.add_argument("--cache", default=DEFAULT_CACHE_FILE, help="Cache JSON path")
    parser.add_argument("--ops-log", default=DEFAULT_OPS_LOG, help="Operations log file path")
    parser.add_argument("--metadata-profile", choices=["ru", "intl"], default=DEFAULT_METADATA_PROFILE, help="ru: kp->tmdb, imdb from kp or tmdb; intl: tmdb->imdb")
    parser.add_argument("--mode", choices=["smart", "manual"], default=DEFAULT_MODE, help="smart: auto-accept one fitting candidate; manual: always confirm")
    parser.add_argument("--dry-first", action="store_true", help="Show resulting tree or folder update preview for each series and ask confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Do not modify filesystem; only print/log planned operations")
    parser.add_argument("--update-series-folders", action="store_true", help="Only update existing root series folder names using fresh metadata; do not move episode/subtitle files")
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
    tmdb_bearer_error = validate_tmdb_bearer_or_exit()
    if tmdb_bearer_error:
        print(f"ERROR: {tmdb_bearer_error}")
        return 1
    kp = KPClient(DEFAULT_KP_API_KEY)
    tmdb = TMDbClient(DEFAULT_TMDB_BEARER)
    cache = load_cache(cache_path)
    groups = scan_tree(root)
    total_applied = 0
    total_removed_dirs = 0
    total_kept_dirs = 0
    total_errors = 0
    processed_groups = 0
    log_line(ops_log_path, "============================================================")
    log_line(ops_log_path, f"START root={root} dry_run={args.dry_run} metadata_profile={args.metadata_profile} update_series_folders={args.update_series_folders}")
    try:
        print(f"Found groups: {len(groups)}")
        print()
        for group in sorted(groups.values(), key=lambda g: str(g.source_dir).lower()):
            while True:
                print("============================================================")
                print(f"Source dir   : {group.source_dir.relative_to(root).as_posix() if group.source_dir != root else group.source_dir.name}")
                print(f"Guessed title: {group.guessed_title}")
                print(f"Files        : {len(group.files)}")
                if group.ids.kp or group.ids.tmdb or group.ids.tt:
                    print(f"Existing IDs : kp={group.ids.kp} tmdb={group.ids.tmdb} tt={group.ids.tt}")
                lang_priority = effective_lang_priority(args.metadata_profile)
                resolved_title, ids, year, original_title, localized_titles = resolve_series(
                    group=group,
                    kp=kp,
                    tmdb=tmdb,
                    cache=cache,
                    metadata_profile=args.metadata_profile,
                    lang_priority=lang_priority,
                    mode=args.mode,
                )
                group.resolved_title = resolved_title
                group.ids = ids
                group.resolved_year = year
                group.resolved_original_title = original_title
                group.localized_titles = localized_titles
                print(f"Resolved     : {resolved_title}")
                print(f"Original     : {original_title}")
                print(f"Year         : {year}")
                print(f"IDs          : kp={ids.kp} tmdb={ids.tmdb} tt={ids.tt}")
                if args.update_series_folders:
                    ops = plan_series_folder_update(root, group, resolved_title, original_title, ids, year, args.metadata_profile)
                    desired_dir = root / render_series_folder_name(args.metadata_profile, resolved_title, original_title, ids, year, localized_titles=group.localized_titles, title_local=resolved_title)
                    if args.dry_first:
                        decision = confirm_series_folder_update(group, resolved_title, ids, group.source_dir, desired_dir)
                        if decision == "3":
                            cache.pop(f"{args.metadata_profile}::{group.guessed_title.lower()}", None)
                            continue
                        if decision in {"2", "4"}:
                            processed_groups += 1
                            break
                    applied, errors, _target_series_dir = apply_ops(ops, ops_log_path, args.dry_run, group.source_dir, root)
                    total_applied += applied
                    total_errors += errors
                    processed_groups += 1
                    log_line(ops_log_path, f"SUMMARY ops={applied} removed_dirs=0 kept_dirs=0 errors={errors}")
                    log_line(ops_log_path, "")
                    print_series_summary(applied, errors, 0, 0, args.dry_run)
                    if applied == 0 and errors == 0:
                        print("Already normalized: no moves needed")
                    break
                ops = plan_group(root, group, resolved_title, original_title, ids, year, args.metadata_profile)
                if not args.dry_first:
                    applied, errors, _target_series_dir = apply_ops(ops, ops_log_path, args.dry_run, group.source_dir, root)
                    removed_dirs, kept_dirs, prune_errors = prune_empty_dirs(group.source_dir, root, ops_log_path, args.dry_run)
                    total_applied += applied
                    total_removed_dirs += removed_dirs
                    total_kept_dirs += kept_dirs
                    total_errors += errors + prune_errors
                    processed_groups += 1
                    log_line(ops_log_path, f"SUMMARY ops={applied} removed_dirs={removed_dirs} kept_dirs={kept_dirs} errors={errors + prune_errors}")
                    log_line(ops_log_path, "")
                    print_series_summary(applied, errors + prune_errors, removed_dirs, kept_dirs, args.dry_run)
                    if applied == 0 and errors == 0 and removed_dirs == 0:
                        print("Already normalized: no moves needed")
                    if kept_dirs:
                        print("Note: some source directories were kept because they are not empty.")
                    break
                decision = confirm_series_plan(root, group, resolved_title, ids, ops)
                if decision == "1":
                    applied, errors, _target_series_dir = apply_ops(ops, ops_log_path, args.dry_run, group.source_dir, root)
                    removed_dirs, kept_dirs, prune_errors = prune_empty_dirs(group.source_dir, root, ops_log_path, args.dry_run)
                    total_applied += applied
                    total_removed_dirs += removed_dirs
                    total_kept_dirs += kept_dirs
                    total_errors += errors + prune_errors
                    processed_groups += 1
                    log_line(ops_log_path, f"SUMMARY ops={applied} removed_dirs={removed_dirs} kept_dirs={kept_dirs} errors={errors + prune_errors}")
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
                    cache.pop(f"{args.metadata_profile}::{group.guessed_title.lower()}", None)
                    continue
    except (UserAbort, KeyboardInterrupt):
        print()
        print("Exit requested. Stopping cleanly.")
    finally:
        cache_save_error = try_save_cache(cache_path, cache)
        try:
            log_line(ops_log_path, f"END processed_groups={processed_groups} applied={total_applied} removed_dirs={total_removed_dirs} kept_dirs={total_kept_dirs} errors={total_errors}")
        except KeyboardInterrupt:
            print()
            print("Exit requested while finalizing log.")
            cache_save_error = cache_save_error or "interrupted while finalizing log"
    print()
    if cache_save_error:
        print(f"WARNING: cache was not saved: {cache_save_error}")
    else:
        print(f"Cache saved: {cache_path}")
    print(f"Operations log: {ops_log_path}")
    print("Dry-run complete." if args.dry_run else "Apply complete.")
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
