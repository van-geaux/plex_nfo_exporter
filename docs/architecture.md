# Architecture

Plex NFO Exporter is a single-file Python script (`main.py`) that reads metadata,
posters, and fan-art from a Plex server over its HTTP API and writes them out as
`.nfo`/`.jpg` files next to the media, in a layout other media servers (primarily
Jellyfin) can read. It runs as a one-shot CLI invocation, either manually or on a
cron schedule inside the Docker image.

There is no persistent service, database, or web UI. State lives entirely in the
config file, the Plex server, and the output files on disk.

## Entry point and CLI

`main.py` is invoked directly (`python main.py ...`). The `if __name__ == '__main__'`
block at the bottom of the file:

1. Parses CLI flags with `argparse` (`--url`, `--token`, `--library`, `--title`,
   naming-mode flags, per-export enable/disable pairs, `--force-overwrite`,
   `--dry-run`, `--log-level`, `--config`).
2. Resolves the config directory (`resolve_config_dir()` / `--config`).
3. Calls `ensure_files_exist()` to generate placeholder `config.yml`/`.env` on
   first run (and exit, so the user can fill them in).
4. Calls `set_logger()` to build the logger and rotate old log files.
5. Calls `main(args, log_name, resolved_config_dir)`, which drives the export.

CLI flags always take precedence over environment variables, which take
precedence over `config.yml` values (see `resolve_base_settings`,
`build_export_flags`, `determine_force_overwrite`, `determine_dry_run`).

## Configuration loading

- `config.yml` is loaded with PyYAML. A custom `!env_var` constructor and a
  regex pass (`env_var_constructor`, `load_configuration`) substitute
  `${VAR_NAME}` placeholders with environment variables (typically sourced from
  `.env` via `python-dotenv`).
- `resolve_config_dir()` auto-detects `/app/config` (the Docker mount point) and
  falls back to the current directory otherwise; `--config` overrides both.
- `Libraries: ['*']` means "process every library"; `Blacklist` names are
  excluded. Music libraries must be listed twice in `Libraries` because Plex
  exposes separate roots for artists and albums under one library key — this is
  handled by the `check_music` state machine in `resolve_library_type()`.

## HTTP layer

All Plex requests go through `get_request()`:

- Enforces same-origin (`same_origin()`) against the configured `baseurl` before
  attaching the `X-Plex-Token` header, so a redirect or misconfigured URL can't
  leak the token to another host.
- Disables `requests`' automatic redirect following (`allow_redirects=False`).
- Applies a fixed `(10, 60)` connect/read timeout (`REQUEST_TIMEOUT`) with no
  retries.

XML responses are read through `response_content()` / `parse_xml_response()`,
which cap response size at `MAX_XML_RESPONSE_BYTES` (50 MiB) before handing the
bytes to `xml.etree.ElementTree`, and raise on parse failure instead of
propagating a raw `ParseError`.

Images are downloaded through `download_image()`, which additionally:
- Validates `Content-Type` starts with `image/`.
- Caps raw and gzip-decompressed body size at `MAX_IMAGE_RESPONSE_BYTES` (50 MiB).
- Caps decoded pixel count at `MAX_IMAGE_PIXELS` (100,000,000) before letting
  Pillow decode it.
- Converts `RGBA`/`P` images to `RGB` before saving as JPEG.

## Library and metadata traversal

1. `get_library_details()` — `GET /library/sections`, resolves the requested
   library names (or `*`) against Plex's section list, applying the blacklist.
2. `resolve_library_type()` — maps Plex's `type` attribute (`movie`, `show`) via
   `TYPE_MAP` to the internal `(library_type, xml_root_tag)` pair, and drives the
   artist/album alternation for music libraries.
3. `fetch_library_root()` — `GET /library/sections/{key}/all` (or `/albums` for
   the second music pass). On HTTP 400, falls back to `fallback_response()`,
   which pages through the library with `X-Plex-Container-Start/Size` and
   concatenates each page's `Directory` nodes into one combined tree.
4. `process_library()` iterates the section's top-level items with a progress
   bar (`alive_progress`), calling `process_content()` per item and aggregating
   counts into a per-library summary (`create_library_result()`).
5. `process_content()` — fetches full item metadata
   (`GET /library/metadata/{ratingKey}`), optionally filters by `--title`,
   resolves the on-disk media path(s) via `get_media_path()`, then computes
   output file paths via `get_file_path()` and dispatches each enabled export
   (NFO, episode NFO, poster, fan-art, season posters) to `process_media()`.

`get_media_path()` reads the on-disk path from Plex's XML differently per type:
- `movie` — `Media/Part[@file]`.
- `tvshow`/`artist` — `Location[@path]`.
- `albums` — fetches the album's track list and reads the first track's
  `Media/Part[@file]`, since Plex doesn't expose a `Location` for albums
  directly.

## Path safety

Two independent guards keep all filesystem writes inside expected directories:

- `map_media_path()` — maps a Plex-side path (e.g. `/data_media/Movies/...`) to
  the local filesystem path using the configured `Path mapping` list. It
  requires absolute, normalized roots, computes the path via `os.path.relpath`,
  and rejects (raises `ValueError`) any result that isn't actually inside the
  matched local root (traversal / partial-prefix protection) or that matches no
  mapping at all when mappings are configured (fails closed).
- `safe_output_path()` — joins a computed filename onto a media directory and
  rejects the result if it resolves (`os.path.realpath`) outside that directory.

## NFO generation

NFO files are built with `xml.etree.ElementTree`, not string concatenation, so
output is escaped and well-formed:

- `write_nfo()` builds a `<movie>`/`<tvshow>`/`<artist>`/`<album>` root and
  delegates to small per-section writers, each independently gated by the
  matching `config.yml` boolean:
  - `write_agent_ids_section()` — parses the item's `guid` and `Guid` children
    into `<tmdbid>`, `<imdbid>`, Hama-style `<{agent}id>`, etc.
  - `write_simple_fields()` — driven by `SIMPLE_FIELD_MAP` (title, plot, mpaa,
    ratings, year, tagline, runtime, release date, studio).
  - `write_tag_collections()` — driven by `TAG_COLLECTION_MAP` (genre, country,
    style).
  - `write_ratings_section()`, `write_people_sections()` (directors/writers via
    `PEOPLE_MAP`), `write_roles_section()` (actors/roles with thumbs).
  - `add_xml_element()` validates every tag name against `XML_NAME_PATTERN`
    before creating it, so unexpected Plex data can't produce malformed XML.
- `write_episode_nfo()` is a separate builder for `<episodedetails>` (season,
  episode, title, plot, mpaa, user rating, aired date, and `<uniqueid>` per
  `Guid`, tagged `imdb`/`tmdb`/`tvdb` by substring match). Unknown GUID agent
  types are currently silently skipped (see `docs/roadmap.md` /
  `CHECKLIST.md`).

## Write decision logic

`process_media()` is the shared decision point for every output file type
(NFO, episode NFO, poster, fan-art, season poster):

- If the target directory doesn't exist, the write is skipped (`not_exist`).
- In dry-run mode, nothing is written; the intended action is logged.
- Otherwise, if the file already exists, its mtime is compared against the
  Plex item's `updatedAt`; it's only rewritten if the Plex copy is newer or
  `force_overwrite` is set. Otherwise it's counted as `skipped`.
- New/updated files are counted as `success`/`updated`; write failures are
  counted as `failure`.

Per-library counts are aggregated in `create_library_result()` /
`update_summary()` and printed at the end of a non-dry-run invocation by
`print_library_summary()`.

## Logging

`set_logger()`:
- Registers a custom `VERBOSE` level (15, between `DEBUG` and `INFO`) used for
  per-item `[ADDED]`/`[UPDATED]`/`[SKIPPED]`/`[FAILURE]` detail lines.
- Attaches a console handler (level from `--log-level` / `LOG_LEVEL` env /
  `log_level` in config, defaulting to `INFO`) and a file handler (always at
  least `VERBOSE`) writing to `logs/app-{date}-{n}.log`.
- Prunes `logs/` down to the 10 most recently modified files on each run.

## Global state

`baseurl`, `headers`, and `logger` are module-level globals set inside
`main()`/`resolve_base_settings()` and read by helper functions throughout the
file (e.g. `get_request()`, `process_media()`). This makes the exporter hard to
unit test in isolation; see `CHECKLIST.md` for the tracked cleanup item.

## Deployment

- `dockerfile` builds from a digest-pinned `python:3.11-slim`, installs
  `requirements.txt`, and installs [Supercronic](https://github.com/aptible/supercronic)
  (checksum-verified) to run the script on a cron schedule inside the
  container.
- `entrypoint.sh` writes a crontab entry from `$CRON_SCHEDULE` (default
  `0 4 * * *`), optionally runs the script immediately if `RUN_IMMEDIATELY=true`,
  then hands off to `supercronic`.
- Config/`.env`/`logs` are expected to be bind-mounted at `/app/config` and
  `/app/logs` respectively; `resolve_config_dir()` and `set_logger()` detect
  this layout automatically.
