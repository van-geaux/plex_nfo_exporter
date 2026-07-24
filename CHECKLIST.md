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
- [ ] Guard `.find('Media/Part')` usage for movies and episodes; skip or warn
      when Plex returns metadata without media parts instead of raising
      `AttributeError`.
- [ ] Fix `get_file_path()` so movie image naming does not depend on
      `Movie NFO name type`; compute the sanitized title and filename once
      before branching.
- [ ] Harden `write_episode_nfo()` GUID handling so unknown agent IDs don't
      leave `utype` undefined or silently drop the `<uniqueid>`.
- [ ] Add defensive parsing for albums, movies, seasons, and episodes when
      Plex returns incomplete XML nodes; log and skip bad items instead of
      aborting.
- [ ] Reduce reliance on module-level globals (`logger`, `headers`, `baseurl`)
      so exporter functions are easier to test and reuse.

## Testability

- [ ] Establish a test runner and layout for `main.py` (see `docs/testing.md`
      — there is currently no working automated suite).
- [ ] Remove or restore the stale `tests/test_service.py` reference to a
      nonexistent `service` package (leftover from an abandoned effort; see
      `docs/testing.md`).
- [ ] Add unit tests for configuration loading and environment substitution.
- [ ] Add unit tests for URL construction and request handling.
- [ ] Add unit tests for path mapping and filename generation.
- [ ] Add unit tests for XML/NFO output.
- [ ] Add unit tests for incomplete Plex responses.

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

- [ ] Add a CI workflow for dependency installation and syntax checks.
- [ ] Add the automated test suite to CI once it exists.
- [ ] Add dependency vulnerability scanning to CI.
- [ ] Add Docker build verification to CI.

## Release follow-up (not started)

- [ ] Run the full test suite in a clean environment once one exists.
- [ ] Run dependency and container vulnerability scans.
- [ ] Build and start the Docker image; verify config, `.env`, cron
      scheduling, dry-run mode, and export behavior end-to-end.
- [ ] Re-query GitHub Dependabot and record the final alert state.
- [ ] Update the README only where implemented behavior or documented
      procedures changed.
