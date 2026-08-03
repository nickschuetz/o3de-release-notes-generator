# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.2-beta] - 2026-08-03

### Fixed
- **The point-release audit reported a false green.** `_maybe_write_pointrelease_audit()` built its "present in report" set from the collected JSON, while the renderer applied flag, release-machinery, and uncategorized filters the audit knew nothing about. A bundled fix that was collected but filtered out therefore showed a ✓. The control designed to prove no point-release fix was lost could certify a loss as fine.

### Changed
- **`classify_for_report()` is now the single source of truth for report membership.** It maps each PR to the reason it is kept out, or `None` if it renders. `summarize_render_coverage()` and the point-release audit both read it, so the reconciliation counts and the audit cannot disagree about what is in the report.
- **The audit sidecar distinguishes three states instead of two:** ✓ rendered, ⚠ collected but filtered out (with the reason), ✗ not found at all. The ⚠ state is the one that matters: the fix shipped in a point release, so a reader expects it in the next major's notes. The summary line counts all three and says "Action required before publishing" when either non-green state is non-empty.
- 5 new tests (323 -> 328).

## [0.6.1-beta] - 2026-08-03

### Security
- `_safe_stderr()` now also scrubs fine-grained personal access tokens (`github_pat_…`). The pattern previously covered only the classic `ghp_/gho_/ghu_/ghs_/ghr_` shapes, so a fine-grained token appearing in subprocess stderr would have been logged verbatim. Documented as covered in SECURITY.md; it was not.

### Fixed
- **README examples were wrong by default.** Nine of eleven `fetch` / `generate` examples, including the Quick Start, omitted `--exclude-json`. Copy-pasting the Quick Start produced a 369-PR window of which 188 had already shipped in 26.05.0, which is the exact failure 0.6.0-beta was written to prevent. Every example now carries the flag and writes to a per-release output path.
- Quick Start comment claimed "everything since 26.05.0", which is what the command did *not* do without the exclusion flag.
- Example figures were internally inconsistent: the JSON schema block claimed `pr_count: 419` with a categorization summary summing to 419, and the reconciliation sample showed 419/402. Both now use the real post-exclusion numbers (201 = 181 `o3de` + 20 `o3de-extras`) and add up.
- Sample Output described a 369-PR run; that is the pre-exclusion figure.
- Narrative-summary docs omitted that release-machinery PRs are excluded from the prompt, and that summary output has HTML tag openers escaped.
- `-v` was documented without its `--verbose` long form.
- AGENTS.md still described point-release tags with the three-component `X.Y.N` notation; they are two-component.

### Changed
- **Architecture diagrams redrawn.** The pipeline diagram predated the ref preflight, the prior-release exclusion stage, and render reconciliation; the incremental-flow diagram did not show exclusion being re-applied after the merge. The trust-boundary diagram gains the `--exclude-json` source as a trusted local input, notes that atomic writes fsync and preserve mode, and has its box borders realigned.
- SECURITY.md, AGENTS.md, and CONTRIBUTING.md updated for the widened token scrub, single-pass markdown/HTML escaping, subprocess timeout handling, and permission-preserving atomic writes.
- 7 new tests (305 -> 312) covering every token shape the scrubber claims to handle.
- **`TestDocumentationAccuracy` (11 checks, 312 -> 323 tests).** The doc drift this release fixed was all mechanically detectable, so it is now detected mechanically: every CLI flag must appear in the docs, the README's JSON example must parse and its `categorization_summary` must sum to its `pr_count`, the documented `schema_version` must match the constant, relative links must resolve, diagram box runs must be equal width, and every `fetch`/`generate` example must carry `--exclude-json` (opt out per block with `# doc-check: exclusion-not-applicable`). Each check was mutation-tested to confirm it fails when the corresponding claim is broken. Deliberately excluded as too brittle to last: the exact test count (asserted as a `300+` floor instead) and anything that parses prose. CHANGELOG.md is exempt, being an append-only record of past states.

## [0.6.0-beta] - 2026-08-03

Accuracy-focused release ahead of the O3DE 26.10.0 cycle. Three defects in this
group caused real content loss in the shipped 26.05.0 notes; re-running against
the same window recovers 55 PRs (188 rendered -> 243).

### Fixed
- **Workflow `sync/*` labels no longer delete PRs from the report.** `detect_pr_flags()` flagged any PR whose label merely *contained* the substring `sync`, which matched O3DE's workflow-tracking labels (`sync/to-stabilization`, `sync/to-development`, `need-sync/to-development`). Those labels sit on the original substantive PR, not on a sync container, so 57 of the 256 PRs in the 26.05.0 corpus (22%) were silently excluded, among them "Fixes blendshapes not working", "Fix Clang20 compile errors", and "Fix call to single-device function in multi-device RayTracingTlas". No O3DE label distinguishes a container from an ordinary PR, so labels are no longer consulted at all; only title evidence flags a cherry-pick. Rendering ignores the legacy flag, so JSON written by older versions renders correctly with no re-fetch.
- **Merge-commit PRs are no longer invisible.** `git log` ran with `--no-merges` and only matched the squash-merge form `(#NNNN)`, but O3DE `development` uses merge commits for a large minority of PRs (`Merge pull request #NNNN from ...`, no parentheses) whose constituent commits carry no PR reference at all. 19 PRs in the `2605.0..development` window were unreachable. Merges are now included and matched by `MERGE_COMMIT_PR_PATTERN`; the count discovered this way is logged.
- **Descriptions are escaped exactly once.** The combined title-plus-body path escaped an already-escaped title, turning `\[` into `\\[`, which markdown renders as a literal backslash followed by an *unescaped* bracket. Three bullets in the shipped 26.05.0 notes carried the artifact.
- **Over-long first paragraphs fall back to the title.** `_extract_first_paragraph()` pre-truncated to exactly 300 characters, so the `>300 -> use the title` guard in `_build_pr_description()` was dead code. 37 of 256 descriptions ended mid-sentence, several on a severed URL. Length policy now lives solely in `_build_pr_description()` (`MIN_DESCRIPTION_CHARS` / `MAX_DESCRIPTION_CHARS`).
- **Repeated mapping flags accumulate.** `--repo-path` (and the new ref flags) used bare `nargs='*'`, so the repeated-flag form documented in the README kept only the last occurrence and every other repo silently fell back to `--default-repo-path`. All mapping flags now use `action='extend'`, supporting both `--flag a=1 b=2` and `--flag a=1 --flag b=2`.
- **Subprocess timeouts no longer abort a run.** `subprocess.TimeoutExpired` escaped `extract_pr_numbers_from_git_log()`, `fetch_pr_metadata_batch()`, and `_check_gh_available()`, killing a run with a traceback and discarding every batch already fetched. All call sites now convert `SubprocessError` / `OSError` into handled errors.
- **Atomic writes preserve permissions and durability.** `tempfile.mkstemp()` creates 0600 and `os.replace()` preserved it, so every output was silently downgraded to owner-only (the committed `sbom.cdx.json` was 0600 on disk). The destination's mode is now mirrored, and content is `fsync`ed before the rename so a crash cannot leave a zero-length file.

### Added
- **Render reconciliation accounting.** `summarize_render_coverage()` partitions every input PR into `rendered` plus mutually exclusive `excluded_*` buckets; `log_render_coverage()` prints the totals and warns whenever anything is dropped. The 26.05.0 regression went unnoticed precisely because nothing reported this.
- **Raw HTML escaping.** Markdown renderers used to publish O3DE notes pass raw HTML through, so `<img src=x onerror=...>` in an untrusted PR title would become live HTML on a published page. Tag-like `<` is now escaped in titles, body-derived descriptions, and LLM narrative output; ordinary arrows (`64->32`) stay readable.
- **`--exclude-json`:** drops PRs already reported in a prior release from the window, before any GitHub call, and again after the incremental merge. Required for a correct major-release window: a tag on the `main` line shares only an ancient merge-base with `development` (2025-07-29 for `2605.0`, before the 26.05 cycle began), so `2605.0..origin/development` spans two cycles. 188 of 369 `o3de/o3de` PRs and 30 of 50 `o3de/o3de-extras` PRs in the 26.10.0 window had already shipped in 26.05.0. The duplicates are development-side merges of fixes that reached the prior release by cherry-pick into its stabilization branch, so they are unreachable from the tag; neither a different ref (`origin/main` gives an identical 369/188) nor a date cutoff separates them, because the two sets interleave in time. Sources and per-repo counts are recorded in `metadata.excluded_prior_releases`. Pointing the flag at the run's own `--output-json` is refused.
- **Per-repo git refs:** `--repo-from-ref` / `--repo-to-ref` accept `owner/repo=REF`. Release lines are not tagged uniformly (`o3de/o3de` carries `2605.0`, `o3de/o3de-extras` does not), and a single global ref aborts the whole multi-repo run on the untagged repo.
- **Ref preflight.** `verify_refs_exist()` resolves every `(repo, ref)` pair with `git rev-parse --verify` before any git log or API work and reports each failure with its remedy.
- **`metadata.tool_version`** records the generating version, and `metadata.repo_refs` records per-repo ranges when they differ from the global ones.
- `generate_sbom.py --check` and `make sbom-check`: exit non-zero when the committed SBOM is stale. Wired into CI.
- `RELEASE_RUNBOOK.md`: step-by-step procedure for running a release cycle.
- 81 new tests (224 -> 305).

### Changed
- **Schema version bumped 3 -> 4.** Adds `metadata.tool_version`; `flags` no longer carries `stabilization-sync` and descriptions are no longer truncated mid-sentence, so data written by <=0.5.0-beta is structurally readable but semantically stale. Schema 3 files still load; re-fetch for accuracy.
- **SBOM is deterministic and self-describing.** The stdlib inventory is discovered by `ast`-parsing the sources instead of a hand-maintained list that had drifted (it omitted `contextlib`, `shlex`, and `typing`). Components carry `bom-ref` so `dependsOn` resolves instead of dangling. Purls moved from `pkg:pypi/cpython-stdlib/...` (a package that does not exist on PyPI) to `pkg:generic/`. The substantive document carries no wall-clock value and no running-interpreter version, so regeneration is a no-op when nothing changed, and CI stops committing a timestamp-only SBOM on every push.
- Documentation corrected throughout: the incremental flow re-fetches the full range (it never fetched "new PRs only"), title and body are joined with a colon (not an em dash), point-release tags are two-component, and examples target 26.10.0.

## [0.5.0-beta] - 2026-05-20

### Added
- **Point-release audit sidecar.** When `--from-ref` is a non-zero point-release tag (e.g. `2510.2`), detects cherry-pick container PRs on the previous stabilization branch (titles matching `cherry-pick … from dev`, `merging point-release …`, etc.), parses the bundled PR numbers from each container's commit body, and writes `<output-md-stem>_pointrelease_audit.md` next to the rendered report: a ✓/✗ checklist showing whether each bundled fix is also present in the rendered report via its development-side merge. Turns the manual "did we lose anything?" check into an auditable artifact. Suppress with `--no-pointrelease-audit`.
- **Merge-base metadata** in `release_data.json`: per-repo `merge_bases` (sha + committer_date) and aggregate `effective_window` (start = earliest merge-base date across repos, end = generated_at). Anchors the diff's time window to the actual fork point, matching the date PR-curators typically reference in their release-notes PR descriptions.
- **Point-release awareness log line.** When `--from-ref` is a point-release tag with earlier siblings (e.g. `2510.1`, `2510.2`), one `INFO` line explains the merge-base equivalence between the major tag (`2510.0`) and the point-release tag against `--to-ref`, so re-runs don't relearn the lesson.
- **Release-machinery classifier.** Tags PRs whose title clearly indicates release engineering (version bumps, SBOM auto-updates, cherry-pick-to-pointrelease containers, "merging pointrelease into main", etc.) or whose entire file diff is unambiguous machinery (`engine.json` / `sbom.cdx.json` / `version.txt`) with `release_machinery: True`. Default-excluded from rendered markdown and summary prompts so the report stays focused on product changes; opt back in with `--include-release-machinery` (use this for point-release notes where machinery IS the content). The file-only heuristic deliberately excludes `.github/workflows/`-only PRs to avoid filtering real CI improvements.
- New helpers: `parse_point_release_tag`, `find_sibling_point_release_tags`, `extract_merge_base`, `extract_pointrelease_containers`, `write_pointrelease_audit`, `is_release_machinery`, `_emit_point_release_awareness_log`, `_maybe_write_pointrelease_audit`.
- New CLI flags: `--no-pointrelease-audit` (fetch / generate), `--include-release-machinery` (render / generate).
- 61 new tests (163 → 224) across `TestSchemaVersion`, `TestParsePointReleaseTag`, `TestFindSiblingPointReleaseTags`, `TestExtractMergeBase`, `TestExtractPointreleaseContainers`, `TestWritePointreleaseAudit`, `TestIsReleaseMachinery`, `TestRenderMarkdownExcludesMachinery`, `TestBuildSummaryPromptExcludesMachinery`, `TestEmitPointReleaseAwarenessLog`.

### Changed
- **Schema version bumped 2 → 3.** New `release_machinery` field on each PR; new metadata fields `merge_bases`, `effective_window`, `release_machinery_count`. `load_existing_json` continues to accept schema 2; no migration step required for existing JSON files.
- `render_markdown()` and `_build_summary_prompt()` now accept `include_release_machinery: bool = False` and filter PRs flagged `release_machinery` by default.
- `.gitignore` cleaned up: the dead `reports/release_data.json` rule was inert (the file is tracked despite the rule) and has been removed; `reports/*.log` is now ignored to keep `--log-file` outputs out of commits.
- Version bumped to 0.5.0-beta.

## [0.4.0-beta] - 2026-04-27

### Added
- `--dry-run` flag (fetch / generate): prints which PRs would be fetched from local `git log` without calling the GitHub API or writing files
- `--summary-timeout` flag: configurable LLM timeout (default 300s, range 10–3600s); supersedes the previous hardcoded 120s
- `--log-file PATH` flag: append logs to a file in addition to stderr (useful for CI runs)
- `_safe_stderr()` now scrubs `ghp_/gho_/ghu_/ghs_/ghr_` token shapes from any subprocess stderr before logging (defense-in-depth)
- 64KB cap on PR body size before regex/string extraction
- Trust-boundary diagram and expanded threat model in ARCHITECTURE.md (LLM prompt-injection row, symlink/`@filepath` row, GraphQL injection row, subprocess-stderr row)
- New top-level docs: `SECURITY.md` (vulnerability disclosure) and `CONTRIBUTING.md` (dual-license policy + SHA-pin policy + dev workflow)
- `pyproject.toml` (pytest / ruff / mypy config; replaces `sys.path.insert` hack in tests) and `Makefile` (test / sbom / lint / typecheck)
- `reports/hints/prior_release_themes.txt`: extracted intro paragraphs from the prior 26.05.0 render, used as `--summary-hint @reports/hints/prior_release_themes.txt` to keep theme/sentiment stable across mid-cycle re-runs
- New CI workflow `.github/workflows/test.yml` runs pytest on Python 3.10/3.11/3.12 for every push and PR
- Concurrency control on `sbom.yml` to prevent racing `git push`es
- 14 new tests (163 total): label-sort determinism, title-tiebreak determinism, GraphQL variable shape, stderr token redaction, body size cap, summary-timeout bounds, merge drop warning, dry-run

### Changed
- **Categorization is now deterministic.** `_categorize_by_labels` and `_categorize_by_title` previously depended on GitHub's label-return order or Python dict iteration order to break ties; both now break ties via `SIG_CANONICAL_ORDER` for stable, run-to-run consistent output.
- GraphQL queries to the GitHub API now use server-side variables (`$owner`, `$name`) instead of string interpolation: `gh api graphql -f query=… -f owner=… -f name=…`. Owner/name validation remains in place; this removes the interpolation surface entirely.
- All subprocess calls (`git`, `gh`, summary command) now pass `encoding='utf-8', errors='replace'` so non-UTF-8 locales cannot corrupt decoded output.
- `merge_with_existing()` now logs a warning when prior-JSON PRs are dropped without a `manual_override_*` flag. Direct edits to `description` / `sig_category` are still silently lost (documented behavior), but the user is no longer surprised by it.
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
- `--summary-hint` flag to steer the LLM narrative; accepts inline text or `@filepath` to read from a file
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
