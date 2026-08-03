# O3DE Release Notes Generator

A standalone tool that generates [Open 3D Engine (O3DE)](https://o3de.org) release notes by extracting merged pull requests from GitHub, categorizing them by SIG (Special Interest Group), and rendering markdown in the established release notes format.

Designed to be run incrementally throughout the pre-release cycle so the release team can track progress as PRs land.

Currently in use for the **O3DE 26.10.0** cycle. See [RELEASE_RUNBOOK.md](RELEASE_RUNBOOK.md) for the step-by-step procedure.

## Prerequisites

- Python 3.10+
- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated (`gh auth login`)
- Local clone(s) of O3DE repositories (read-only reference)
- (Optional) An LLM for automated narrative summary generation: [Ollama](https://ollama.com/) (local, open-source) or [Claude CLI](https://claude.ai/claude-code) (cloud)

## Quick Start

```bash
# Generate release notes for 26.10.0 (everything since 26.05.0)
python release_notes.py generate \
  --from-ref 2605.0 \
  --to-ref origin/development \
  --default-repo-path /path/to/o3de \
  --output-json release_data.json \
  --output-md 26100_release_notes.md \
  --release-version 26.10.0
```

Switch `--to-ref` to `origin/stabilization/26100` once that branch is cut. For a
real run you also need `--exclude-json` pointed at the previous release's report;
see [Excluding the Previous Release](#excluding-the-previous-release). If point releases ship on the `2605` line, use the latest of them (`2605.1`, `2605.2`, …) as `--from-ref`.

## Project Structure

```
o3de-release-notes-generator/
├── README.md                       # This file
├── ARCHITECTURE.md                 # Architecture, security model, data flow
├── CHANGELOG.md                    # Version history (Keep a Changelog format)
├── CONTRIBUTING.md                 # Dev workflow, dual-license, SHA-pin policy
├── SECURITY.md                     # Vulnerability disclosure
├── AGENTS.md                       # AI agent instructions for this repo
├── RELEASE_RUNBOOK.md              # Step-by-step procedure for a release cycle
├── release_notes.py                # Main script (zero external dependencies)
├── generate_sbom.py                # CycloneDX 1.5 SBOM generator
├── sbom.cdx.json                   # Generated SBOM (auto-updated via CI)
├── pyproject.toml                  # pytest / ruff / mypy config
├── Makefile                        # test / sbom / lint / typecheck targets
├── tests/
│   └── test_release_notes.py       # Unit tests
├── reports/                        # Per-release reports (committed)
│   ├── 26050_release_data.json     # 26.05.0 report; exclusion source for 26.10.0
│   └── hints/                      # Reusable --summary-hint files
├── .github/
│   └── workflows/
│       ├── sbom.yml                # Auto-regenerates SBOM on push
│       └── test.yml                # Runs pytest on push & PR
├── LICENSE.txt                     # Dual-license overview
├── LICENSE_APACHE2.TXT             # Apache License 2.0
├── LICENSE_MIT.TXT                 # MIT License
└── .gitignore
```

## CLI Reference

The tool has three subcommands: `fetch`, `render`, and `generate`.

### `fetch` - Extract PR data from GitHub into JSON

```bash
python release_notes.py fetch \
  --from-ref <start-tag> \
  --to-ref <end-branch> \
  --default-repo-path <path-to-local-clone> \
  --output-json <output.json> \
  [--repos owner/repo ...] \
  [--repo-path owner/repo=/path ...] \
  [--repo-from-ref owner/repo=REF ...] \
  [--repo-to-ref owner/repo=REF ...] \
  [--exclude-json prior_release.json ...] \
  [--dry-run] \
  [--no-pointrelease-audit] \
  [--log-file PATH] \
  [-v]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--from-ref` | Yes | - | Starting git reference (tag or commit) |
| `--to-ref` | Yes | - | Ending git reference (branch or tag) |
| `--default-repo-path` | No | `.` | Default local clone path for repos without explicit mapping |
| `--repo-path` | No | - | Per-repo clone paths as `owner/repo=/path/to/clone` (repeatable) |
| `--repo-from-ref` | No | - | Per-repo override for `--from-ref` as `owner/repo=REF` (repeatable). Needed when a release tag exists in some repos but not others |
| `--repo-to-ref` | No | - | Per-repo override for `--to-ref` as `owner/repo=REF` (repeatable) |
| `--exclude-json` | No | - | Prior release report JSON(s). PRs already reported there are dropped from the window and never fetched (repeatable). **Required for a correct major-release window;** see below |
| `--output-json` | Yes | - | Output JSON file path |
| `--repos` | No | `o3de/o3de` | GitHub repos in `owner/repo` format (where PRs live) |
| `--dry-run` | No | off | Print which PRs would be fetched (from git log) without calling the GitHub API or writing files |
| `--no-pointrelease-audit` | No | off | Skip the point-release audit sidecar even when `--from-ref` looks like a point-release tag (`MAJOR.PATCH` with a non-zero patch) |
| `--log-file` | No | - | Append logs to this file in addition to stderr |
| `-v` | No | - | Verbose logging |

### `render` - Generate markdown from JSON

```bash
python release_notes.py render \
  --input-json <input.json> \
  --output-md <output.md> \
  --release-version <version-string> \
  [--include-uncategorized] \
  [--include-release-machinery] \
  [--generate-summary] \
  [--summary-cmd <command>] \
  [--summary-hint <text>] \
  [--summary-timeout <seconds>] \
  [--log-file PATH]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--input-json` | Yes | - | Path to JSON from `fetch` |
| `--output-md` | Yes | - | Output markdown file path |
| `--release-version` | Yes | - | Release version string (e.g., `26.05.0`) |
| `--include-uncategorized` | No | off | Show PRs that couldn't be categorized |
| `--include-release-machinery` | No | off | Include release-engineering PRs (version bumps, SBOM auto-updates, cherry-pick-to-pointrelease wrappers, etc.) in the rendered output. Off by default for major releases; turn on for point-release notes where machinery IS the content |
| `--generate-summary` | No | off | Generate a narrative summary using an LLM |
| `--summary-cmd` | No | `ollama run --nowordwrap qwen2.5:14b` | Command to generate the summary |
| `--summary-hint` | No | - | Narrative guidance: inline text or `@filepath` to read from a file |
| `--summary-timeout` | No | `300` | Timeout (seconds) for the summary command (range: 10–3600) |
| `--log-file` | No | - | Append logs to this file in addition to stderr |

### `generate` - Fetch and render in one step

Combines `fetch` and `render`. Accepts all flags from both subcommands.

## Examples

### Generate notes for a specific release

```bash
python release_notes.py generate \
  --from-ref 2605.0 \
  --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md 26100_release_notes.md \
  --release-version 26.10.0
```

### Incremental update during pre-release

Re-run the same command. Every PR in the range is re-fetched from GitHub on each
run (there is no per-PR cache), but manual edits in the JSON are preserved:
`manual_override_sig` and `manual_override_description` survive re-runs.

```bash
# Week 1
python release_notes.py generate --from-ref 2605.0 --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de --output-json release_data.json \
  --output-md notes.md --release-version 26.10.0

# Week 2 (same command; re-fetches the full range, re-applies your overrides)
python release_notes.py generate --from-ref 2605.0 --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de --output-json release_data.json \
  --output-md notes.md --release-version 26.10.0
```

A full range costs roughly one GraphQL request per 30 PRs, so a ~420-PR cycle is
about 14 requests. Weekly re-runs are comfortably inside GitHub's rate limits.

### Multi-repo with separate local clones

```bash
python release_notes.py generate \
  --from-ref 2605.0 --to-ref origin/development \
  --repos o3de/o3de o3de/o3de-extras \
  --default-repo-path ~/PROJECTS/o3de \
  --repo-path o3de/o3de-extras=~/PROJECTS/o3de-extras \
  --repo-from-ref o3de/o3de-extras=2510.2 \
  --exclude-json reports/26050_release_data.json \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.10.0
```

Each repo runs `git log` against its own local clone. The `--default-repo-path` is used for any repo without an explicit `--repo-path` mapping.

**Not every repo is tagged on every release line.** `o3de/o3de` carries `2605.0`, but `o3de/o3de-extras` does not, so a single global `--from-ref 2605.0` cannot resolve there. Use `--repo-from-ref owner/repo=REF` to give that repo its own starting point (`--repo-to-ref` does the same for the end of the range). A preflight check resolves every `(repo, ref)` pair before any work starts and fails with an actionable message rather than aborting part-way through a run.

### Generate with automated narrative summary

```bash
python release_notes.py generate \
  --from-ref 2605.0 --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.10.0 \
  --generate-summary
```

This builds a structured prompt from the categorized PR data and pipes it via stdin to the summary command (default: `ollama run --nowordwrap qwen2.5:14b`). The generated narrative replaces the placeholder intro in the markdown output.

To use a different model or tool:

```bash
# Claude CLI (cloud, highest quality)
--generate-summary --summary-cmd "claude -p"

# Larger local model for machines with more VRAM
--generate-summary --summary-cmd "ollama run --nowordwrap qwen2.5:32b"

# Or any tool that reads a prompt from stdin and writes to stdout
--generate-summary --summary-cmd "my-llm-tool --flag"

# Bump the timeout for slower models / hardware
--generate-summary --summary-timeout 900
```

The command must read the prompt from **stdin** and write its response to **stdout**.

### Steer the narrative with a hint

Use `--summary-hint` to guide the LLM toward specific themes or tone:

```bash
python release_notes.py generate \
  --from-ref 2605.0 --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.10.0 \
  --generate-summary \
  --summary-hint "This is a major platform expansion release. Emphasize Wayland support, Mac ARM64, and Emscripten. Note that PhysX4 deprecation is a breaking change."
```

The hint is injected into the LLM prompt as "additional guidance from the release manager" and shapes the narrative without overriding the structured PR data.

To load the hint from a file, prefix the path with `@`:

```bash
  --summary-hint @release_briefing.txt
```

This is useful for longer guidance or when reusing the same narrative direction across incremental runs.

### Fetch only (for AI agent consumption)

```bash
python release_notes.py fetch \
  --from-ref 2605.0 --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json
```

### Include uncategorized PRs for triage

```bash
python release_notes.py generate \
  --from-ref 2605.0 --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.10.0 \
  --include-uncategorized
```

### Dry-run (preview which PRs would be fetched)

```bash
python release_notes.py fetch \
  --from-ref 2605.0 --to-ref origin/development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json /tmp/unused.json \
  --dry-run
```

Reads `git log` locally and prints the PR numbers that would be fetched. No GitHub API calls; no files written. Always do this first: it verifies refs and clone paths, and it is the cheapest way to confirm the PR count looks right before a long run.

### Generating notes when point releases have shipped on the previous line

When point releases have shipped between the previous major and the current cycle (e.g. `2605.0` → `2605.1` → `2605.2`), pass the **latest point-release tag** as `--from-ref`:

```bash
python release_notes.py generate \
  --from-ref 2605.2 \
  --to-ref origin/stabilization/26100 \
  --repos o3de/o3de o3de/o3de-extras \
  --repo-path o3de/o3de=~/PROJECTS/o3de \
  --repo-path o3de/o3de-extras=~/PROJECTS/o3de-extras \
  --repo-from-ref o3de/o3de-extras=2510.2 \
  --output-json reports/26100_release_data.json \
  --output-md reports/26100_release_notes.md \
  --release-version 26.10.0
```

Point-release tags are two-component (`MAJOR.PATCH`, e.g. `2605.2`), where the
major token encodes year and month.

The tool auto-detects the point-release pattern and:

1. Emits a one-line `INFO` log noting that the merge-base of `2605.0` and `2605.2` against `--to-ref` is identical (point-release cherry-picks are correctly excluded; their bundled fixes are counted via the development-side merges instead).
2. Writes a **point-release audit sidecar** at `reports/26100_release_notes_pointrelease_audit.md` listing every cherry-pick container PR found on the previous stabilization branch, with each bundled PR shown as ✓ (present in the rendered report) or ✗ (missing; investigate). Turns the manual "did we lose any fixes?" check into a one-glance checklist. Suppress with `--no-pointrelease-audit`.
3. Flags release-machinery PRs (version bumps, SBOM auto-updates, cherry-pick wrappers, "merging pointrelease into main" merges, etc.) with `release_machinery: true` in the JSON and excludes them from the rendered output. Opt back in with `--include-release-machinery`; useful for *point-release* notes where the machinery PRs are the headline content.

## Sample Output

A real run against `o3de/o3de` 26.05.0 → `development` (369 PRs) renders something like:

```markdown
# 26.10.0 Release Notes

The O3DE 26.10.0 release includes bug fixes, performance enhancements,
and new features across the engine.

<!-- TODO: Write a narrative summary of the release highlights -->

# Full list of changes

## SIG-Build
- Remove system cmake dependency from the Linux installer. [o3de#19704](https://github.com/o3de/o3de/pull/19704)
- Update vcpkg baseline for clang-19 builds. [o3de#19712](https://github.com/o3de/o3de/pull/19712)
- ...

## SIG-Graphics-Audio
- Fix shader compilation error in Atom on dx12. [o3de#19651](https://github.com/o3de/o3de/pull/19651)
- ...

## SIG-Platform
- Initial Wayland support for Linux. [o3de#19589](https://github.com/o3de/o3de/pull/19589)
- ...
```

The `<!-- TODO -->` placeholder is replaced with a real narrative when `--generate-summary` is used. A complete sample run is checked in under [`reports/`](reports/) (one full release; refresh manually as desired).

## Excluding the Previous Release

**A release tag is not a usable window boundary on its own.** O3DE's `main` line
is built from periodic "merge stabilization to main" commits, so a tag like
`2605.0` shares only an ancient merge-base with `development`:

```
merge-base(2605.0, origin/development) = 57680ee42  (2025-07-29)
```

That is before the 26.05 cycle began, so `2605.0..origin/development` spans *two*
release cycles. Measured against real clones:

| Window | PRs found | Already in the 26.05.0 notes | Genuinely new |
|---|---|---|---|
| `o3de/o3de` `2605.0..development` | 369 | 188 | 181 |
| `o3de/o3de-extras` `2510.2..development` | 50 | 30 | 20 |

The duplicates are the development-side merges of fixes that reached the
previous release by cherry-pick into its stabilization branch. They are distinct
commits with distinct SHAs, unreachable from the tag, so **neither a different
ref nor a date cutoff can separate them** (the two sets interleave in time: the
new PRs start 2025-09-05 while the already-shipped ones run to 2026-04-12).

Pass the previous release's report as an exclusion source:

```bash
--exclude-json reports/26050_release_data.json
```

PRs already reported there are dropped before any GitHub call, which also cuts
the fetch cost. The sources used, and the per-repo counts excluded, are recorded
in `metadata.excluded_prior_releases`. Pointing `--exclude-json` at this run's
own `--output-json` is refused, since it would empty the report on the next run.

## Reconciliation Output

Every `render` (and the render half of `generate`) prints an explicit account of
what reached the report and what did not:

```
[INFO] o3de.release_notes: Reconciliation: 419 PR(s) in JSON, 402 rendered
[WARNING] o3de.release_notes: Excluded 17 PR(s) from the report: cherry-pick=12,
          release_machinery=1, uncategorized=4. Re-run render with
          --include-uncategorized / --include-release-machinery to inspect them.
```

The counts are mutually exclusive and sum to the total, so nothing can be
dropped silently. **Read this line on every run.** A sudden jump in any excluded
category means a heuristic has started over-matching; that is exactly how 57 real
PRs went missing from the 26.05.0 notes undetected.

## JSON Schema

The intermediate JSON is the primary data format. It can be edited by humans or consumed by AI agents.

```json
{
  "metadata": {
    "generated_at": "2026-08-03T10:00:00+00:00",
    "from_ref": "2605.0",
    "to_ref": "origin/development",
    "repos": ["o3de/o3de", "o3de/o3de-extras"],
    "repo_paths": {
      "o3de/o3de": "/home/user/PROJECTS/o3de",
      "o3de/o3de-extras": "/home/user/PROJECTS/o3de-extras"
    },
    "schema_version": 4,
    "tool_version": "0.6.0-beta",
    "pr_count": 419,
    "categorization_summary": {
      "label": 268,
      "heuristic_title": 92,
      "heuristic_files": 55,
      "uncategorized": 4
    },
    "release_machinery_count": 1,
    "merge_bases": {
      "o3de/o3de": {
        "sha": "57680ee42f18d5952e4d4fa5ab52750edefb878e",
        "committer_date": "2025-07-29T11:12:47-07:00"
      },
      "o3de/o3de-extras": {
        "sha": "3038e4ac7b566b8b0ab7360acc67d6280eb68eba",
        "committer_date": "2025-09-08T14:48:13+02:00"
      }
    },
    "effective_window": {
      "start": "2025-07-29T11:12:47-07:00",
      "end": "2026-08-03T10:00:00+00:00"
    },
    "excluded_prior_releases": {
      "sources": ["/home/user/.../reports/26050_release_data.json"],
      "per_repo": {"o3de/o3de": 188, "o3de/o3de-extras": 30},
      "total": 218
    },
    "repo_refs": {
      "o3de/o3de": {"from_ref": "2605.0", "to_ref": "origin/development"},
      "o3de/o3de-extras": {"from_ref": "2510.2", "to_ref": "origin/development"}
    }
  },
  "pull_requests": [
    {
      "number": 19709,
      "repo": "o3de/o3de",
      "title": "Fix for choppy mouse movement in FlyCameraInputComponent",
      "url": "https://github.com/o3de/o3de/pull/19709",
      "author": "contributor",
      "merged_at": "2026-04-20T17:14:14Z",
      "labels": ["sig/content"],
      "files": ["Gems/AtomLyIntegration/.../FlyCameraInputComponent.cpp"],
      "sig_category": "sig/content",
      "categorization_source": "label",
      "description": "Fix for choppy mouse movement in FlyCameraInputComponent.",
      "flags": [],
      "release_machinery": false,
      "manual_override_sig": null,
      "manual_override_description": null
    }
  ]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `sig_category` | Assigned SIG. Set automatically, or via `manual_override_sig`. |
| `categorization_source` | How the SIG was assigned: `label`, `heuristic_title`, `heuristic_files`, `uncategorized`, `manual_override` |
| `flags` | Auto-detected flags. Currently only `cherry-pick` (title evidence), which excludes the PR from rendered markdown. A legacy `stabilization-sync` value may appear in JSON written by ≤0.5.0-beta; it is ignored on render. |
| `release_machinery` | Auto-detected boolean for release-engineering PRs (version bumps, SBOM auto-updates, cherry-pick-to-pointrelease wrappers, `engine.json`/`sbom.cdx.json`/`version.txt`-only diffs). Excluded from rendered markdown and summary prompts by default; opt back in with `--include-release-machinery`. |
| `manual_override_sig` | Set this to reassign a PR to a different SIG. Preserved on re-runs. |
| `manual_override_description` | Set this to override the auto-generated description. Preserved on re-runs. |
| `metadata.merge_bases` | Per-repo `{sha, committer_date}` for the merge-base of `from_ref` and `to_ref`. Anchors the actual fork point. |
| `metadata.effective_window` | `{start, end}` window the diff covers. `start` is the earliest merge-base committer-date across repos; `end` is `generated_at`. |
| `metadata.release_machinery_count` | Number of PRs flagged `release_machinery: true` in this run. |
| `metadata.tool_version` | Version of `release_notes.py` that produced the file. Present from schema 4. |
| `metadata.excluded_prior_releases` | Which prior reports were used as exclusion sources and how many PRs each repo dropped because of them. |
| `metadata.repo_refs` | Per-repo `{from_ref, to_ref}`. Emitted only when `--repo-from-ref` / `--repo-to-ref` made a repo's range differ from the global one. |

## PR Discovery

PR numbers come from the local `git log` over `<from-ref>..<to-ref>`, matched two ways:

| Merge strategy | Commit subject | Pattern |
|---|---|---|
| Squash merge | `Fix choppy mouse movement (#19709)` | `\(#(\d+)\)` |
| Merge commit | `Merge pull request #19882 from o3de/branch` | `^Merge pull request #(\d+)` |

Both are required. O3DE `development` uses merge commits for a large minority of
PRs, whose constituent commits carry no PR reference at all; matching only the
squash form (and passing `--no-merges`) missed 19 PRs in the 26.05.0 → 26.10.0
window. The count found via merge commits is logged on each run.

## SIG Categorization

PRs are categorized using three methods in priority order:

1. **GitHub labels** - PRs with `sig/*` labels (e.g., `sig/build`, `sig/graphics-audio`) are categorized directly. Highest confidence.
2. **Title keywords** - PR titles are matched against keyword lists per SIG.
3. **File paths** - Changed file paths are matched against directory-to-SIG mappings.

If none match, the PR is marked `uncategorized` for manual triage.

### Updating Heuristics

The categorization data lives as four data-driven structures at the top of `release_notes.py`:

| Constant | Purpose |
|----------|---------|
| `SIG_CANONICAL_ORDER` | Canonical SIG list. Defines section order in markdown output **and** acts as the deterministic tiebreaker when a PR has multiple SIG labels or its title matches keywords from multiple SIGs. |
| `SIG_DISPLAY_NAMES` | Map from `sig/foo` → `SIG-Foo` (the heading that appears in the rendered markdown). |
| `SIG_TITLE_KEYWORDS` | Per-SIG keyword list for the title-heuristic categorizer. |
| `SIG_FILE_PATH_PATTERNS` | Per-SIG file-path prefix list for the file-heuristic categorizer (longest-match-wins). |

To **adjust** an existing SIG's heuristics, edit `SIG_TITLE_KEYWORDS` and/or `SIG_FILE_PATH_PATTERNS`. To **add a new SIG**, you must update *all four*; otherwise the new SIG either won't render (missing display name) or won't be picked up at all (missing from canonical order).

> **Determinism note:** When a PR has multiple SIG labels, or its title hits keywords in multiple SIGs, the SIG that comes earliest in `SIG_CANONICAL_ORDER` wins. This guarantees the same PR is categorized the same way on every run, regardless of label order from the GitHub API or dict iteration order.

## Narrative Summary Generation

When `--generate-summary` is enabled, the tool builds a structured prompt from the categorized PR data and sends it to a configurable LLM command.

**How it works:**
1. PRs are grouped by SIG with up to 15 titles per group (truncated for large sections)
2. Cherry-picks and uncategorized PRs are excluded from the prompt
3. If `--summary-hint` is provided (inline text or `@filepath`), it's injected as "additional guidance from the release manager"
4. The prompt asks for a 2-3 paragraph narrative in the style of previous O3DE release notes
5. The LLM's output is cleaned (preamble/dividers stripped) and replaces the `<!-- TODO -->` placeholder

**Default command:** `ollama run --nowordwrap qwen2.5:14b` ([Ollama](https://ollama.com/) with Qwen 2.5 14B). Override with `--summary-cmd`. The default targets a ~12GB VRAM budget so it works on a typical workstation; bump up to `qwen2.5:32b` if you have the headroom, or use `claude -p` for the highest quality.

**Supported LLM options:**

| Command | Type | Quality | Requirements |
|---------|------|---------|--------------|
| `claude -p` | Cloud | Highest | [Claude CLI](https://claude.ai/claude-code) authenticated |
| `ollama run --nowordwrap qwen2.5:32b` | Local | Highest local | [Ollama](https://ollama.com/), ~24GB VRAM |
| `ollama run --nowordwrap qwen2.5:14b` | Local | High | [Ollama](https://ollama.com/), ~12GB VRAM (default) |
| `ollama run --nowordwrap mistral` | Local | Good | [Ollama](https://ollama.com/), ~6GB VRAM |

**Requirements for custom commands:** Must read the prompt from stdin and write the response to stdout. LLM preamble text (e.g., "Here's the summary:") and `---` dividers are automatically stripped from the output.

**When disabled (default):** A placeholder intro and `<!-- TODO -->` comment are inserted for manual writing.

## SBOM (Software Bill of Materials)

A CycloneDX 1.5 SBOM is maintained at `sbom.cdx.json`. It is automatically regenerated by a GitHub Action on every push to `main` that changes Python source files.

To regenerate locally:

```bash
make sbom          # rewrite sbom.cdx.json (no-op if already current)
make sbom-check    # exit non-zero if it is stale; run in CI
```

The SBOM captures:
- Project metadata (name, version, license, repository URL)
- Python stdlib modules used as dependencies, **discovered by parsing the source
  with `ast`** rather than from a hand-maintained list that can drift
- SHA-256 hashes of all source files for integrity verification
- `bom-ref` identifiers on every component so the dependency graph actually resolves
- Explicit declaration of zero external dependencies

**Determinism:** the substantive document is a pure function of repository
content. It carries no wall-clock value and no running-interpreter version, so
two checkouts of the same commit produce identical output on any machine. Only
`metadata.timestamp` and the content-derived `serialNumber` vary, and both are
excluded from the comparison. That is what makes `--check` meaningful and stops
CI from committing a timestamp-only SBOM change on every push.

## Running Tests

```bash
python -m pytest tests/ -v
```

305 unit tests covering input validation (including path-traversal edge cases), multi-repo path parsing, SIG categorization (including deterministic tiebreaks for both title and file-based heuristics), GraphQL variable shape, summary prompt building, summary generation (with timeout-bounds validation), LLM output cleaning, markdown rendering (including release-machinery filtering), incremental merging (with drop-warning behavior), dry-run, atomic I/O, stderr token redaction, PR body size capping, point-release tag parsing, sibling-tag discovery, merge-base extraction, cherry-pick container parsing, point-release audit sidecar generation, release-machinery classification, point-release awareness logging, merge-commit PR discovery, per-repo ref overrides and preflight ref
resolution, render reconciliation accounting, markdown/HTML escaping (including
the double-escape and raw-HTML regressions), subprocess timeout handling, atomic
write permissions and durability, SBOM determinism and dependency-graph
integrity, and security controls.

A `Makefile` is provided for the common targets:

```bash
make test         # run pytest
make sbom         # regenerate sbom.cdx.json
make sbom-check   # verify sbom.cdx.json is current (CI gate)
make lint         # ruff (if installed)
make typecheck    # mypy (if installed)
make check        # all of the above
```

## Security

This tool is designed with OWASP and NIST SP 800-53 security controls. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full security model, threat analysis, trust boundaries, and input validation specifications. To report a vulnerability, see [SECURITY.md](SECURITY.md).

Key highlights:
- Zero external dependencies (Python stdlib only)
- All subprocess calls use list arguments (no `shell=True`)
- All subprocess output decoded with `encoding='utf-8', errors='replace'`
- All user inputs validated with regex before use
- GraphQL queries use server-side variables (`$owner`, `$name`); no string interpolation
- GitHub auth delegated to `gh` CLI; stderr scrubbed for token shapes before logging
- Atomic file writes prevent data corruption
- PR titles and descriptions sanitized for markdown **and raw HTML** (tag-like `<` is escaped, so an `<img onerror=...>` in a PR title cannot become live HTML on a published page); PR bodies capped at 64KB before extraction
- LLM summary output passes through the same HTML neutralization
- Every `git` / `gh` invocation converts timeouts and missing binaries into handled errors instead of aborting a run mid-flight
- Atomic writes preserve the destination file's permissions and `fsync` before rename
- Summary command runtime bounded (`--summary-timeout`, default 300s, range 10–3600s)
- CycloneDX SBOM with source file hashes for supply chain transparency
- GitHub Actions pinned to commit SHAs (not floating tags)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev workflow, dual-license policy, and the GitHub Actions SHA-pinning policy.

## License

Apache-2.0 OR MIT (see [LICENSE.txt](LICENSE.txt))
