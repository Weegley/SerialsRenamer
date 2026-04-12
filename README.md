# SerialsRenamer

Русская версия: [README.ru.md](README.ru.md)

Production-oriented Python script for normalizing TV series folders and episode files.

It helps reorganize messy TV series collections into a predictable structure:

```text
Series Title (Original Title) (Year) [tmdbid-123456][imdbid-tt1234567]/
└── Season 01/
    ├── S01E01.mkv
    ├── S01E01.full.rus.srt
    ├── S01E02.mkv
    └── ...
```

## API keys and credentials

This script uses:

- [**Kinopoisk Api Unofficial**](https://kinopoiskapiunofficial.tech/)
- [**TMDb**](https://www.themoviedb.org/)

### Kinopoisk Api Unofficial

The script currently contains a bundled shared Kinopoisk Api Unofficial key in the source code for quick testing.

This is convenient for trying the script, but for regular use it is **strongly recommended** to replace it with **your own Kinopoisk Api Unofficial key**.

Why:

- shared keys can hit rate limits
- shared keys may stop working unexpectedly
- your own key is more reliable and predictable

### TMDb

For TMDb, you should **provide your own TMDb bearer token** in the script settings.

This is effectively required for real usage.

Why:

- TMDb is a core part of the current metadata pipeline
- it is used directly in the `intl` profile
- it is used for enrichment, external IDs, and localized titles in the `ru` profile
- multilingual title fields depend on TMDb translations

In short:

- bundled Kinopoisk key is acceptable for quick testing
- your own Kinopoisk key is strongly recommended
- your own TMDb bearer token is required

---

The script is designed to be interactive, conservative, and filesystem-safe:

- it can preview changes before applying them
- it asks for confirmation per series
- it avoids aggressive guessing in ambiguous cases
- it keeps non-empty directories instead of deleting them blindly
- it uses fallback logic when filenames are messy but still sortable

---

## Features

### Metadata profiles

The script supports two metadata profiles:

- `ru`
- `intl`

#### `ru` profile

- primary source: Kinopoisk
- enrichment: TMDb
- IMDb id: from Kinopoisk when available, otherwise from TMDb
- primary title is usually Russian

Resolution flow:

```text
kp -> tmdb ; imdb = kp if present else tmdb
```

#### `intl` profile

- primary source: TMDb
- IMDb id: from TMDb
- Kinopoisk is not used as the primary metadata source
- primary title is usually English / international

Resolution flow:

```text
tmdb -> imdb
```

### Canonical ID formats

The script always renders IDs in canonical Jellyfin-friendly form:

- `[kp-1234567]`
- `[tmdbid-123456]`
- `[imdbid-tt1234567]`

Older input forms are still recognized during parsing.

Supported incoming variants include:

- Kinopoisk:
  - `[kp1234567]`
  - `[kp-1234567]`

- TMDb:
  - `[tmdb12345]`
  - `[tmdb-12345]`
  - `[tmdbid-12345]`

- IMDb:
  - `[tt1234567]`
  - `[imdbidtt1234567]`
  - `[imdbid=tt1234567]`
  - `[imdbid-tt1234567]`

### Series recognition

- searches series via Kinopoisk or TMDb depending on profile
- supports direct `kp` id input during manual Kinopoisk selection
- supports direct `tmdb` id input during manual TMDb selection
- reuses IDs already embedded in folder names
- supports tolerant parsing of old and new ID formats

### Folder normalization

- normalizes the main series folder name using templates
- normalizes season folder names
- normalizes episode and subtitle filenames
- can rename already identified but badly named source folders
- can run in safe metadata-only update mode for already normalized series roots

### Update mode

`--update-series-folders`

This mode:

- scans already normalized root series folders
- refreshes missing metadata and IDs
- renames only the root series folder when needed
- does **not** move episode or subtitle files

This is a safe metadata update mode.

### Episode recognition

Recognizes common episode patterns such as:

- `S01E01`
- `S1E1`
- `S01.E01`
- `S01-E01`
- `S01_E01`
- `1x01`
- `01x01`
- `1x1`
- `01x1`
- `E01` when season is known
- leading number, for example:
  - `01 Episode title...`
  - `01.Series.Name...`

### Season recognition

Recognizes common season folder formats such as:

- `Season 1`
- `Season 01`
- `1 season`
- `S1`
- `S01`
- folder names ending in season number, for example:
  - `sopranos1`
  - `sopranos6`

Also supports a fallback assumption:

- if files are placed directly in the series root and season is unknown,
  they are treated as `Season 01`

### Subtitle support

Supports subtitle files:

- `.srt`
- `.ass`
- `.ssa`
- `.sub`

Detects subtitle metadata from filenames and folders.

Languages:

- `ru`, `rus`, `russian` → `rus`
- `en`, `eng`, `english` → `eng`

Subtype:

- `forced`
- `full`
- `sdh`

### Safe fallback logic

When filenames do not explicitly contain a recognizable episode number:

- video files are assigned by sorted order within their source folder
- numbering starts from `E01`
- numbering skips already occupied targets
- paired subtitles with the same normalized stem are moved together with the video

This makes the script resilient against badly named releases without trying to over-guess weird naming schemes.

### Conservative behavior

- ambiguous subtitle-only files are not guessed aggressively
- non-empty directories are not deleted
- already normalized series are left untouched
- `Ctrl+C` or menu option `0` exits cleanly

---

## Default resulting structure

Default output layout:

### `ru` profile

```text
{title} ({original_title}) ({year}) [kp-{kp}][tmdbid-{tmdb}][imdbid-{tt}]/
└── Season {season:02d}/
    ├── S{season:02d}E{episode:02d}{ext}
    └── S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}
```

### `intl` profile

```text
{title} ({original_title}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]/
└── Season {season:02d}/
    ├── S{season:02d}E{episode:02d}{ext}
    └── S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}
```

Example:

```text
Блудливая Калифорния (Californication) (2007) [kp-394375][tmdbid-1215][imdbid-tt0904208]/
└── Season 01/
    ├── S01E01.mkv
    ├── S01E02.mkv
    ├── S01E02.eng.srt
    └── S01E02.rus.srt
```

---

## Installation

### Requirements

- Python 3.10+
- internet access for Kinopoisk and TMDb requests

No external Python dependencies are required.

---

## Usage

### Basic run

```bash
python SerialsRenamer.py /path/to/Serials
```

### Preview changes only

```bash
python SerialsRenamer.py /path/to/Serials --dry-run
```

### Interactive preview before each series

```bash
python SerialsRenamer.py /path/to/Serials --dry-first
```

### Use international metadata profile

```bash
python SerialsRenamer.py /path/to/Serials --metadata-profile intl
```

### Always confirm search results manually

```bash
python SerialsRenamer.py /path/to/Serials --mode manual
```

### Update already normalized series root folders only

```bash
python SerialsRenamer.py /path/to/Serials --update-series-folders --dry-run
```

---

## Command line options

```text
root                    Root path to Serials
--cache                 Cache json path
--ops-log               Operations log file path
--metadata-profile      ru | intl
--mode                  smart | manual
--dry-first             Show resulting tree or folder update preview for each series and ask confirmation
--dry-run               Do not modify filesystem; only print/log planned operations
--update-series-folders Only update existing root series folder names using fresh metadata
```

---

## Interactive workflow

For each detected series, the script:

1. scans files
2. tries to infer title from folder structure
3. resolves series metadata using the active profile
4. builds a rename and move plan
5. optionally shows preview
6. applies changes after confirmation

### Search result menu

Typical options:

- `0` — exit the whole script
- `98` — skip current search result selection
- `99` — retry same search
- `Enter` — accept the only result, when there is exactly one
- any other text — new search query or direct `kp` / `tmdb` id

Examples of valid manual input:

- `kp1234567`
- `1234567`
- `tmdb1215`
- `The Sopranos`

---

## Preview mode

With `--dry-first`, the script shows a per-series preview like this:

```text
Planned tree:
  Блудливая Калифорния (Californication) (2007) [kp-394375][tmdbid-1215][imdbid-tt0904208]/
    [Season 01] -> [Season 01]
      S01E01.mkv -> S01E01.mkv
      S01E02.mkv -> S01E02.mkv
      ...
```

Fallback assignments are displayed separately:

```text
Fallback assignments:
  sopranos6/Klan_Soprano_VI_13_DVDRip.avi -> Season 06/S06E13.avi
  sopranos6/Klan_Soprano_VI_14_DVDRip.avi -> Season 06/S06E14.avi
  ...
```

If nothing needs changing:

```text
Already normalized: no moves needed
```

---

## Logging

The script writes a human-readable operations log.

Default log file:

```text
SerialsRenamer.operations.log
```

Typical entries:

```text
============================================================
SERIES  Sopranos(full version)  ->  Блудливая Калифорния (Californication) (2007) [kp-394375][tmdbid-1215][imdbid-tt0904208]

MOVE   sopranos1/The Sopranos [S01E01, Goblin].avi  =>  Season 01/S01E01.avi
PAIRSB plevako/01 Плевако .2023.WEB-DLRip.Files-x.srt  =>  Season 01/S01E01.rus.srt
FALLBK sopranos6/Klan_Soprano_VI_13_DVDRip.avi  =>  Season 06/S06E13.avi
DELDIR old_subfolder
KEEPDIR leftovers  ::  not empty
SUMMARY ops=18 removed_dirs=5 kept_dirs=1 errors=0
```

### Operation types

- `RENAME` — rename top-level series folder
- `MOVE` — normal recognized move
- `FALLBK` — fallback move by sorted video list
- `PAIRSB` — subtitle moved together with fallback-paired video
- `DELDIR` — removed empty directory
- `KEEPDIR` — directory left in place because it is not empty
- `ERROR` — operation failed

---

## Cache

The script caches resolved metadata to reduce repeated manual work.

Default cache file:

```text
.series_rename_cache.json
```

Cached data may include:

- chosen title
- Kinopoisk ID
- TMDb ID
- IMDb ID
- year
- original title
- localized titles

When testing template or localization changes, it is recommended to use a fresh cache file or delete the old one.

---

## Naming templates

The script uses templates for the final structure.

### Default templates

```python
RU_SERIES_FOLDER_TEMPLATE = "{title} ({original_title}) ({year}) [kp-{kp}][tmdbid-{tmdb}][imdbid-{tt}]"
INTL_SERIES_FOLDER_TEMPLATE = "{title} ({original_title}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"
RU_SEASON_FOLDER_TEMPLATE = "Season {season:02d}"
INTL_SEASON_FOLDER_TEMPLATE = "Season {season:02d}"
RU_EPISODE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{ext}"
INTL_EPISODE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{ext}"
RU_SUBTITLE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}"
INTL_SUBTITLE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}"
```

### Available template fields

Primary fields:

- `{title}` — primary display title for the active metadata profile
- `{original_title}` — original or provider-original title
- `{title_local}` — localized title for the active profile context

Localized title fields:

- `{title_ru}`
- `{title_en}`
- `{title_de}`
- `{title_fr}`
- `{title_ko}`
- other `title_XX` fields, including regional variants such as `{title_pt_BR}` or `{title_zh_CN}`

Other fields:

- `{kp}` — Kinopoisk ID without prefix
- `{tmdb}` — TMDb ID without prefix
- `{tt}` — IMDb ID including `tt`
- `{year}` — release year
- `{season}` — season number
- `{episode}` — episode number
- `{lang}` — subtitle language
- `{subtype}` — subtitle subtype
- `{ext}` — file extension including dot

### Deduplication rules

`{title}` is always the primary field.

Before rendering:

- if `{original_title}` is equal to `{title}`, it is cleared
- if any `{title_XX}` is equal to `{title}`, it is cleared
- if secondary fields duplicate each other, only the first unique value is kept and later duplicates are cleared

Deduplication uses normalized title keys:

- case-insensitive
- repeated spaces ignored
- separator and punctuation differences normalized

### Example custom templates

Conservative `intl` variant with an extra Russian title:

```python
INTL_SERIES_FOLDER_TEMPLATE = "{title} ({title_ru}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"
```

Verbose multilingual example:

```python
INTL_SERIES_FOLDER_TEMPLATE = "{title} ({original_title}) ({title_ru}) ({title_fr}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"
```

The script validates template fields on startup and fails fast if a template contains an unknown field.

---

## Safety rules

The script is intentionally conservative.

### It will do

- rename and reorganize recognized files
- use fallback only for sortable unknown video files
- move paired subtitles together with fallback video
- remove empty source directories
- keep non-empty directories untouched
- update only root series folders in `--update-series-folders` mode

### It will not do

- blindly guess arbitrary subtitle-only files
- delete non-empty directories
- overwrite existing destination files
- aggressively parse every weird naming fantasy found in the wild

---

## Typical use cases

### 1. Messy season folders

```text
Sopranos(full version)/
├── sopranos1/
├── sopranos2/
├── sopranos3/
└── ...
```

Becomes:

```text
Сопрано (The Sopranos) (1999) [kp-79848][tmdbid-1398][imdbid-tt0141842]/
├── Season 01/
├── Season 02/
├── Season 03/
└── ...
```

### 2. Files in series root

```text
Плевако/
├── 01 Плевако .2023.WEB-DLRip.Files-x.avi
├── 02 Плевако .2023.WEB-DLRip.Files-x.avi
└── ...
```

Becomes:

```text
Плевако (Plevako) (2023) [kp-4470538][tmdbid-000000][imdbid-tt0000000]/
└── Season 01/
    ├── S01E01.avi
    ├── S01E02.avi
    └── ...
```

### 3. Badly named fallback files

```text
sopranos6/
├── Klan_Soprano_VI_13_DVDRip.avi
├── Klan_Soprano_VI_14_DVDRip.avi
└── ...
```

If explicit numbering is missing, files are assigned by sorted order and placed into the appropriate season without overwriting recognized targets.

---

## Recommended workflow

For new collections:

```bash
python SerialsRenamer.py /path/to/Serials --dry-first
```

This is the safest mode:

- you see the plan before it is applied
- you can skip or re-search if needed
- you can stop anytime with `0` or `Ctrl+C`

Once you trust the current batch:

```bash
python SerialsRenamer.py /path/to/Serials
```

---

## Limitations

- relies on Kinopoisk and TMDb availability
- does not try to understand every possible custom fan naming scheme
- subtitle-only ambiguous collections are intentionally not guessed too aggressively
- roman numeral based episode detection is not supported directly unless sortable fallback is sufficient

---

## Exit behavior

- `0` in menus exits the whole script cleanly
- `Ctrl+C` also exits cleanly
- cache is still saved on exit
- operations log is still finalized on exit

---

## License

MIT
