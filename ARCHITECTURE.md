# Architecture

## Overview

The release notes generator is a standalone Python project with zero external dependencies. It consists of two main scripts:

- **`release_notes.py`** - Pipeline (preflight, extract, exclude, fetch, categorize, render) that generates O3DE release notes from merged pull requests. The intermediate JSON is schema v6.
- **`generate_sbom.py`** - Generates a CycloneDX 1.5 SBOM for supply chain transparency.

Both scripts use only Python stdlib modules and interact with external systems (git, GitHub API) exclusively through the `gh` CLI and `git` commands via `subprocess` with list arguments.

```
   Local git clones                     prior release report(s)
   (read-only, per-repo)                via --exclude-json
          │                                      │
          ▼                                      ▼
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────────┐
   │  Preflight  │──▶│   Extract   │──▶│   Exclude   │──▶│    Fetch     │──▶ GitHub
   │ rev-parse   │   │ git log:    │   │ drop PRs    │   │ gh CLI,      │    GraphQL
   │ every       │   │ squash AND  │   │ already in  │   │ GraphQL,     │    API
   │ (repo, ref) │   │ merge-      │   │ a prior     │   │ 30 PRs/req   │
   │ before any  │   │ commit      │   │ report      │   │              │
   │ work        │   │ patterns;   │   │             │   │              │
   │             │   │ merge-base  │   │             │   │              │
   └─────────────┘   └─────────────┘   └─────────────┘   └──────┬───────┘
                                                                │
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐       │
   │    Render    │◀──│   JSON v6    │◀──│  Categorize  │◀──────┘
   │ markdown by  │   │ (editable;   │   │ 1. labels    │
   │ SIG; filters │   │  human or AI │   │ 2. title     │
   │ flags and    │   │  sets        │   │ 3. files     │
   │ machinery;   │   │  manual_     │   │ + release-   │
   │ reconciles   │   │  override_*) │   │   machinery  │
   │ every PR;    │   │              │   │   flag       │
   │ optional LLM │   │              │   │              │
   │ summary      │   │              │   │              │
   └──────┬───────┘   └──────────────┘   └──────────────┘
          │
          ▼
   .md release notes  +  point-release audit sidecar
   (when --from-ref is a point-release tag with a non-zero patch)
```
## Project Components

### `release_notes.py`

The main script. Three subcommands (`fetch`, `render`, `generate`) exposed via `argparse`.

**Key data structures:**
- `SIG_TITLE_KEYWORDS` - Dict mapping SIG names to title keyword lists for heuristic categorization.
- `SIG_FILE_PATH_PATTERNS` - Dict mapping SIG names to file path prefixes for heuristic categorization.
- `SIG_CANONICAL_ORDER` - List defining the fixed section ordering in rendered markdown.
- `CHERRY_PICK_PATTERNS` - Regex list that flags PR titles as cherry-pick containers (filtered from rendered output via the per-PR `flags` field). **Title evidence only.** Labels are deliberately not consulted: no O3DE label distinguishes a sync container from an ordinary PR (`sync/to-stabilization` sat on 30 ordinary PRs and 2 containers in the 26.05.0 corpus), and a substring match on it previously deleted 57 real changes from the report.
- `EXCLUDED_FLAGS` - The single source of truth for which `flags` values remove a PR from the report and the summary prompt. The legacy `stabilization-sync` value is absent, so JSON written by older versions renders correctly without a re-fetch.
- `load_prior_release_pr_keys()` / `_apply_prior_release_exclusion()` - Read `(repo, number)` pairs from prior release reports and filter the window. Deliberately lenient about schema version, since only `repo` and `number` are read.
- `MERGE_COMMIT_PR_PATTERN` - Matches `Merge pull request #NNNN`, the only place a merge-commit PR's number appears. Required alongside `PR_NUMBER_PATTERN`; see "Stage 1: Extract".
- `POINTRELEASE_CONTAINER_PATTERNS` - Regex list (subset of cherry-pick patterns specialised for *containers*: commits whose bodies enumerate bundled PRs via the `(#NNNN)` convention). Used by `extract_pointrelease_containers()` when writing the audit sidecar.
- `POINT_RELEASE_TAG_PATTERN` - Compiled regex matching `X.Y` style tags (e.g. `2510.2`) so the tool can detect point-release refs and emit the awareness log line / audit sidecar.
- `RELEASE_MACHINERY_TITLE_PATTERNS` - Regex list matching titles that clearly indicate non-product PRs (`Update version`, `Update SBOM`, `Update Linux GPG key`, `Cherry pick … pointrelease`, `Merge … pointrelease into main`, etc.).
- `RELEASE_MACHINERY_FILE_PATTERNS` - Narrow file-path patterns (`engine.json` / `sbom.cdx.json` / `version.txt` / `.github/FUNDING.yml`). Used by `is_release_machinery()` only when ALL changed files match. Deliberately excludes `.github/workflows/` and the rest of `.github/` so real CI and template work by SIGs isn't filtered. `FUNDING.yml` is listed as the exact file because repository governance is owned by the TSC, not by a SIG: the notes are organised entirely by SIG, so there is no correct heading for it. Classifying it here makes the exclusion a decision rather than a classification failure, which keeps it out of the uncategorized triage list every cycle.

**Multi-repo support:** The `parse_repo_path_mappings()` function resolves per-repo local clone paths. Each repo can have its own clone via `--repo-path owner/repo=/path`, with `--default-repo-path` as the fallback. `parse_repo_ref_mappings()` does the same for git refs via `--repo-from-ref` / `--repo-to-ref`, which exist because release lines are not tagged uniformly: `o3de/o3de` carries `2605.0` while `o3de/o3de-extras` does not, and a single global ref would abort the whole run on the untagged repo. All mapping flags use `action='extend'`, so both `--flag a=1 b=2` and `--flag a=1 --flag b=2` accumulate.

**Preflight:** `verify_refs_exist()` resolves every `(repo, from-ref)` and `(repo, to-ref)` pair with `git rev-parse --verify` before any git log or API work, and reports each failure with the remedy. This converts a mid-run abort, potentially after minutes of GitHub calls, into an actionable error at second zero.

**Report membership:** `classify_reasons()` returns one exclusion reason (or `None`) per PR, positionally aligned with the input list. It is the only place the filter chain exists. `render_markdown()`, `_build_summary_prompt()`, and `summarize_render_coverage()` all read it, so a filter added to one is visible to all three; each previously kept a private copy, which is how the renderer and the point-release audit came to disagree about what was in the report. `classify_for_report()` is a keyed `(repo, number)` view over the same result, used only by the audit, which looks PRs up by number. Membership itself stays positional: keying it would let two entries sharing a key silently inherit one decision.

**Reconciliation:** `summarize_render_coverage()` partitions the input PR list into `rendered` plus one mutually exclusive `excluded_*` bucket per reason, and `log_render_coverage()` emits it (WARNING when anything was dropped). The counts sum to the total by construction, so a filter regression cannot hide.

**Summary generation:** The `generate_summary()` function builds a structured prompt from categorized PR data and passes it via stdin to a configurable LLM command via subprocess (list args, no `shell=True`). Default: `ollama run --nowordwrap qwen2.5:14b` (local, ~12 GB VRAM); also supports `qwen2.5:32b` for ~24 GB hosts and `claude -p` (cloud). The `_clean_summary()` function strips LLM preamble text and dividers from the output. Command is parsed via `shlex.split()`. Optional `--summary-hint` injects release manager guidance into the prompt; it accepts inline text or `@filepath` to read from a file (resolved via `_resolve_hint()`). Enabled via `--generate-summary`; disabled by default. PRs flagged `release_machinery: True` are excluded from the prompt unless `--include-release-machinery` is set, so the LLM stays focused on product changes.

**Point-release awareness and audit:** When `--from-ref` parses as a point-release tag with a non-zero patch (e.g. `2510.2`), `_emit_point_release_awareness_log()` runs `git merge-base` against the major sibling tag (`2510.0`) and `--to-ref`; when the merge-bases match, it logs a single `INFO` line so future runs don't relearn the equivalence. `_maybe_write_pointrelease_audit()` then iterates per repo, calls `extract_pointrelease_containers()` to find cherry-pick container PRs between the major and point-release tags, parses bundled PR numbers from each container's commit body, and writes a `<output-md-stem>_pointrelease_audit.md` sidecar with a ✓/✗ checklist for every bundled fix vs the rendered report. Suppressed via `--no-pointrelease-audit`.

**Merge-base metadata:** `extract_merge_base()` runs `git merge-base <from-ref> <to-ref>` and `git show -s --format=%cI <sha>` per repo, returning `(sha, committer_date)`. Results land in `release_data.json` under `metadata.merge_bases`; the earliest committer-date across repos plus the run's `generated_at` form `metadata.effective_window`. Anchors the diff to the actual fork point, usually the date PR-curators reference in their release-notes PR description.

### `generate_sbom.py`

Generates a CycloneDX 1.5 JSON SBOM (`sbom.cdx.json`). Captures project metadata, Python stdlib module inventory, and SHA-256 hashes of all source files.

### `tests/test_release_notes.py`

Unit tests using `pytest` and `unittest.mock`. No network calls; every `gh` / `git` / LLM invocation is mocked. Covers input validation (including injection attempts and stderr token redaction across all six token shapes), multi-repo path and ref parsing, repeatable mapping flags, SIG categorization (labels, title heuristics, file heuristics, priority ordering, deterministic tiebreaks), GraphQL variable shape, batch-failure classification and backoff, file-list truncation recording, summary prompt building, summary generation (success, failure, timeout, timeout-bounds validation), markdown and HTML escaping, description length policy, markdown rendering (with and without summary, with release-machinery filtering), render-coverage reconciliation, incremental merging with manual-override preservation and drop warnings, `--reuse-existing` cache eligibility and field re-derivation, `--log-file` validation, prior-release exclusion, dry-run behavior, atomic file I/O and mode preservation, SBOM integrity and determinism, JSON loading/validation, PR body size capping, point-release tag parsing, sibling-tag discovery, merge-base extraction, cherry-pick container parsing, audit sidecar generation against the rendered set, release-machinery classification (title + file-path heuristics), point-release awareness log line, and documentation accuracy (see below).

`TestDocumentationAccuracy` checks the docs against the code rather than against a reviewer's memory: every CLI flag must appear in the docs, the README's JSON example must parse and be internally consistent, the documented schema version must match `SCHEMA_VERSION` (in both JSON and prose form, and against every superseded version, not just the previous one), relative links must resolve, ASCII diagram box runs must be equal width, and every `fetch`/`generate` example must carry `--exclude-json`. Each check was mutation-tested to confirm it fails when the claim it guards is broken.

### `.github/workflows/sbom.yml`

GitHub Action that regenerates `sbom.cdx.json` on every push to `main` that changes Python source files. Commits the updated SBOM back to the repository automatically.

## Data Flow

### Stage 1: Extract

**Input:** Local git repositories (read-only, one per repo), two git references (tag/branch).

**Process:**
1. Resolves per-repo local clone paths via `parse_repo_path_mappings()`.
2. Resolves per-repo refs via `parse_repo_ref_mappings()` and preflights them with `verify_refs_exist()`.
3. For each repo, runs `git log --format=%s <from>..<to>` via `subprocess.run()` with list arguments against that repo's local clone. **Merge commits are included on purpose.**
4. Parses PR numbers from commit subjects with two patterns: `\(#(\d+)\)` for squash merges and `^Merge pull request #(\d+)` for merge commits. O3DE uses both strategies on `development`; a merge-commit PR's constituent commits carry no PR reference, so excluding merges lost those PRs entirely (19 of them in the 26.05.0 → 26.10.0 window). The number found via merge commits is logged.
5. Deduplicates and sorts per repo.
6. Drops PR numbers listed in any `--exclude-json` source. A release tag on the `main` line shares only an ancient merge-base with `development` (2025-07-29 for `2605.0`), so the raw window spans two release cycles; 188 of 369 PRs in the 26.10.0 window had already shipped in 26.05.0. The duplicates are development-side merges of fixes that reached the prior release by cherry-pick, so they are unreachable from the tag and cannot be separated by ancestry or by date. Exclusion happens before any GitHub call, and again after the incremental merge so a stale entry in an existing output JSON cannot reintroduce one.

**Output:** Sorted list of PR numbers per repo.

**Trust boundary:** The git log output is from local repositories the user controls. PR numbers are parsed as integers, preventing injection. Repo path mappings are validated for format before use.

### Stage 2: Fetch + Categorize

**Input:** PR numbers per repo, GitHub repo slug(s).

**Process:**
1. For each repo, constructs GraphQL queries batching up to 30 PRs per request (~8 requests for a typical release of ~230 PRs). Queries fetch title, body, labels, files, author, and merge date. The query uses GraphQL variables (`$owner`, `$name`) instead of string interpolation, so owner/name never appear in the query body.
2. Executes via `gh api graphql -f query=… -f owner=… -f name=…` (subprocess with list args). Each repo's PRs are fetched from the correct GitHub owner/repo. Batch failures are classified before retrying: an unresolvable PR number is permanent, so it is parsed out of stderr, dropped, and the batch retried once; a transient failure (rate limit, 5xx, connection reset) backs off exponentially up to `MAX_BATCH_ATTEMPTS`. Falling back to one request per PR is the last resort, since responding to a rate limit with 30 more requests is the worst available move.
3. PR descriptions are built from the PR body's first meaningful paragraph (20-300 chars; skipping template headers, checklists, URLs, images, `<img>` tags, and bullet lists). The body is capped at 64KB before extraction so a pathological body cannot blow up regex/string ops. When the paragraph shares less than 20% word overlap with the title, both are combined with a colon for standalone readability, composed from the raw title and escaped exactly once (escaping twice turned `\[` into `\\[`, which renders as a literal backslash plus an *unescaped* bracket). Falls back to the sanitized title if the body is empty, too short, longer than `MAX_DESCRIPTION_CHARS`, or entirely noise. The over-length case genuinely falls back now: `_extract_first_paragraph()` returns untruncated text and `_build_pr_description()` owns the length policy, where previously the paragraph was pre-truncated to exactly 300 chars and the guard was dead code, producing descriptions that ended mid-sentence on a severed URL.
4. For each PR, categorizes by SIG using three methods in priority order:
   - **Label match:** Checks for `sig/*` GitHub labels. Highest confidence. When multiple SIG labels are present, the SIG earliest in `SIG_CANONICAL_ORDER` wins (deterministic, does not depend on label-return order from GitHub).
   - **Title heuristic:** Matches title keywords against per-SIG keyword maps. Best-keyword-count wins; on ties, the SIG earliest in `SIG_CANONICAL_ORDER` wins.
   - **File path heuristic:** Matches changed file paths against directory-to-SIG maps (derived from `.github/CODEOWNERS`). Uses longest-match-wins: for overlapping patterns (e.g., `AzCore/AzCore/Math/` vs `AzCore/`), the most specific match determines the SIG.
5. Detects flags (cherry-pick, from title evidence only) for filtering.
6. Tags each PR with `release_machinery: True/False` via `is_release_machinery()`. True when the title matches `RELEASE_MACHINERY_TITLE_PATTERNS` (version bumps, SBOM auto-updates, cherry-pick-to-pointrelease wrappers, etc.) **or** when every changed file matches `RELEASE_MACHINERY_FILE_PATTERNS` (a deliberately narrow set: `engine.json` / `sbom.cdx.json` / `version.txt`). Used by Stage 3 to filter non-product PRs out of the rendered report by default.
7. Computes per-repo `merge_bases` via `extract_merge_base()` (sha + committer-date) and aggregates the earliest committer-date into `effective_window.start`. Writes these into `metadata` alongside `schema_version: 6`, `tool_version`, `pr_count`, `release_machinery_count`, and (when `--reuse-existing` is used) `reused_from_cache`.
8. With `--reuse-existing`, PRs categorised by label in the previous report are served from it instead of being re-fetched, and their derived fields are recomputed via `rederive_pr_fields()` so a heuristic change still reaches them. Heuristic and uncategorised PRs are never cached: their `sig/*` label may have been applied since the last run, and caching would freeze a wrong SIG for the cycle. Merges with any existing JSON data, preserving manual overrides. PRs that exist in the prior JSON but no longer appear in `git log` and lack `manual_override_*` are dropped, and a warning is logged so the user notices when this happens. PRs from older JSONs without a `release_machinery` field are backfilled by re-running `is_release_machinery()` against their cached title/files.
9. If `--from-ref` parses as a point-release tag with non-zero patch (e.g. `2510.2`) and `--no-pointrelease-audit` was not set, writes the point-release audit sidecar (see "Point-release awareness and audit" above).

**Output:** Structured JSON with full PR metadata and categorization, plus (optionally) a point-release audit sidecar.

**Trust boundary:** PR data comes from the GitHub API (untrusted). Titles are sanitized before rendering. Labels and file paths are used for categorization only, not interpolated into shell commands.

### Stage 3: Render

**Input:** JSON data from Stage 2, version string, optional summary generation config.

**Process:**
1. If `--generate-summary` is enabled, builds a structured prompt from the PR data and passes it via stdin to the configured LLM command (default: `ollama run --nowordwrap qwen2.5:14b`; or `claude -p` for cloud, or `qwen2.5:32b` for ~24 GB VRAM hosts) via subprocess with list args. LLM preamble text and dividers are stripped from the output. PRs flagged `release_machinery` are excluded from the prompt unless `--include-release-machinery` is set.
2. Groups PRs by SIG category.
3. Filters out PRs carrying a flag in `EXCLUDED_FLAGS` (currently `cherry-pick` only, from title evidence). Sync-label detection was removed: no O3DE label distinguishes a sync container from an ordinary PR, and matching on one deleted 57 real changes from a shipped report.
4. Filters out PRs flagged `release_machinery: True` unless `--include-release-machinery` is set (default off for major releases; turn on for point-release notes where machinery IS the content).
4b. Collapses duplicates: PRs sharing a repo, a normalized title, and an identical changed-file set are rendered once, unless `--include-duplicates` is set. All three signals are required because a title alone recurs on unrelated work across a release window, and a PR with no file list is never collapsed. Each collapsed group is logged by number so the decision can be audited. The point-release audit counts a collapsed duplicate as present, since the change reached the reader through its twin.
5. Renders markdown with fixed SIG ordering matching the established O3DE release notes format.
6. Inserts the LLM-generated narrative summary (or a placeholder if summary generation is disabled or fails).
7. Sanitizes PR titles for markdown (escapes `[`, `]`, `` ` ``, `|`) and for HTML (escapes `<` when it opens a tag, leaving ordinary arrows like `64->32` readable).
8. Emits the reconciliation line accounting for every input PR.

**Output:** Markdown file.

**Trust boundary:** Output is written atomically (`tempfile.mkstemp()` + `fsync` + `os.replace()`), preserving the destination's permission bits. PR titles are sanitized to prevent markdown injection. The summary command is executed via subprocess with list args (no `shell=True`). The LLM's output is inserted as-is into the markdown intro section; it is not interpolated into shell commands or other untrusted contexts.

## Incremental Update Flow

The tool supports re-running throughout the pre-release cycle. By default each run re-fetches every PR in the range from GitHub; batching keeps a ~420-PR cycle to roughly 14 GraphQL requests. `--reuse-existing` serves label-categorised PRs from the previous report instead, cutting a 200-PR run from 8 requests to 4. Either way, manual edits to the JSON (via `manual_override_sig` and `manual_override_description`) are re-applied on top of the resulting data.

```
First run:                       Subsequent runs:

git log (per repo) ──▶ PR #s     git log (per repo) ──▶ PR #s (may have grown)
    │                                │
    ▼                                ▼
drop PRs in --exclude-json       drop PRs in --exclude-json
    │                                │
    ▼                                ▼
GitHub API ──▶ all remaining     with --reuse-existing: serve
    │           PRs                  │  label-categorised PRs from the
    │                                │  previous report, fetch the rest
    ▼                                ▼
categorize ──▶ JSON              merge with existing JSON
    │                            (re-apply manual_override_* fields,
    │                             re-filter against --exclude-json)
    ▼                                │
write JSON                           ▼
    │                            write updated JSON
    ▼                                │
(optional) LLM summary               ▼
    │                            (optional) LLM summary
    ▼                                │
render .md + reconciliation          ▼
                                 render updated .md + reconciliation
```

## SBOM Generation

The `generate_sbom.py` script produces a CycloneDX 1.5 JSON SBOM at `sbom.cdx.json`.

**Contents:**
- Project metadata (name, version, license, repo URL)
- Python stdlib modules declared as dependencies, discovered by `ast`-parsing `SOURCE_FILES` rather than from a hand-maintained list (the old static list had drifted, omitting `contextlib`, `shlex`, and `typing`)
- `bom-ref` on every component, so `dependencies[].dependsOn` resolves instead of dangling
- `pkg:generic/` purls; the previous `pkg:pypi/cpython-stdlib/...` named a package that does not exist on PyPI, which makes scanners report phantom components
- SHA-256 hashes of all source files (`release_notes.py`, `generate_sbom.py`, `tests/test_release_notes.py`)
- Explicit `cdx:externalDependencies: none` property
- Dependency graph linking the project to its stdlib modules

**Determinism:** the substantive document (everything except `metadata.timestamp` and the content-derived `serialNumber`) is a pure function of repository content. It deliberately records the project's minimum Python version rather than `platform.python_version()`, so a 3.12 CI runner and a 3.14 workstation produce identical output. `generate_sbom.py --check` exits non-zero when the committed SBOM is stale, and a plain regeneration is a no-op when nothing substantive changed.

**Automation:** The `.github/workflows/sbom.yml` workflow regenerates the SBOM on every push to `main` that changes `*.py` files. The workflow uses `github-actions[bot]` to commit the updated SBOM, preventing infinite trigger loops (bot commits don't trigger workflows by default). Because regeneration is now a no-op when content is unchanged, the "commit only if changed" guard actually fires; previously the wall-clock timestamp guaranteed a diff and produced an SBOM commit on every qualifying push.

**Atomic writes:** Like the main script, the SBOM generator uses `tempfile.mkstemp()` + `os.replace()` for crash-safe file output.

## Security Model

### Trust Boundaries

```
┌───────────────────────────────────────────────────────────────────────────┐
│                       TRUSTED: local user environment                     │
│                                                                           │
│   user CLI args ────┐                                                     │
│   gh credentials ───┤                                                     │
│   local git repos ──┼──▶ release_notes.py ──▶ output: JSON, .md           │
│   prior report      │            │            (atomic, fsync,             │
│   (--exclude-json) ─┘            │             mode-preserving)           │
│                                  │ subprocess (list args, no shell=True)  │
│        ┌─────────────────────────┼─────────────────────────┐              │
│        ▼                         ▼                         ▼              │
│ ┌────────────┐           ┌────────────┐            ┌─────────────┐        │
│ │ git log /  │           │ gh CLI     │            │ summary cmd │        │
│ │ rev-parse  │           │ (auth via  │            │ (ollama /   │        │
│ │ (read-only)│           │  keyring)  │            │  claude /   │        │
│ │            │           │            │            │  custom)    │        │
│ └────────────┘           └─────┬──────┘            └──────┬──────┘        │
│                                │                          │               │
└────────────────────────────────┼──────────────────────────┼───────────────┘
                                 │                          │
              ═══════════════ trust boundary ═══════════════
                                 │                          │
                    ┌────────────▼──────────┐    ┌──────────▼──────────┐
                    │   GitHub GraphQL API  │    │  LLM (local/cloud)  │
                    │   (PR titles, bodies, │    │  (untrusted output, │
                    │    labels; UNTRUSTED) │    │   escaped into MD)  │
                    └───────────────────────┘    └─────────────────────┘
```

Everything inside the trusted box is data the user controls or gh's credential store. Anything crossing a trust boundary (GitHub API responses, LLM output) is treated as untrusted: validated structurally, sanitized for markdown, and never used to construct shell commands or file paths.

### Threat Model

| Asset | Threat | Mitigation |
|-------|--------|------------|
| GitHub auth token | Exposure in logs or code | Delegated to `gh` CLI credential store; never handled directly. `_safe_stderr()` scrubs both the classic `ghp_/gho_/ghu_/ghs_/ghr_` shapes and fine-grained `github_pat_` tokens from any subprocess stderr before logging (defense-in-depth). Fine-grained PATs are the default for new tokens, so covering only the classic shapes left the common case unredacted. |
| PR titles (untrusted) | Markdown injection in rendered output | Sanitized: `#`, `[`, `]`, `` ` ``, `\|` escaped; trailing PR refs stripped. Escaping runs exactly once; composing an already-escaped string and re-escaping it produced `\\[`, which renders as a literal backslash plus an **unescaped** bracket. |
| PR titles / bodies (untrusted) | **Raw HTML injection** in published output | Markdown renderers used to publish O3DE notes (Hugo/goldmark, GitHub) pass raw HTML through, so `<img src=x onerror=...>` in a PR title would become live HTML on o3de.org. `<` is escaped whenever it opens a tag (`<[a-zA-Z/!?]`); ordinary comparisons and arrows (`64->32`) are left readable. |
| PR titles (untrusted) | LLM prompt injection via summary prompt | Title is inserted as data, not instruction. The summary output is human-reviewed before publishing and is only ever placed in the markdown intro, never executed, never used as a path or command. Worst case: a release manager rejects a tampered narrative. |
| PR bodies (untrusted) | Markdown/HTML injection via body extraction | First paragraph only (20-300 chars); body capped at 64KB before extraction; images, `<img>` tags, bullet lists, and template noise filtered; combined with title only when word overlap <20%; sanitized before rendering |
| Git refs (user input) | Command injection via subprocess | Validated against `^[a-zA-Z0-9._/-]+$`; must not start with `-` |
| Repo slugs (user input) | Command injection | Validated against `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` |
| GraphQL query owner/name | Query injection via string interpolation | Owner and name are passed as GraphQL variables (`$owner`, `$name`) via `gh api graphql -f owner=… -f name=…`; never interpolated into the query string. |
| Output file paths | Path traversal | Resolved via `pathlib.Path.resolve()`; optional base-dir containment check |
| Summary hint file (`@filepath`) | Symlink-following / unbounded read | `pathlib.Path.resolve()` normalises the path; failure logs and returns empty rather than raising. The CLI is a developer-run tool, so the threat is self-DoS rather than escalation. |
| JSON data files | Corruption from interrupted writes | Atomic writes via `tempfile` + `os.replace()` |
| GitHub API responses | Malformed data | Validated structure before use; missing fields default safely |
| LLM summary command | Command injection via `--summary-cmd` | Command parsed via `shlex.split()` (respects shell quoting), executed via subprocess with list args; executable checked via `shutil.which()` before invocation; runtime bounded by `--summary-timeout` (10–3600s). |
| LLM output | Prompt injection in generated narrative | Output is inserted into markdown intro only; not used in shell commands, file paths, or API calls. Tag-like `<` is escaped by `_clean_summary()` so an injected instruction cannot land raw HTML in the published page. Output is reviewed by a human before publishing. |
| Long-running `git` / `gh` calls | Unhandled `TimeoutExpired` aborts a run and discards completed work | Every subprocess call site converts `SubprocessError` and `OSError` into a handled error. A timed-out GraphQL batch degrades to per-PR retries instead of terminating the process with a traceback. |
| Output files | Permission downgrade / truncated file on crash | `tempfile.mkstemp()` creates 0600 and `os.replace()` preserves it, so writes silently made outputs owner-only; the destination's mode is now mirrored explicitly. Content is `fsync`ed before the rename so a crash cannot leave a zero-length file. |
| Git refs that do not exist | Mid-run abort after minutes of API calls | `verify_refs_exist()` preflights every `(repo, ref)` pair before any work and reports the remedy. |
| Subprocess stderr | Sensitive data in CI logs | All subprocess output decoded with `encoding='utf-8', errors='replace'`; stderr passed through `_safe_stderr()` (token-scrub + 200-char truncation) before logging. |
| Supply chain | Undetected dependency changes | CycloneDX SBOM with source file SHA-256 hashes; module inventory derived by `ast`-parsing the sources so it cannot drift; deterministic substantive content makes `generate_sbom.py --check` a real staleness gate in CI; GitHub Actions pinned to commit SHAs (not floating tags). |
| Release report | Silent content loss from an over-matching filter | `summarize_render_coverage()` accounts for every input PR in mutually exclusive buckets and logs a WARNING whenever anything is excluded. |

### OWASP Top 10 Mapping

| OWASP Category | Applicability | Controls |
|----------------|--------------|----------|
| **A03:2021 Injection** | Subprocess calls, markdown output | All subprocess calls use list args (never `shell=True`). All user inputs validated with regex before use. PR titles sanitized for markdown. |
| **A04:2021 Insecure Design** | Overall architecture | Defense-in-depth: validate at input, sanitize at output. Atomic file writes. Fail-closed on validation errors. |
| **A05:2021 Security Misconfiguration** | Secret management | No hardcoded secrets. Auth delegated to `gh` CLI. Preflight check verifies auth status. |
| **A06:2021 Vulnerable and Outdated Components** | Dependencies | Zero external dependencies. Uses only Python stdlib. SBOM tracks all components with SHA-256 hashes. |
| **A07:2021 Identification and Authentication Failures** | GitHub API access | Auth fully managed by `gh` CLI. Script verifies `gh auth status` before making API calls. |
| **A08:2021 Software and Data Integrity Failures** | JSON data, file I/O, supply chain | JSON schema versioned (`schema_version` field). Atomic writes prevent partial/corrupt files. CycloneDX SBOM with file hashes for integrity verification. |
| **A09:2021 Security Logging and Monitoring Failures** | Operational logging | Structured logging (`[LEVEL] o3de.release_notes: message`). Never logs tokens, credentials, or full API response bodies. Logs all validation failures. |

### NIST SP 800-53 Controls

| Control | Implementation |
|---------|---------------|
| **SI-10 (Information Input Validation)** | All external inputs (git refs, repo slugs, file paths) validated with regex patterns and length limits before use. |
| **SI-15 (Information Output Filtering)** | PR titles and body-derived descriptions sanitized for markdown special characters and HTML tag openers before rendering, exactly once. LLM narrative output passes the same filter. Only whitelisted fields from API responses are used. |
| **AU-3 (Content of Audit Records)** | Structured log format with severity levels. Categorization summary, merge-commit discovery count, and a full render reconciliation (rendered vs. each exclusion reason) logged on each run. `metadata.tool_version` records which build produced a given JSON. |
| **SC-28 (Protection of Information at Rest)** | Atomic file writes via `tempfile.mkstemp()` + `fsync` + `os.replace()` prevent data corruption from interrupted writes; the destination's permission bits are preserved rather than downgraded to 0600. |
| **CM-7 (Least Functionality)** | Minimal stdlib-only implementation. Read-only network access, batched at 30 PRs per GraphQL request. No write access to the O3DE repository. |
| **SA-8 (Security and Privacy Engineering Principles)** | CycloneDX SBOM generated and maintained for supply chain transparency. Source file integrity verified via SHA-256 hashes. |

### Input Validation Specifications

| Input | Pattern | Max Length | Additional Checks |
|-------|---------|------------|-------------------|
| Git ref | `^[a-zA-Z0-9._/-]+$` | 256 | Must not start with `-` |
| Repo slug | `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` | 128 | Exactly one `/` |
| Repo path mapping | `^(owner/repo)=(.+)$` | N/A | Repo slug validated separately; path resolved via `pathlib`; `.git` existence checked |
| Repo ref mapping | `^(owner/repo)=(.+)$` | 256 | Repo slug and ref each validated by their own function; ref must resolve via `git rev-parse --verify` in preflight |
| Output path | N/A (uses pathlib) | OS limit | Parent must exist; optional base-dir containment |
| Version string | Free text (user-facing) | N/A | Used only in markdown heading |
| PR number | Parsed as `int()` | 999999 | Must be 1-999999; validated before GraphQL query construction |
| Summary hint | Free text or `@filepath` | N/A | If prefixed with `@`, reads from file; file must exist and be readable; returns empty on failure |
| Summary command | Parsed via `shlex.split()` | N/A | Executable checked via `shutil.which()` before invocation |
| Summary timeout | Integer | N/A | Must be 10–3600 seconds; out-of-range values reject the run |
| PR body | Free text from GitHub API | 64KB | Capped before regex/string operations |

### Subprocess Execution

Every subprocess call uses list arguments:

```python
subprocess.run(['git', 'log', '--format=%s', f'{from_ref}..{to_ref}'], ...)  # merges included
subprocess.run(['git', 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}'], ...)
subprocess.run(['gh', 'api', 'graphql',
                '-f', f'query={query}',
                '-f', f'owner={owner}',
                '-f', f'name={name}'], ...)  # owner/name are GraphQL variables
subprocess.run(['gh', 'auth', 'status'], ...)
subprocess.run(cmd_parts, input=prompt, ...)  # summary generation via stdin
```

No call uses `shell=True`. All calls pass `encoding='utf-8', errors='replace'` so non-UTF-8 locales cannot corrupt decoded output. The `from_ref` and `to_ref` values are validated before interpolation into the argument list, preventing argument injection (e.g., a ref like `--exec=malicious` is rejected by the leading-hyphen check). For GraphQL, owner and name are passed as variables (`$owner`, `$name`) via separate `-f` arguments; they are never interpolated into the query string itself. The summary command is parsed via `shlex.split()` (respects shell quoting) and the executable is verified via `shutil.which()` before invocation. PR numbers are validated to be positive integers within bounds (1-999999) before inclusion in GraphQL queries.
