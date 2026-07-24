# Testing

## Automated tests

`tests/test_main.py` is a `pytest` suite that imports `main` directly and
unit-tests its pure helper functions — no live Plex server required:

- `sanitize_filename`, `get_file_path` (all naming-mode combinations)
- `map_media_path`, `safe_output_path` (path-mapping and traversal/escape
  guards)
- `same_origin`, `get_request` (origin enforcement, timeout, redirect
  disabling — `requests.get` is monkeypatched)
- `response_content`, `parse_xml_response` (size limits, malformed-XML
  handling)
- `resolve_library_type` (movie/show/music artist-album alternation)
- `add_xml_element` and the NFO section writers (`write_simple_fields`,
  `write_tag_collections`, `write_ratings_section`, `write_people_sections`,
  `write_roles_section`, `write_agent_ids_section`), each driven by a
  hand-built `xml.etree.ElementTree` element standing in for Plex metadata.

Run it with:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

(`requirements-dev.txt` layers `pytest` on top of `requirements.txt`; the
runtime dependency list is unaffected.)

Functions that depend on module-level globals (`baseurl`, `headers`,
`logger`) or perform live HTTP/filesystem I/O end-to-end — `process_media`,
`process_content`, `process_library`, `download_image`, `write_nfo`,
`write_episode_nfo` — are not yet covered by unit tests; see
`CHECKLIST.md`'s testability items (reducing global state, adding coverage
for incomplete Plex responses) for what's still open.

`tests/test_service.py`, which referenced a nonexistent `service` package
from an abandoned web-service/job-runner effort, has been removed — there was
nothing in the repo or git history to restore it against.

## Manual verification

Automated coverage above is unit-level only; still verify manually for
anything that touches live Plex behavior:

1. **Dry run against a real Plex server** — set `DRY_RUN=true` (or `--dry-run`)
   so the script logs every action it *would* take without writing files:
   ```bash
   python main.py --dry-run --log-level VERBOSE
   ```
   Check the console/log output for the expected `[ADDED]`/`[UPDATED]`/
   `[SKIPPED]`/`[FAILURE]` lines for the libraries and export types you changed.
2. **Live run against a scratch/test library** — point `config.yml`'s
   `Libraries` (or `--library`) at a small, disposable Plex library (or use
   `Blacklist` to exclude production libraries), then run without `--dry-run`
   and inspect the generated `.nfo`/`.jpg` files and the printed summary
   counts.
3. **Docker build** — verify the image still builds and the entrypoint script
   is valid after `dockerfile`/`entrypoint.sh` changes:
   ```bash
   docker build -t plex-nfo-exporter:test .
   ```

## Adding tests

- Add new tests to `tests/test_main.py` (or a new `tests/test_*.py` module)
  by importing `main` directly, following the pattern above.
- Functions that read the module globals (`get_request`, `process_media`,
  `main`) need those globals set or monkeypatched (see
  `test_get_request_rejects_cross_origin` for the pattern) until
  `CHECKLIST.md`'s global-state cleanup item is done.
