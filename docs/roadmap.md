# Roadmap

This describes the phased plan for hardening and stabilizing Plex NFO
Exporter. For the current status of any individual item, see `CHECKLIST.md` —
this file explains the *why* and *ordering*, not the checkbox state. Migrated
from `SECURITY_ROADMAP.md`/`TODO.md` on 2026-07-24; those files are retired.

Work is handled one item at a time. Items may be reordered only after
reviewing the impact on the current item and its verification plan.

## Phase 1 — Close open Dependabot alerts

Upgrade `pillow`, `urllib3`, `requests`, and `python-dotenv` to the versions
that close currently-known CVEs, verifying compatibility and basic
functionality (image load/save, request preparation, `.env` loading) after
each bump. Finish by re-checking Dependabot to confirm the alerts actually
close and running a full dependency consistency/vulnerability pass.

## Phase 2 — Reproducible and safer dependency/container supply chain

Pin `alive-progress` to an explicit version instead of floating. Pin the
Docker base image by digest rather than a moving tag, and document who's
responsible for updating that digest. Verify Supercronic downloads by
checksum in the `dockerfile`. Review `.github/workflows/stale.yml` for least
privilege and pin the `actions/stale` action to a commit hash.

## Phase 3 — Network and remote-input hardening

Centralize all Plex/image HTTP GETs behind one helper with explicit timeouts
and no automatic retries. Restrict that helper to the configured Plex origin
and disable redirect following, so an authenticated request can't be
redirected to another host. Cap response sizes for both XML and image
downloads (including decompressed/decoded size) before parsing or decoding.
Keep XML parsing on the standard-library parser with defensive handling for
malformed or oversized Plex responses.

## Phase 4 — File-system and generated-output hardening

Replace partial-prefix path mapping with boundary-aware, absolute-path
mapping that fails closed on unmatched mappings or traversal attempts, and
apply it consistently across movie/TV/episode/season/artist/album output
paths. Replace raw XML string concatenation in NFO generation with an
`ElementTree` builder that escapes correctly. Episode GUID handling has been
hardened (a missing `id` attribute no longer raises `TypeError`), the movie
`Media/Part` lookup in `process_content()` is now guarded, and
`process_library()` catches per-item exceptions so one item with incomplete
Plex metadata doesn't abort the whole library run. Movie image-filename
derivation was already independent of the NFO naming mode. Remaining in this
phase: reducing reliance on module-level globals (see Phase 5).

## Phase 5 — Testability and maintainability

A real test runner and layout now exists (`tests/test_main.py`, `pytest` —
see `docs/testing.md`), with unit coverage for URL/request construction, path
mapping and filename generation, XML/NFO output, GUID handling,
incomplete-Plex-response handling, and configuration loading/environment
substitution. The stale `tests/test_service.py` reference to a nonexistent
`service` package has been removed — nothing in the repo or git history to
restore it against. `headers` is no longer a module global — it's built once
in `main()` and threaded explicitly through the export call chain; `logger`
is now initialized at module scope so it's available even before
`set_logger()` configures it. `baseurl` stays a module global by design,
since `get_request()`'s same-origin check depends on it, but
`resolve_base_settings()` now also returns it so callers don't have to reach
into module state directly. Phase 5 is complete.

## Phase 6 — Final verification and release follow-up

Once the above phases land: run the full test suite and dependency/container
vulnerability scans in a clean environment, build and start the Docker image
and verify config/`.env`/cron/dry-run/export behavior end-to-end, re-query
Dependabot for the final alert state, review the complete diff, and update
the README only where implemented behavior or documented procedures actually
changed.

## Recommended execution order

1. Phase 1 — dependency upgrades
2. Phase 2 — supply-chain pinning/verification
3. Phase 3 — network/remote-input hardening
4. Phase 4 — file-system and output hardening
5. Phase 5 — testability
6. Phase 6 — final verification and release follow-up

Phases 1–5 are complete. A CI workflow (`.github/workflows/ci.yml`) now runs
the test suite, dependency consistency/vulnerability checks, and a Docker
build on every push/PR. See `CHECKLIST.md` for the remaining Phase 6 release
follow-up items (clean-environment run, end-to-end Docker verification with
a live Plex server, Dependabot re-query, README update) — these need a real
Plex connection and/or repository write access this environment doesn't
have.
