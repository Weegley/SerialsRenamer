# SerialsRenamer

Production-oriented Python script for normalizing TV series folders and episode files.

It helps reorganize messy series collections into a predictable structure for media servers such as Jellyfin.

Canonical rendered ID formats:

- `[kp-1234567]`
- `[tmdbid-123456]`
- `[imdbid-tt1234567]`

The script can read older ID variants from existing folder names, but always renders IDs in the canonical format above.

---

## What the script does

The script is designed to be interactive, conservative, and filesystem-safe:

- it can preview changes before applying them
- it asks for confirmation per series
- it avoids aggressive guessing in ambiguous cases
- it keeps non-empty directories instead of deleting them blindly
- it uses fallback logic when filenames are messy but still sortable
- it can update already normalized series root folders without touching episode files

---

## Metadata sources and profiles

The script supports two metadata profiles.

### `ru`

Primary use case: Russian library.

Resolution flow:

- primary source: Kinopoisk
- enrichment: TMDb
- IMDb id: Kinopoisk first, TMDb as fallback

In short:

`kp -> tmdb`, IMDb from KP if present, otherwise from TMDb.

### `intl`

Primary use case: international / English-oriented library.

Resolution flow:

- primary source: TMDb
- IMDb id: TMDb
- Kinopoisk is not used as the primary source

In short:

`tmdb -> imdb`

### Default title language by profile

There is no `--lang-priority` option anymore.

The primary title is chosen automatically by profile:

- `ru` -> Russian primary title
- `intl` -> English / international primary title

---

## Important note about API keys

The script contains built-in default API credentials for quick testing:

- Kinopoisk Api Unofficial key
- TMDb bearer token

This is convenient for local testing, but for regular use it is recommended to replace them with your own credentials inside the script.

Why:

- shared keys can hit rate limits
- shared keys may stop working unexpectedly
- using your own keys is more reliable and predictable

---

## Features

### Series recognition

- supports Kinopoisk-based resolution in `ru` profile
- supports TMDb-based resolution in `intl` profile
- supports direct manual `kp` id input during Kinopoisk selection
- supports direct manual `tmdb` id input during TMDb selection
- can reuse IDs already embedded in existing folder names

Supported input ID variants:

#### Kinopoisk

- `[kp1234567]`
- `[kp-1234567]`

#### TMDb

- `[tmdb12345]`
- `[tmdb-12345]`
- `[tmdbid-12345]`

#### IMDb

- `[tt1234567]`
- `[imdbidtt1234567]`
- `[imdbid=tt1234567]`
- `[imdbid-tt1234567]`

All other bracketed tags in existing series folder names are treated as disposable noise during folder normalization and update mode.

Examples of removable noise:

- `[WEB-DL]`
- `[LostFilm]`
- `[1080p]`

### Folder normalization

- normalizes the main series folder name using templates
- normalizes season folder names
- normalizes episode filenames
- normalizes subtitle filenames
- can rename already identified but badly named source folders

### Safe metadata-only update mode

`--update-series-folders` updates only the root series folders.

It does **not** move or rename season folders, episode files, or subtitle files.

This mode is intended for safely:

- adding missing IDs
- rebuilding canonical folder names
- cleaning old noisy bracket tags
- updating metadata on already organized libraries

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

- `ru`, `rus`, `russian` -> `rus`
- `en`, `eng`, `english` -> `eng`

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

### Localized titles from TMDb translations

The script can use localized title fields in templates, for example:

- `{title_ru}`
- `{title_en}`
- `{title_de}`
- `{title_fr}`
- `{title_ko}`
- `{title_pt_BR}`
- `{title_zh_CN}`

Localized title availability depends on TMDb translations for that specific show.

Not every series has translations for every language.

### Deduplication of title fields

`{title}` is always the primary field.

Before rendering:

- if `{original_title}` is equal to `{title}`, it is cleared
- if any `{title_XX}` is equal to `{title}`, it is cleared
- if secondary fields duplicate each other, only the first unique value is kept and later duplicates are cleared

This prevents folder names from containing repeated titles such as the same Russian title twice.

---

## Default resulting structure

Default conservative output layout:

### `ru` profile

```text
{title} ({original_title}) ({year}) [kp-{kp}][tmdbid-{tmdb}][imdbid-{tt}]/
└── Season {season:02d}/
    ├── S{season:02d}E{episode:02d}{ext}
    └── S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}
```

Example:

```text
Блудливая Калифорния (Californication) (2007) [kp-394375][tmdbid-1215][imdbid-tt0904208]/
└── Season 01/
    ├── S01E01.avi
    ├── S01E02.avi
    ├── S01E02.eng.srt
    └── S01E02.rus.srt
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
Californication (2007) [tmdbid-1215][imdbid-tt0904208]/
└── Season 01/
    ├── S01E01.avi
    ├── S01E02.avi
    ├── S01E02.eng.srt
    └── S01E02.rus.srt
```

---

## Installation

### Requirements

- Python 3.10+
- internet access for Kinopoisk and TMDb lookups

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

### Use Russian metadata profile

```bash
python SerialsRenamer.py /path/to/Serials --metadata-profile ru
```

### Use international metadata profile

```bash
python SerialsRenamer.py /path/to/Serials --metadata-profile intl
```

### Always confirm search results manually

```bash
python SerialsRenamer.py /path/to/Serials --mode manual
```

### Metadata-only root folder update

```bash
python SerialsRenamer.py /path/to/Serials --update-series-folders --dry-run
```

---

## Command line options

```text
root                    Root path to Serials
--cache                 Cache JSON path
--ops-log               Operations log file path
--metadata-profile      ru | intl
--mode                  smart | manual
--dry-first             Show resulting tree or folder update preview for each series and ask confirmation
--dry-run               Do not modify filesystem
--update-series-folders Only update existing root series folder names using fresh metadata; do not move episode/subtitle files
```

---

## Interactive workflow

For each detected series, the script:

1. scans files
2. tries to infer title from folder structure
3. resolves series metadata according to the selected profile
4. builds a rename and move plan
5. optionally shows preview
6. applies changes after confirmation

### Search result menu

Typical options:

- `0` — exit the whole script
- `98` — skip current series
- `99` — retry same search
- `Enter` — accept the only result, when there is exactly one
- any other text — new search query or direct id input

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
  Сопрано (The Sopranos) (1999) [kp-79848][tmdbid-1398][imdbid-tt0141842]/
    [sopranos1] -> [Season 01]
      The Sopranos [S01E01, Goblin].avi -> S01E01.avi
      The Sopranos [S01E02, Goblin].avi -> S01E02.avi
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
SERIES  Sopranos(full version)  ->  Сопрано (The Sopranos) (1999) [kp-79848][tmdbid-1398][imdbid-tt0141842]

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

The script caches resolved series metadata to reduce repeated manual work.

Default cache file:

```text
.series_rename_cache.json
```

Cached data may include:

- chosen primary title
- Kinopoisk ID
- TMDb ID
- IMDb ID
- year
- original title
- localized titles

When testing new localization or template behavior, it is recommended to use a fresh cache file or clear the existing cache.

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
- `{title_es}`
- `{title_pt_BR}`
- `{title_zh_CN}`
- and other TMDb translation-derived fields when available

Other supported fields:

- `{kp}` — Kinopoisk ID without prefix
- `{tmdb}` — TMDb ID without prefix
- `{tt}` — IMDb ID including `tt` prefix
- `{year}` — release year
- `{season}` — season number
- `{episode}` — episode number
- `{lang}` — subtitle language token
- `{subtype}` — subtitle subtype token
- `{ext}` — file extension including the dot

### Example custom templates

Compact `intl`:

```python
INTL_SERIES_FOLDER_TEMPLATE = "{title} ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"
```

`intl` with an extra localized title:

```python
INTL_SERIES_FOLDER_TEMPLATE = "{title} ({title_ru}) ({year}) [tmdbid-{tmdb}][imdbid-{tt}]"
```

Verbose multilingual experiment:

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
- update already organized root series folders in metadata-only mode

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
Плевако (2023) [kp-4470538][tmdbid-...][imdbid-...]/
└── Season 01/
    ├── S01E01.avi
    ├── S01E02.avi
    └── ...
```

### 3. Metadata-only root folder refresh

```text
Адмирал Кузнецов (2024) [kp-5367251] [WEB-DL]/
```

Can become:

```text
Адмирал Кузнецов (2024) [kp-5367251][tmdbid-249204][imdbid-tt31715424]/
```

without moving episode files.

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

For already organized libraries that only need canonical folder names refreshed:

```bash
python SerialsRenamer.py /path/to/Serials --update-series-folders --dry-first
```

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
- not every series has TMDb translations for every language

---

## Exit behavior

- `0` in menus exits the whole script cleanly
- `Ctrl+C` also exits cleanly
- cache is still saved on exit
- operations log is still finalized on exit

---

## License

MIT
