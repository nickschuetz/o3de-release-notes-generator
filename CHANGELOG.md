# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0-beta] - 2026-05-20

### Added
- **Point-release audit sidecar.** When `--from-ref` is a non-zero point-release tag (e.g. `2510.2`), detects cherry-pick container PRs on the previous stabilization branch (titles matching `cherry-pick … from dev`, `merging point-release …`, etc.), parses the bundled PR numbers from each container's commit body, and writes `<output-md-stem>_pointrelease_audit.md` next to the rendered report — a ✓/✗ checklist showing whether each bundled fix is also present in the rendered report via its development-side merge. Turns the manual "did we lose anything?" check into an auditable artifact. Suppress with `--no-pointrelease-audit`.
- **Merge-base metadata** in `release_data.json`: per-repo `merge_bases` (sha + committer_date) and aggregate `effective_window` (start = earliest merge-base date across repos, end = generated_at). Anchors the diff's time window to the actual fork point, matching the date PR-curators typically reference in their release-notes PR descriptions.
- **Point-release awareness log line.** When `--from-ref` is a point-release tag with earlier siblings (e.g. `2510.1`, `2510.2`), one `INFO` line explains the merge-base equivalence between the major tag (`2510.0`) and the point-release tag against `--to-ref`, so re-runs don't relearn the lesson.
- **Release-machinery classifier.** Tags PRs whose title clearly indicates release engineering (version bumps, SBOM auto-updates, cherry-pick-to-pointrelease containers, "merging pointrelease into main", etc.) or whose entire file diff is unambiguous machinery (`engine.json` / `sbom.cdx.json` / `version.txt`) with `release_machinery: True`. Default-excluded from rendered markdown and summary prompts so the report stays focused on product changes; opt back in with `--include-release-machinery` (use this for point-release notes where machinery IS the content). The file-only heuristic deliberately excludes `.github/workflows/`-only PRs to avoid filtering real CI improvements.
- New helpers: `parse_point_release_tag`, `find_sibling_point_release_tags`, `extract_merge_base`, `extract_pointrelease_containers`, `write_pointrelease_audit`, `is_release_machinery`, `_emit_point_release_awareness_log`, `_maybe_write_pointrelease_audit`.
- New CLI flags: `--no-pointrelease-audit` (fetch / generate), `--include-release-machinery` (render / generate).
- 61 new tests (163 → 224) across `TestSchemaVersion`, `TestParsePointReleaseTag`, `TestFindSiblingPointReleaseTags`, `TestExtractMergeBase`, `TestExtractPointreleaseContainers`, `TestWritePointreleaseAudit`, `TestIsReleaseMachinery`, `TestRenderMarkdownExcludesMachinery`, `TestBuildSummaryPromptExcludesMachinery`, `TestEmitPointReleaseAwarenessLog`.

### Changed
- **Schema version bumped 2 → 3.** New `release_machinery` field on each PR; new metadata fields `merge_bases`, `effective_window`, `release_machinery_count`. `load_existing_json` continues to accept schema 2 — no migration step required for existing JSON files.
- `render_markdown()` and `_build_summary_prompt()` now accept `include_release_machinery: bool = False` and filter PRs flagged `release_machinery` by default.
- `.gitignore` cleaned up: the dead `reports/release_data.json` rule was inert (the file is tracked despite the rule) and has been removed; `reports/*.log` is now ignored to keep `--log-file` outputs out of commits.
- Version bumped to 0.5.0-beta.

## [0.4.0-beta] - 2026-04-27

### Added
- `--dry-run` flag (fetch / generate) — prints which PRs would be fetched from local `git log` without calling the GitHub API or writing files
- `--summary-timeout` flag — configurable LLM timeout (default 300s, range 10–3600s); supersedes the previous hardcoded 120s
- `--log-file PATH` flag — append logs to a file in addition to stderr (useful for CI runs)
- `_safe_stderr()` now scrubs `ghp_/gho_/ghu_/ghs_/ghr_` token shapes from any subprocess stderr before logging (defense-in-depth)
- 64KB cap on PR body size before regex/string extraction
- Trust-boundary diagram and expanded threat model in ARCHITECTURE.md (LLM prompt-injection row, symlink/`@filepath` row, GraphQL injection row, subprocess-stderr row)
- New top-level docs: `SECURITY.md` (vulnerability disclosure) and `CONTRIBUTING.md` (dual-license policy + SHA-pin policy + dev workflow)
- `pyproject.toml` (pytest / ruff / mypy config — replaces `sys.path.insert` hack in tests) and `Makefile` (test / sbom / lint / typecheck)
- `reports/hints/prior_release_themes.txt` — extracted intro paragraphs from the prior 26.05.0 render, used as `--summary-hint @reports/hints/prior_release_themes.txt` to keep theme/sentiment stable across mid-cycle re-runs
- New CI workflow `.github/workflows/test.yml` runs pytest on Python 3.10/3.11/3.12 for every push and PR
- Concurrency control on `sbom.yml` to prevent racing `git push`es
- 14 new tests (163 total): label-sort determinism, title-tiebreak determinism, GraphQL variable shape, stderr token redaction, body size cap, summary-timeout bounds, merge drop warning, dry-run

### Changed
- **Categorization is now deterministic.** `_categorize_by_labels` and `_categorize_by_title` previously depended on GitHub's label-return order or Python dict iteration order to break ties; both now break ties via `SIG_CANONICAL_ORDER` for stable, run-to-run consistent output.
- GraphQL queries to the GitHub API now use server-side variables (`$owner`, `$name`) instead of string interpolation — `gh api graphql -f query=… -f owner=… -f name=…`. Owner/name validation remains in place; this removes the interpolation surface entirely.
- All subprocess calls (`git`, `gh`, summary command) now pass `encoding='utf-8', errors='replace'` so non-UTF-8 locales cannot corrupt decoded output.
- `merge_with_existing()` now logs a warning when prior-JSON PRs are dropped without a `manual_override_*` flag — direct edits to `description` / `sig_category` are still silently lost (documented behavior), but the user is no longer surprised by it.
- Default `--summary-cmd` lowered from `qwen2.5:32b` (~24GB VRAM) to `qwen2.5:14b` (~12GB VRAM) for a more reasonable out-of-box experience. The README LLM-options table now lists `qwen2.5:32b` first for users with the headroom.
- GitHub Actions in `.github/workflows/sbom.yml` are now pinned to commit SHAs instead of floating `@v4` / `@v5` tags.
- Version bumped to 0.4.0-beta

### Security
- Eliminated GraphQL string-interpolation surface (owner/name are now query variables)
- Added stderr token-shape scrubbing as defense-in-depth against accidental token leak in CI logs
- Bounded PR body size and summary-command runtime
- Pinned GitHub Actions to commit SHAs

## [0.3.0-beta] - 2026-04-21

### Added
- `--summary-hint` flag to steer the LLM narrative — accepts inline text or `@filepath` to read from a file
- Clickable GitHub PR links in rendered markdown output
- LLM output cleaner (`_clean_summary()`) that strips preamble text and `---` dividers
- ANSI escape code stripping for terminal-based LLM tools (e.g., ollama)
- `--nowordwrap` in default ollama command to prevent word wrapping artifacts
- PR number bounds validation (1-999999) and batch_size validation (1-100)
- Consistent error message truncation via `_safe_stderr()` (200 char max)
- `shlex.split()` for safe summary command parsing (supports quoted arguments)
- `reports/` directory with example output from a full multi-repo run
- PR descriptions now built from PR body's first meaningful paragraph (filters bullet lists, images, template noise; combines with title when body lacks context)
- SIG file path patterns rebuilt from `.github/CODEOWNERS` with longest-match-wins logic
- ROS2/SimulationInterfaces file paths and keywords mapped to sig/simulation
- LLM postamble stripping (self-explanatory paragraphs from chatty LLMs)
- 62 new tests (149 total) for PR validation, description building, body extraction, hint resolution, ANSI stripping, ROS2 categorization, and edge cases

### Changed
- PR references now render as clickable markdown links (e.g., `[o3de#19709](https://github.com/o3de/o3de/pull/19709)`)
- Summary prompt passed via stdin instead of `-p` flag for universal LLM compatibility
- Default summary command updated to `ollama run --nowordwrap qwen2.5:32b`
- `generate` subcommand no longer requires `--input-json` (set automatically from `--output-json`)
- Version bumped to 0.3.0-beta

## [0.2.0-beta] - 2026-04-21

### Added
- Multi-repo support: each repo can have its own local clone via `--repo-path owner/repo=/path/to/clone`
- `--default-repo-path` flag for setting the fallback clone path when no explicit mapping is given
- Automated narrative summary generation via `--generate-summary` flag (default: off)
- `--summary-cmd` flag to configure the LLM command (default: `ollama run --nowordwrap qwen2.5:32b`)
- Summary prompt builder that groups PRs by SIG with truncation for large sections
- 18 new unit tests for multi-repo parsing, summary prompt building, and summary generation

### Changed
- `--repo-path` now accepts per-repo mappings in `owner/repo=/path` format
- Schema version bumped to 2 (v1 JSON files are still accepted for backward compatibility)
- JSON metadata now includes `repo_paths` mapping for traceability
- Version bumped to 0.2.0-beta

### Removed
- Single-path `--repo-path` positional behavior replaced by `--default-repo-path`

## [0.1.0-beta] - 2026-04-21

### Added
- Three-stage release notes pipeline: Extract (git log), Categorize (SIG labels/heuristics), Render (markdown)
- Three CLI subcommands: `fetch`, `render`, `generate`
- GraphQL batched PR fetching via `gh` CLI (zero external Python dependencies)
- SIG categorization by GitHub labels, title keyword heuristics, and file path heuristics
- Incremental update support with manual override preservation (`manual_override_sig`, `manual_override_description`)
- Cherry-pick and stabilization-sync PR detection and filtering
- AI-agent friendly JSON intermediate format with schema versioning
- CycloneDX 1.5 SBOM generation (`generate_sbom.py`) with source file SHA-256 hashes
- GitHub Action for automatic SBOM regeneration on push (`.github/workflows/sbom.yml`)
- 87 unit tests covering validation, categorization, rendering, merging, and I/O
- OWASP Top 10 and NIST SP 800-53 aligned security controls
- Atomic file writes for crash-safe output
- Input validation on all user-supplied values (git refs, repo slugs, file paths)
- PR title sanitization to prevent markdown injection
- Dual licensing (Apache-2.0 OR MIT) matching the O3DE project

### Known Limitations
- `--force-recategorize` flag is documented in the plan but not yet implemented
