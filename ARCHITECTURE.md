# Architecture

## Overview

The release notes generator is a standalone Python project with zero external dependencies. It consists of two main scripts:

- **`release_notes.py`** - Three-stage pipeline (Extract, Categorize, Render) that generates O3DE release notes from merged pull requests.
- **`generate_sbom.py`** - Generates a CycloneDX 1.5 SBOM for supply chain transparency.

Both scripts use only Python stdlib modules and interact with external systems (git, GitHub API) exclusively through the `gh` CLI and `git` commands via `subprocess` with list arguments.

```
                    ┌──────────────────────────────────────────────────────────────┐
                    │                     release_notes.py                         │
                    │                                                              │
                    │   ┌───────────┐     ┌──────────────┐     ┌──────────────┐    │
 Local git clones ─▶│   │  Extract  │────▶│  Categorize  │────▶│   Render     │    │
   (read-only,      │   │           │     │              │     │              │    │
    per-repo)       │   │ git log   │     │ 1. Labels    │     │ Markdown     │    │
                    │   │ PR #s     │     │ 2. Title     │     │ by SIG       │    │
                    │   │ merge-    │     │ 3. Files     │     │ (filters     │    │
                    │   │  base     │     │ + machinery  │     │  machinery)  │    │
                    │   └─────┬─────┘     └──────┬───────┘     └──────┬───────┘    │
                    │         │                  │                    │            │
                    │         ▼                  ▼                    ▼            │
                    │   ┌───────────┐     ┌──────────────┐     ┌──────────────┐    │
                    │   │  gh CLI   │     │ JSON cache   │     │  .md output  │    │
                    │   │  GraphQL  │     │ (editable,   │     │ + optional   │    │
                    │   │           │     │  schema v3)  │     │  LLM summary │    │
                    │   └───────────┘     └──────────────┘     └──────┬───────┘    │
                    │                                                 │            │
                    │                            point-release audit  │            │
                    │                            sidecar (auto when ◀─┘            │
                    │                            from-ref is X.Y.N)                │
                    └──────────────────────────────────────────────────────────────┘
                          │                     ▲                      │
                          ▼                     │                      ▼
                     GitHub API           Human / AI agent       Feature list /
                     (batched,            edits JSON for         release notes
                      auth via            manual overrides       (.md file) +
                      gh CLI)                                    audit sidecar
```

## Project Components

### `release_notes.py`

The main script. Three subcommands (`fetch`, `render`, `generate`) exposed via `argparse`.

**Key data structures:**
- `SIG_TITLE_KEYWORDS` - Dict mapping SIG names to title keyword lists for heuristic categorization.
- `SIG_FILE_PATH_PATTERNS` - Dict mapping SIG names to file path prefixes for heuristic categorization.
- `SIG_CANONICAL_ORDER` - List defining the fixed section ordering in rendered markdown.
- `CHERRY_PICK_PATTERNS` - Regex list that flags PR titles as cherry-picks or stabilization-syncs (filtered from rendered output via the per-PR `flags` field).
- `POINTRELEASE_CONTAINER_PATTERNS` - Regex list (subset of cherry-pick patterns specialised for *containers*: commits whose bodies enumerate bundled PRs via the `(#NNNN)` convention). Used by `extract_pointrelease_containers()` when writing the audit sidecar.
- `POINT_RELEASE_TAG_PATTERN` - Compiled regex matching `X.Y` style tags (e.g. `2510.2`) so the tool can detect point-release refs and emit the awareness log line / audit sidecar.
- `RELEASE_MACHINERY_TITLE_PATTERNS` - Regex list matching titles that clearly indicate non-product PRs (`Update version`, `Update SBOM`, `Update Linux GPG key`, `Cherry pick … pointrelease`, `Merge … pointrelease into main`, etc.).
- `RELEASE_MACHINERY_FILE_PATTERNS` - Narrow file-path patterns (`engine.json` / `sbom.cdx.json` / `version.txt`). Used by `is_release_machinery()` only when ALL changed files match. Deliberately excludes `.github/workflows/` so real CI improvements aren't filtered.

**Multi-repo support:** The `parse_repo_path_mappings()` function resolves per-repo local clone paths. Each repo can have its own clone via `--repo-path owner/repo=/path`, with `--default-repo-path` as the fallback.

**Summary generation:** The `generate_summary()` function builds a structured prompt from categorized PR data and passes it via stdin to a configurable LLM command via subprocess (list args, no `shell=True`). Default: `ollama run --nowordwrap qwen2.5:14b` (local, ~12 GB VRAM); also supports `qwen2.5:32b` for ~24 GB hosts and `claude -p` (cloud). The `_clean_summary()` function strips LLM preamble text and dividers from the output. Command is parsed via `shlex.split()`. Optional `--summary-hint` injects release manager guidance into the prompt; it accepts inline text or `@filepath` to read from a file (resolved via `_resolve_hint()`). Enabled via `--generate-summary`; disabled by default. PRs flagged `release_machinery: True` are excluded from the prompt unless `--include-release-machinery` is set, so the LLM stays focused on product changes.

**Point-release awareness and audit:** When `--from-ref` parses as a point-release tag with a non-zero patch (e.g. `2510.2`), `_emit_point_release_awareness_log()` runs `git merge-base` against the major sibling tag (`2510.0`) and `--to-ref`; when the merge-bases match, it logs a single `INFO` line so future runs don't relearn the equivalence. `_maybe_write_pointrelease_audit()` then iterates per repo, calls `extract_pointrelease_containers()` to find cherry-pick container PRs between the major and point-release tags, parses bundled PR numbers from each container's commit body, and writes a `<output-md-stem>_pointrelease_audit.md` sidecar with a ✓/✗ checklist for every bundled fix vs the rendered report. Suppressed via `--no-pointrelease-audit`.

**Merge-base metadata:** `extract_merge_base()` runs `git merge-base <from-ref> <to-ref>` and `git show -s --format=%cI <sha>` per repo, returning `(sha, committer_date)`. Results land in `release_data.json` under `metadata.merge_bases`; the earliest committer-date across repos plus the run's `generated_at` form `metadata.effective_window`. Anchors the diff to the actual fork point, usually the date PR-curators reference in their release-notes PR description.

### `generate_sbom.py`

Generates a CycloneDX 1.5 JSON SBOM (`sbom.cdx.json`). Captures project metadata, Python stdlib module inventory, and SHA-256 hashes of all source files.

### `tests/test_release_notes.py`

Unit tests using `pytest` and `unittest.mock`. Covers input validation (including injection attempts and stderr token redaction), multi-repo path parsing, SIG categorization (labels, title heuristics, file heuristics, priority ordering, deterministic tiebreaks), GraphQL variable shape, summary prompt building, summary generation (success, failure, timeout, timeout-bounds validation), markdown rendering (with and without summary, with release-machinery filtering), incremental merging with manual-override preservation and drop warnings, dry-run behavior, atomic file I/O, JSON loading/validation, PR body size capping, point-release tag parsing, sibling-tag discovery, merge-base extraction, cherry-pick container parsing, audit sidecar generation, release-machinery classification (title + file-path heuristics), and point-release awareness log line.

### `.github/workflows/sbom.yml`

GitHub Action that regenerates `sbom.cdx.json` on every push to `main` that changes Python source files. Commits the updated SBOM back to the repository automatically.

## Data Flow

### Stage 1: Extract

**Input:** Local git repositories (read-only, one per repo), two git references (tag/branch).

**Process:**
1. Resolves per-repo local clone paths via `parse_repo_path_mappings()`.
2. For each repo, runs `git log --format=%s <from>..<to> --no-merges` via `subprocess.run()` with list arguments against that repo's local clone.
3. Parses PR numbers from commit subjects using regex `\(#(\d+)\)`.
4. Deduplicates and sorts per repo.

**Output:** Sorted list of PR numbers per repo.

**Trust boundary:** The git log output is from local repositories the user controls. PR numbers are parsed as integers, preventing injection. Repo path mappings are validated for format before use.

### Stage 2: Fetch + Categorize

**Input:** PR numbers per repo, GitHub repo slug(s).

**Process:**
1. For each repo, constructs GraphQL queries batching up to 30 PRs per request (~8 requests for a typical release of ~230 PRs). Queries fetch title, body, labels, files, author, and merge date. The query uses GraphQL variables (`$owner`, `$name`) instead of string interpolation, so owner/name never appear in the query body.
2. Executes via `gh api graphql -f query=… -f owner=… -f name=…` (subprocess with list args). Each repo's PRs are fetched from the correct GitHub owner/repo.
3. PR descriptions are built from the PR body's first meaningful paragraph (20-300 chars; skipping template headers, checklists, URLs, images, `<img>` tags, and bullet lists). The body is capped at 64KB before extraction so a pathological body cannot blow up regex/string ops. When the paragraph shares less than 20% word overlap with the title, both are combined with an em dash for standalone readability. Falls back to the sanitized title if the body is empty, too short, too long, or entirely noise.
4. For each PR, categorizes by SIG using three methods in priority order:
   - **Label match:** Checks for `sig/*` GitHub labels. Highest confidence. When multiple SIG labels are present, the SIG earliest in `SIG_CANONICAL_ORDER` wins (deterministic, does not depend on label-return order from GitHub).
   - **Title heuristic:** Matches title keywords against per-SIG keyword maps. Best-keyword-count wins; on ties, the SIG earliest in `SIG_CANONICAL_ORDER` wins.
   - **File path heuristic:** Matches changed file paths against directory-to-SIG maps (derived from `.github/CODEOWNERS`). Uses longest-match-wins: for overlapping patterns (e.g., `AzCore/AzCore/Math/` vs `AzCore/`), the most specific match determines the SIG.
5. Detects flags (cherry-pick, stabilization-sync) for filtering.
6. Tags each PR with `release_machinery: True/False` via `is_release_machinery()`. True when the title matches `RELEASE_MACHINERY_TITLE_PATTERNS` (version bumps, SBOM auto-updates, cherry-pick-to-pointrelease wrappers, etc.) **or** when every changed file matches `RELEASE_MACHINERY_FILE_PATTERNS` (a deliberately narrow set: `engine.json` / `sbom.cdx.json` / `version.txt`). Used by Stage 3 to filter non-product PRs out of the rendered report by default.
7. Computes per-repo `merge_bases` via `extract_merge_base()` (sha + committer-date) and aggregates the earliest committer-date into `effective_window.start`. Writes these into `metadata` alongside `schema_version: 3`, `pr_count`, and `release_machinery_count`.
8. Merges with any existing JSON data, preserving manual overrides. PRs that exist in the prior JSON but no longer appear in `git log` and lack `manual_override_*` are dropped, and a warning is logged so the user notices when this happens. PRs from older JSONs without a `release_machinery` field are backfilled by re-running `is_release_machinery()` against their cached title/files.
9. If `--from-ref` parses as a point-release tag with non-zero patch (e.g. `2510.2`) and `--no-pointrelease-audit` was not set, writes the point-release audit sidecar (see "Point-release awareness and audit" above).

**Output:** Structured JSON with full PR metadata and categorization, plus (optionally) a point-release audit sidecar.

**Trust boundary:** PR data comes from the GitHub API (untrusted). Titles are sanitized before rendering. Labels and file paths are used for categorization only, not interpolated into shell commands.

### Stage 3: Render

**Input:** JSON data from Stage 2, version string, optional summary generation config.

**Process:**
1. If `--generate-summary` is enabled, builds a structured prompt from the PR data and passes it via stdin to the configured LLM command (default: `ollama run --nowordwrap qwen2.5:14b`; or `claude -p` for cloud, or `qwen2.5:32b` for ~24 GB VRAM hosts) via subprocess with list args. LLM preamble text and dividers are stripped from the output. PRs flagged `release_machinery` are excluded from the prompt unless `--include-release-machinery` is set.
2. Groups PRs by SIG category.
3. Filters out cherry-picks and stabilization sync PRs.
4. Filters out PRs flagged `release_machinery: True` unless `--include-release-machinery` is set (default off for major releases; turn on for point-release notes where machinery IS the content).
5. Renders markdown with fixed SIG ordering matching the established O3DE release notes format.
6. Inserts the LLM-generated narrative summary (or a placeholder if summary generation is disabled or fails).
7. Sanitizes PR titles for markdown (escapes special characters).

**Output:** Markdown file.

**Trust boundary:** Output is written atomically to prevent corruption. PR titles are sanitized to prevent markdown injection. The summary command is executed via subprocess with list args (no `shell=True`). The LLM's output is inserted as-is into the markdown intro section; it is not interpolated into shell commands or other untrusted contexts.

## Incremental Update Flow

The tool supports re-running throughout the pre-release cycle. On subsequent runs, only new PRs are fetched from GitHub, and any manual edits to the JSON (via `manual_override_sig` and `manual_override_description` fields) are preserved.

```
First run:                    Subsequent runs:

git log (per repo) ──▶ PR #s  git log (per repo) ──▶ PR #s (may have grown)
    │                             │
    ▼                             ▼
GitHub API ──▶ all PRs        GitHub API ──▶ new PRs only
    │                             │
    ▼                             ▼
categorize ──▶ JSON           merge with existing JSON
    │                         (preserve manual_override_* fields)
    ▼                             │
write JSON                        ▼
    │                         write updated JSON
    ▼                             │
(optional) LLM summary            ▼
    │                         (optional) LLM summary
    ▼                             │
render .md                        ▼
                              render updated .md
```

## SBOM Generation

The `generate_sbom.py` script produces a CycloneDX 1.5 JSON SBOM at `sbom.cdx.json`.

**Contents:**
- Project metadata (name, version, license, repo URL)
- 13 Python stdlib modules declared as framework dependencies with package URLs
- SHA-256 hashes of all source files (`release_notes.py`, `generate_sbom.py`, `tests/test_release_notes.py`)
- Explicit `cdx:externalDependencies: none` property
- Dependency graph linking the project to its stdlib modules

**Automation:** The `.github/workflows/sbom.yml` workflow regenerates the SBOM on every push to `main` that changes `*.py` files. The workflow uses `github-actions[bot]` to commit the updated SBOM, preventing infinite trigger loops (bot commits don't trigger workflows by default).

**Atomic writes:** Like the main script, the SBOM generator uses `tempfile.mkstemp()` + `os.replace()` for crash-safe file output.

## Security Model

### Trust Boundaries

```
┌───────────────────────────────────────────────────────────────────────────┐
│                        TRUSTED: local user environment                   │
│                                                                           │
│   user CLI args ──┐                                                       │
│   gh credentials ─┼──▶ release_notes.py ──▶ output: JSON, .md (atomic)    │
│   local git repo ─┘         │                                             │
│                             │ subprocess (list args, no shell=True)       │
│        ┌────────────────────┼─────────────────────────┐                   │
│        ▼                    ▼                         ▼                   │
│ ┌────────────┐       ┌────────────┐            ┌─────────────┐            │
│ │ git log    │       │ gh CLI     │            │ summary cmd │            │
│ │ (read-only)│       │ (auth via  │            │ (ollama /   │            │
│ │            │       │  keyring)  │            │  claude /   │            │
│ │            │       │            │            │  custom)    │            │
│ └────────────┘       └─────┬──────┘            └──────┬──────┘            │
│                            │                          │                   │
└────────────────────────────┼──────────────────────────┼───────────────────┘
                             │                          │
            ═══════════════ trust boundary ═══════════════
                             │                          │
                ┌────────────▼──────────┐    ┌──────────▼──────────┐
                │   GitHub GraphQL API  │    │  LLM (local/cloud)  │
                │   (PR titles, bodies, │    │  (untrusted output, │
                │    labels; UNTRUSTED) │    │   sanitized into MD)│
                └───────────────────────┘    └─────────────────────┘
```

Everything inside the trusted box is data the user controls or gh's credential store. Anything crossing a trust boundary (GitHub API responses, LLM output) is treated as untrusted: validated structurally, sanitized for markdown, and never used to construct shell commands or file paths.

### Threat Model

| Asset | Threat | Mitigation |
|-------|--------|------------|
| GitHub auth token | Exposure in logs or code | Delegated to `gh` CLI credential store; never handled directly. `_safe_stderr()` scrubs `ghp_/gho_/ghu_/ghs_/ghr_` token shapes from any subprocess stderr before logging (defense-in-depth). |
| PR titles (untrusted) | Markdown injection in rendered output | Sanitized: `#`, `[`, `]`, `` ` ``, `\|` escaped; trailing PR refs stripped |
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
| LLM output | Prompt injection in generated narrative | Output is inserted into markdown intro only; not used in shell commands, file paths, or API calls. Output is reviewed by a human before publishing. |
| Subprocess stderr | Sensitive data in CI logs | All subprocess output decoded with `encoding='utf-8', errors='replace'`; stderr passed through `_safe_stderr()` (token-scrub + 200-char truncation) before logging. |
| Supply chain | Undetected dependency changes | CycloneDX SBOM with source file SHA-256 hashes; auto-updated via CI (`sbom.yml`); GitHub Actions pinned to commit SHAs (not floating tags). |

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
| **SI-15 (Information Output Filtering)** | PR titles sanitized for markdown special characters before rendering. Only whitelisted fields from API responses are used. |
| **AU-3 (Content of Audit Records)** | Structured log format with severity levels. Categorization summary logged on each run. |
| **SC-28 (Protection of Information at Rest)** | Atomic file writes via `tempfile.mkstemp()` + `os.replace()` prevent data corruption from interrupted writes. |
| **CM-7 (Least Functionality)** | Minimal stdlib-only implementation. No unnecessary network calls (only fetches new PRs on re-run). No write access to the O3DE repository. |
| **SA-8 (Security and Privacy Engineering Principles)** | CycloneDX SBOM generated and maintained for supply chain transparency. Source file integrity verified via SHA-256 hashes. |

### Input Validation Specifications

| Input | Pattern | Max Length | Additional Checks |
|-------|---------|------------|-------------------|
| Git ref | `^[a-zA-Z0-9._/-]+$` | 256 | Must not start with `-` |
| Repo slug | `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` | 128 | Exactly one `/` |
| Repo path mapping | `^(owner/repo)=(.+)$` | N/A | Repo slug validated separately; path resolved via `pathlib`; `.git` existence checked |
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
subprocess.run(['git', 'log', '--format=%s', f'{from_ref}..{to_ref}'], ...)
subprocess.run(['gh', 'api', 'graphql',
                '-f', f'query={query}',
                '-f', f'owner={owner}',
                '-f', f'name={name}'], ...)  # owner/name are GraphQL variables
subprocess.run(['gh', 'auth', 'status'], ...)
subprocess.run(cmd_parts, input=prompt, ...)  # summary generation via stdin
```

No call uses `shell=True`. All calls pass `encoding='utf-8', errors='replace'` so non-UTF-8 locales cannot corrupt decoded output. The `from_ref` and `to_ref` values are validated before interpolation into the argument list, preventing argument injection (e.g., a ref like `--exec=malicious` is rejected by the leading-hyphen check). For GraphQL, owner and name are passed as variables (`$owner`, `$name`) via separate `-f` arguments; they are never interpolated into the query string itself. The summary command is parsed via `shlex.split()` (respects shell quoting) and the executable is verified via `shutil.which()` before invocation. PR numbers are validated to be positive integers within bounds (1-999999) before inclusion in GraphQL queries.
