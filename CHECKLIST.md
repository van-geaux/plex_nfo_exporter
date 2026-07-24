# Project Checklist

Current status of tracked work on Plex NFO Exporter. This is the single
source of truth for "is X done" — `docs/roadmap.md` explains the phased plan
and ordering; this file tracks item-by-item status. Migrated from the former
`TODO.md` and `SECURITY_ROADMAP.md` on 2026-07-24; those files are retired.

## Status legend

- `[ ]` Not started
- `[-]` In progress
- `[x]` Complete and verified
- `[!]` Blocked or needs a decision

## Audit baseline

- Dependabot alerts reviewed: 2026-07-24
- Open Dependabot alerts: 28
- Historical fixed alerts: 1 (Tornado, alert #1)
- Current dependency manifest: `requirements.txt`

## Reliability and correctness

- [x] Pagination fallback (`fallback_response`) combines chunked responses into
      one XML tree instead of returning only the last chunk.
- [x] Empty/missing `Libraries` config handled without indexing an empty list.
- [x] Blacklist normalized so `in` checks never raise `TypeError`.
- [x] NFO generation uses an `ElementTree` builder (`write_nfo`,
      `write_episode_nfo`, `add_xml_element`) instead of raw string
      concatenation, with escaping and tag-name validation.
- [x] Plex/image HTTP requests centralized behind `get_request()` with
      explicit timeouts and no automatic retries.
- [x] Guard `.find('Media/Part')` usage for movies and episodes; skip or warn
      when Plex returns metadata without media parts instead of raising
      `AttributeError`. (Episode side was already guarded in
      `export_episode_nfos`; movie side fixed in `process_content`.)
- [x] Fix `get_file_path()` so movie image naming does not depend on
      `Movie NFO name type`; compute the sanitized title and filename once
      before branching. (Already resolved in `ed894b1`; confirmed via
      `test_get_file_path_image_naming_independent_of_nfo_naming`.)
- [x] Harden `write_episode_nfo()` GUID handling so unknown agent IDs don't
      leave `utype` undefined or silently drop the `<uniqueid>`. Fixed a real
      bug where a `Guid` element with no `id` attribute raised `TypeError`
      (`'imdb' in guid.get('id')` on `None`), aborting the whole episode NFO.
- [x] Add defensive parsing for albums, movies, seasons, and episodes when
      Plex returns incomplete XML nodes; log and skip bad items instead of
      aborting. `process_library()` now catches per-item exceptions from
      `process_content()` (e.g. `get_media_path()`'s `ValueError` for
      albums with no tracks) and logs + continues instead of aborting the
      whole library.
- [x] Reduce reliance on module-level globals (`logger`, `headers`,
      `baseurl`) so exporter functions are easier to test and reuse.
      `logger` is now initialized at true module scope (`logging.getLogger`
      is a singleton, so `set_logger()` configuring it later still works)
      so it exists even before `set_logger()` runs. `headers` is no longer a
      global at all — `main()` builds it locally and it's threaded
      explicitly through `process_library`/`process_content`/
      `process_media`/`fetch_library_root`/`export_episode_nfos`/
      `export_season_posters`. `baseurl` remains a module global
      deliberately: `get_request()`'s same-origin enforcement (Phase 3)
      reads it via `globals()`, and removing that would silently disable
      the security check; `resolve_base_settings()` now also returns it
      so callers thread it explicitly instead of reading the bare global.
      Verified with the full pytest suite plus an ad hoc end-to-end smoke
      test (fake local Plex HTTP server, dry-run and real-write passes)
      exercising the whole refactored call chain.

## Testability

- [x] Establish a test runner and layout for `main.py` (`tests/test_main.py`,
      `pytest`, see `docs/testing.md`).
- [x] Remove the stale `tests/test_service.py` reference to a nonexistent
      `service` package (leftover from an abandoned effort; confirmed via
      `git log` that no `service` module ever existed to restore it
      against).
- [x] Add unit tests for URL construction and request handling
      (`same_origin`, `get_request`, `response_content`,
      `parse_xml_response`).
- [x] Add unit tests for path mapping and filename generation
      (`map_media_path`, `safe_output_path`, `get_file_path`,
      `sanitize_filename`).
- [x] Add unit tests for XML/NFO output (`add_xml_element` and the NFO
      section writers).
- [x] Add unit tests for configuration loading and environment substitution
      (`load_configuration`, `resolve_base_settings`, `build_export_flags`,
      `determine_force_overwrite`, `determine_dry_run`, `resolve_config_dir`,
      `str_to_bool`).
- [x] Add unit tests for incomplete Plex responses: `write_episode_nfo()`
      with a `Guid` missing `id` / with an unknown agent, and
      `process_content()` for a movie with no `Media/Part`.

## Dependency and supply-chain hardening

- [x] Upgrade `pillow` to `12.3.0`.
- [x] Upgrade `urllib3` to `2.7.0`.
- [x] Upgrade `requests` to `2.34.2`.
- [x] Upgrade `python-dotenv` to `1.2.2`.
- [x] Run dependency consistency checks (`pip check`) and a vulnerability scan
      against `requirements.txt`.
- [ ] Recheck Dependabot alerts and confirm the Pillow/urllib3/Requests/
      python-dotenv alerts close.
- [x] Pin `alive-progress` to `3.3.0`.
- [x] Pin the Docker base image (`python:3.11-slim`) by digest.
- [x] Verify the Supercronic binary download by checksum in `dockerfile`.
- [x] Review and tighten `.github/workflows/stale.yml` permissions; pin
      `actions/stale` to a commit hash.

## Network and remote-input hardening

- [x] Add explicit connect/read timeouts to every HTTP request, no retries.
- [x] Reject requests outside the configured Plex origin before attaching
      auth headers; disable automatic redirects.
- [x] Limit remote XML/image response sizes and decoded image pixel count.
- [x] Restrict XML parsing to the standard-library parser via one wrapper,
      with defensive handling for malformed/oversized responses.

## File-system and generated-output hardening

- [x] Boundary-aware, absolute-path mapping for Plex-derived output paths
      (`map_media_path`, `safe_output_path`); fail closed on unmatched
      mappings or traversal attempts.

## CI

- [x] Add a CI workflow for dependency installation and syntax checks
      (`.github/workflows/ci.yml`, `test` job: `pip install`, `pip check`,
      `python -m py_compile main.py`).
- [x] Add the automated test suite to CI once it exists (`test` job runs
      `pytest -q`).
- [x] Add dependency vulnerability scanning to CI (`dependency-audit` job
      runs `pip-audit -r requirements.txt`; verified locally with no known
      vulnerabilities against current pins).
- [x] Add Docker build verification to CI (`docker-build` job builds the
      image from `dockerfile`; verified locally with `docker build`).

## Release follow-up (not started)

- [ ] Run the full test suite in a clean environment once one exists.
- [ ] Run dependency and container vulnerability scans.
- [ ] Build and start the Docker image; verify config, `.env`, cron
      scheduling, dry-run mode, and export behavior end-to-end.
- [ ] Re-query GitHub Dependabot and record the final alert state.
- [ ] Update the README only where implemented behavior or documented
      procedures changed.
