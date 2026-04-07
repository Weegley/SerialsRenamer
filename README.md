# SerialsRenamer

Production-oriented Python script for normalizing TV series folders and episode files.

It helps reorganize messy serial collections into a predictable structure:

```text
Series Title [kp1234567][tt1234567]/
└── Season 01/
    ├── S01E01.mkv
    ├── S01E01.rus.srt
    ├── S01E02.mkv
    └── ...
```

## Important note about API key

This script uses **Kinopoisk Api Unofficial** as its data source:
<https://kinopoiskapiunofficial.tech/>

By default, the script contains a shared API key for **Kinopoisk Api Unofficial**.

This is convenient for quick testing, but for regular use it is strongly recommended to replace it with **your own API key**.

Why:
- shared keys can hit rate limits
- shared keys may stop working unexpectedly
- using your own key is more reliable and predictable

In other words: the bundled key is fine for trying the script, but for real usage you should set your own key in the script.

---

The script is designed to be interactive, conservative, and filesystem-safe:

- it can preview changes before applying them
- it asks for confirmation per series
- it avoids aggressive guessing in ambiguous cases
- it keeps non-empty directories instead of deleting them blindly
- it uses fallback logic when filenames are messy but still sortable

---

## Features

### Series recognition

- searches series on Kinopoisk
- supports direct `kp` ID input during manual selection
- can reuse IDs already embedded in folder names:
  - `[kp1234567]`
  - `[tt1234567]`

### Folder normalization

- normalizes the main series folder name using templates
- normalizes season folder names
- can rename already identified but badly named source folders

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

## Resulting structure

Default output layout:

```text
{title} [kp{kp}][{tt}]/
└── Season {season:02d}/
    ├── S{season:02d}E{episode:02d}{ext}
    └── S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}
```

Example:

```text
Сопрано [kp79848][tt0141842]/
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
- internet access for Kinopoisk search and details lookup

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

### Prefer Russian titles

```bash
python SerialsRenamer.py /path/to/Serials --lang-priority ru
```

### Prefer English titles

```bash
python SerialsRenamer.py /path/to/Serials --lang-priority en
```

### Always confirm search results manually

```bash
python SerialsRenamer.py /path/to/Serials --mode manual
```

---

## Command line options

```text
root                  Root path to Serials
--cache               Cache json path
--ops-log             Operations log file path
--lang-priority       ru | en | any
--mode                smart | manual
--dry-first           Show resulting tree for each series and ask confirmation
--dry-run             Do not modify filesystem
```

---

## Interactive workflow

For each detected series, the script:

1. scans files
2. tries to infer title from folder structure
3. resolves series metadata via Kinopoisk
4. builds a rename and move plan
5. optionally shows preview
6. applies changes after confirmation

### Search result menu

Typical options:

- `0` — exit the whole script
- `98` — skip current series
- `99` — retry same search
- `Enter` — accept the only result, when there is exactly one
- any other text — new search query or `kp` ID

Examples of valid manual input:
- `kp1234567`
- `1234567`
- `The Sopranos`

---

## Preview mode

With `--dry-first`, the script shows a per-series preview like this:

```text
Planned tree:
  Сопрано [kp79848][tt0141842]/
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
SERIES  Sopranos(full version)  ->  Сопрано [kp79848][tt0141842]

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

Cached data typically includes:
- chosen title
- Kinopoisk ID
- IMDb ID
- year
- original title

---

## Naming templates

The script uses templates for the final structure.

### Default templates

```python
SERIES_FOLDER_TEMPLATE = "{title} [kp{kp}][{tt}]"
SEASON_FOLDER_TEMPLATE = "Season {season:02d}"
EPISODE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{ext}"
SUBTITLE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}.{subtype}.{lang}{ext}"
```

### Available template fields

- `{title}` — chosen title according to `--lang-priority`
- `{series_title}` — alias of `{title}`
- `{original_title}` — original or alternate title
- `{kp}` — Kinopoisk ID
- `{tt}` — IMDb ID
- `{year}` — release year
- `{season}` — season number
- `{episode}` — episode number
- `{lang}` — subtitle language
- `{subtype}` — subtitle subtype
- `{ext}` — file extension including dot

### Example custom templates

Compact:

```python
SERIES_FOLDER_TEMPLATE = "{title}"
SEASON_FOLDER_TEMPLATE = "S{season:02d}"
EPISODE_FILE_TEMPLATE = "S{season:02d}E{episode:02d}{ext}"
```

Verbose:

```python
EPISODE_FILE_TEMPLATE = "{title} ({original_title}) {year} Сезон {season:02d} Серия {episode:02d}{ext}"
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
Сопрано [kp79848][tt0141842]/
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
Плевако [kp4470538]/
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

- relies on Kinopoisk API availability
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
