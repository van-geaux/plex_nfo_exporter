# Testing

## Current state: no working automated test suite

`tests/test_service.py` exists but **cannot currently be collected or run**:

- It imports `from service import app as app_module` and
  `from service.jobs import JobManager, JobStatus` — there is no `service`
  package anywhere in this repository.
- It depends on `fastapi` (via `fastapi.testclient.TestClient`) and `pytest`,
  neither of which is listed in `requirements.txt`.

This appears to be leftover coverage from an abandoned web-service/job-runner
effort that was never merged, not a test of the actual `main.py` CLI. It is
tracked for cleanup in `CHECKLIST.md` ("Remove or restore the stale
`tests/test_service.py` reference to a nonexistent `service` package").
**Do not treat a green run of this file as verification of anything** — as of
this writing it fails to import before any test runs, and there is currently no
`service` module to restore it against.

Until that item is resolved, `main.py` has no automated regression coverage at
all. Changes must be verified manually (below) and, where practical, backed by
new targeted tests introduced alongside the change (see "Adding tests" below).

## Manual verification (current practice)

1. **Syntax / import check** — install dependencies, then confirm the module
   imports cleanly:
   ```bash
   pip install -r requirements.txt
   python -c "import main"
   ```
2. **Dry run against a real Plex server** — set `DRY_RUN=true` (or `--dry-run`)
   so the script logs every action it *would* take without writing files:
   ```bash
   python main.py --dry-run --log-level VERBOSE
   ```
   Check the console/log output for the expected `[ADDED]`/`[UPDATED]`/
   `[SKIPPED]`/`[FAILURE]` lines for the libraries and export types you changed.
3. **Live run against a scratch/test library** — point `config.yml`'s
   `Libraries` (or `--library`) at a small, disposable Plex library (or use
   `Blacklist` to exclude production libraries), then run without `--dry-run`
   and inspect the generated `.nfo`/`.jpg` files and the printed summary
   counts.
4. **Docker build** — verify the image still builds and the entrypoint script
   is valid after `dockerfile`/`entrypoint.sh` changes:
   ```bash
   docker build -t plex-nfo-exporter:test .
   ```

## Adding tests

There is no established test runner or layout yet (tracked as
`CHECKLIST.md` → "Establish a test runner and layout for `main.py`"). If you
add tests before that item lands:

- Add `pytest` to `requirements.txt` (or a separate dev-requirements file) and
  a `tests/` module that imports `main` directly rather than shelling out.
- Favor unit-testing the pure helper functions that don't depend on the
  `baseurl`/`headers`/`logger` globals or live HTTP calls: `sanitize_filename`,
  `map_media_path`, `safe_output_path`, `get_file_path`, `same_origin`,
  `resolve_library_type`, and the NFO section writers (`write_simple_fields`,
  `write_tag_collections`, `write_people_sections`, etc., called with a hand-built
  `xml.etree.ElementTree` element standing in for Plex metadata).
- Functions that read the module globals (`get_request`, `process_media`,
  `main`) will need those globals set or monkeypatched until
  `CHECKLIST.md`'s global-state cleanup item is done.
- Do not name new tests `test_service.py` unless you are genuinely restoring a
  `service` module — reuse of that filename without the module will reintroduce
  the current broken-import problem.
