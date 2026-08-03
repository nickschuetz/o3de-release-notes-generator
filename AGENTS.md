# AGENTS.md

## Project overview

O3DE Release Notes Generator: a standalone Python tool that generates Open 3D Engine release notes from merged pull requests. Zero external dependencies (Python 3.10+ stdlib only).

## Build & run

```bash
# No build step (single-file Python script)
python release_notes.py --version

# Run tests
python -m pytest tests/ -v

# Regenerate SBOM
python generate_sbom.py
```

## Key commands

```bash
# Generate release notes (most common usage)
python release_notes.py generate \
  --from-ref <start-tag> --to-ref <end-branch> \
  --default-repo-path /path/to/o3de \
  --output-json release_data.json \
  --output-md release_notes.md \
  --release-version <version>

# Fetch only (JSON output for programmatic use)
python release_notes.py fetch \
  --from-ref <start-tag> --to-ref <end-branch> \
  --default-repo-path /path/to/o3de \
  --output-json release_data.json

# Render only (from existing JSON)
python release_notes.py render \
  --input-json release_data.json \
  --output-md release_notes.md \
  --release-version <version>
```

## Code conventions

- Zero external dependencies (stdlib only); do not add pip packages
- All subprocess calls use list arguments, never `shell=True`
- All subprocess calls pass `encoding='utf-8', errors='replace'`
- All user inputs validated with regex before use in subprocess or file I/O
- GraphQL queries use server-side variables (`$owner`, `$name`); never string-interpolate owner/repo into the query body
- Atomic file writes via `tempfile.mkstemp()` + `os.replace()`
- Logging via `logging.getLogger('o3de.release_notes')`; never log secrets; subprocess stderr passes through `_safe_stderr()` (token-scrub + truncate)
- Return codes: 0 = success, 1 = failure
- PR titles and descriptions sanitized for markdown AND HTML before rendering; escape exactly once (`_strip_title_decorations` then `_escape_markdown`), never re-escape an already-escaped string; PR bodies capped at 64KB before extraction
- Subprocess call sites must convert `subprocess.SubprocessError` and `OSError` into handled errors; never let `TimeoutExpired` escape and discard a run's work
- Atomic writes go through `write_text_atomic()`, which fsyncs and preserves the destination's mode
- Every filter that removes a PR from the report must be reflected in `summarize_render_coverage()`; silent drops are the failure mode this project cares most about
- Tests use `pytest` with `unittest.mock`; no network calls in tests
- Summary command parsed via `shlex.split()` (not `.split()`) so quoted args are supported
- Summary command runtime bounded by `--summary-timeout` (default 300s, range 10–3600s)
- LLM output cleaned by `_clean_summary()` (strips preamble and dividers)
- SIG categorization tiebreaks deterministically via `SIG_CANONICAL_ORDER` (label sort + title-keyword tiebreak); do not introduce non-deterministic ordering

## Architecture

Three-stage pipeline: Extract (git log) → Categorize (SIG labels/heuristics) → Render (markdown). See ARCHITECTURE.md for full details including security model (OWASP/NIST).

SIG categorization heuristics are data-driven dicts at the top of `release_notes.py` (`SIG_TITLE_KEYWORDS`, `SIG_FILE_PATH_PATTERNS`); edit these to adjust categorization.

PR discovery requires BOTH `PR_NUMBER_PATTERN` (squash merges, `(#N)`) and `MERGE_COMMIT_PR_PATTERN` (merge commits, `Merge pull request #N`). Do not add `--no-merges` back to the git log call: O3DE uses both merge strategies and merge-commit PRs have no other reference.

## Things to know

- The o3de repo is always read-only; this tool never writes to it
- `--repo-path` takes `owner/repo=/path` mappings for multi-repo support; `--repo-from-ref` / `--repo-to-ref` do the same for git refs, needed because `o3de/o3de-extras` is not tagged on every release line. All three use `action='extend'` so repeated flags accumulate
- Refs are preflighted with `verify_refs_exist()` before any git log or API work
- `--exclude-json` drops PRs already reported in a prior release. This is NOT optional for a major-release window: a `main`-line tag shares only an ancient merge-base with `development`, so `2605.0..development` spans two cycles (188 of 369 PRs had already shipped in 26.05.0). Ancestry and date cutoffs both fail here; the previous report is the only reliable separator
- `--generate-summary` pipes a prompt via stdin to an LLM (default: `ollama run --nowordwrap qwen2.5:14b`; use `claude -p` for cloud, or `qwen2.5:32b` if you have ~24GB VRAM)
- `--summary-hint` injects narrative guidance into the LLM prompt; accepts inline text or `@filepath` to read from a file
- `--summary-timeout` bounds the LLM runtime (default 300s, range 10–3600s)
- `--dry-run` previews which PRs would be fetched (from local `git log`) without calling the GitHub API or writing files
- `--log-file PATH` appends logs to a file in addition to stderr
- `--no-pointrelease-audit` suppresses the audit sidecar that's normally written when `--from-ref` looks like a point-release tag (`X.Y.N`, `N>0`); the sidecar cross-checks each cherry-pick container PR's bundled fixes against the rendered report
- `--include-release-machinery` re-includes PRs flagged `release_machinery: true` (version bumps, SBOM auto-updates, cherry-pick-to-pointrelease wrappers, `engine.json`/`sbom.cdx.json`/`version.txt`-only diffs) in the rendered output. Default is to filter them; turn on for point-release notes where machinery IS the content
- JSON intermediate format supports `manual_override_sig` and `manual_override_description` fields; these must be preserved on incremental re-runs
- **Labels are not evidence of a sync container.** `sync/to-stabilization` and friends live on ordinary PRs; a substring match on them once deleted 57 real changes from a shipped report. Only title evidence flags a cherry-pick
- Every run logs a reconciliation line (`N in JSON, M rendered`) plus a WARNING breakdown of exclusions; read it
- **Watch for the merge drop warning**: PRs in the prior JSON that no longer appear in `git log` are dropped *unless* they carry a `manual_override_*` field. Direct edits to `description` / `sig_category` without setting the override are silently lost; `merge_with_existing` logs a `WARNING` count when this happens.
- Schema version is in the `SCHEMA_VERSION` constant. Bump it when changing JSON structure, and accept the previous version for backward compatibility
- SBOM at `sbom.cdx.json` is auto-regenerated by GitHub Actions on push. Its stdlib inventory is derived by `ast`-parsing the sources, so it cannot drift; do not reintroduce a hand-maintained module list. Substantive content is deterministic (no wall-clock, no running-interpreter version), which is what makes `make sbom-check` a real CI gate
- Tests run on Python 3.10 / 3.11 / 3.12 / 3.13 in CI on every push and PR (`.github/workflows/test.yml`); the lint job also runs ruff, mypy strict, and `generate_sbom.py --check`
- GitHub Actions are pinned to commit SHAs; see CONTRIBUTING.md for the update policy
- Dual licensed: Apache-2.0 OR MIT (contributions must be under both; see CONTRIBUTING.md)