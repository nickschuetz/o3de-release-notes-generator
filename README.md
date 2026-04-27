# O3DE Release Notes Generator

A standalone tool that generates [Open 3D Engine (O3DE)](https://o3de.org) release notes by extracting merged pull requests from GitHub, categorizing them by SIG (Special Interest Group), and rendering markdown in the established release notes format.

Designed to be run incrementally throughout the pre-release cycle so the release team can track progress as PRs land.

## Prerequisites

- Python 3.10+
- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated (`gh auth login`)
- Local clone(s) of O3DE repositories (read-only reference)
- (Optional) An LLM for automated narrative summary generation — [Ollama](https://ollama.com/) (local, open-source) or [Claude CLI](https://claude.ai/claude-code) (cloud)

## Quick Start

```bash
# Generate release notes for 26.05.0 (everything since 25.10.0)
python release_notes.py generate \
  --from-ref 2510.0 \
  --to-ref development \
  --default-repo-path /path/to/o3de \
  --output-json release_data.json \
  --output-md 26050_release_notes.md \
  --release-version 26.05.0
```

## Project Structure

```
o3de_release_notes_generator/
├── README.md                       # This file
├── ARCHITECTURE.md                 # Architecture, security model, data flow
├── CHANGELOG.md                    # Version history (Keep a Changelog format)
├── CONTRIBUTING.md                 # Dev workflow, dual-license, SHA-pin policy
├── SECURITY.md                     # Vulnerability disclosure
├── AGENTS.md                       # AI agent instructions for this repo
├── release_notes.py                # Main script (zero external dependencies)
├── generate_sbom.py                # CycloneDX 1.5 SBOM generator
├── sbom.cdx.json                   # Generated SBOM (auto-updated via CI)
├── pyproject.toml                  # pytest / ruff / mypy config
├── Makefile                        # test / sbom / lint / typecheck targets
├── tests/
│   └── test_release_notes.py       # Unit tests
├── reports/                        # Sample rendered release notes (committed)
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
  [--dry-run] \
  [--log-file PATH] \
  [-v]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--from-ref` | Yes | - | Starting git reference (tag or commit) |
| `--to-ref` | Yes | - | Ending git reference (branch or tag) |
| `--default-repo-path` | No | `.` | Default local clone path for repos without explicit mapping |
| `--repo-path` | No | - | Per-repo clone paths as `owner/repo=/path/to/clone` (repeatable) |
| `--output-json` | Yes | - | Output JSON file path |
| `--repos` | No | `o3de/o3de` | GitHub repos in `owner/repo` format (where PRs live) |
| `--dry-run` | No | off | Print which PRs would be fetched (from git log) without calling the GitHub API or writing files |
| `--log-file` | No | - | Append logs to this file in addition to stderr |
| `-v` | No | - | Verbose logging |

### `render` - Generate markdown from JSON

```bash
python release_notes.py render \
  --input-json <input.json> \
  --output-md <output.md> \
  --release-version <version-string> \
  [--include-uncategorized] \
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
| `--generate-summary` | No | off | Generate a narrative summary using an LLM |
| `--summary-cmd` | No | `ollama run --nowordwrap qwen2.5:14b` | Command to generate the summary |
| `--summary-hint` | No | - | Narrative guidance — inline text or `@filepath` to read from a file |
| `--summary-timeout` | No | `300` | Timeout (seconds) for the summary command (range: 10–3600) |
| `--log-file` | No | - | Append logs to this file in addition to stderr |

### `generate` - Fetch and render in one step

Combines `fetch` and `render`. Accepts all flags from both subcommands.

## Examples

### Generate notes for a specific release

```bash
python release_notes.py generate \
  --from-ref 2510.0 \
  --to-ref development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md 26050_release_notes.md \
  --release-version 26.05.0
```

### Incremental update during pre-release

Re-run the same command. New PRs are fetched; existing data and any manual edits in the JSON are preserved.

```bash
# Week 1
python release_notes.py generate --from-ref 2510.0 --to-ref development \
  --default-repo-path ~/PROJECTS/o3de --output-json release_data.json \
  --output-md notes.md --release-version 26.05.0

# Week 2 (same command - only fetches new PRs)
python release_notes.py generate --from-ref 2510.0 --to-ref development \
  --default-repo-path ~/PROJECTS/o3de --output-json release_data.json \
  --output-md notes.md --release-version 26.05.0
```

### Multi-repo with separate local clones

```bash
python release_notes.py generate \
  --from-ref 2510.0 --to-ref development \
  --repos o3de/o3de o3de/o3de-extras \
  --default-repo-path ~/PROJECTS/o3de \
  --repo-path o3de/o3de-extras=~/PROJECTS/o3de-extras \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.05.0
```

Each repo runs `git log` against its own local clone. The `--default-repo-path` is used for any repo without an explicit `--repo-path` mapping.

### Generate with automated narrative summary

```bash
python release_notes.py generate \
  --from-ref 2510.0 --to-ref development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.05.0 \
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
  --from-ref 2510.0 --to-ref development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.05.0 \
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
  --from-ref 2510.0 --to-ref development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json
```

### Include uncategorized PRs for triage

```bash
python release_notes.py generate \
  --from-ref 2510.0 --to-ref development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json release_data.json \
  --output-md notes.md \
  --release-version 26.05.0 \
  --include-uncategorized
```

### Dry-run (preview which PRs would be fetched)

```bash
python release_notes.py fetch \
  --from-ref 2510.0 --to-ref development \
  --default-repo-path ~/PROJECTS/o3de \
  --output-json /tmp/unused.json \
  --dry-run
```

Reads `git log` locally and prints the PR numbers that would be fetched. No GitHub API calls; no files written. Useful for verifying refs and clone paths before a long run.

## Sample Output

A real run against `o3de/o3de` 25.10.0 → 26.05.0 (228 PRs) renders something like:

```markdown
# 26.05.0 Release Notes

The O3DE 26.05.0 release includes bug fixes, performance enhancements,
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

## JSON Schema

The intermediate JSON is the primary data format. It can be edited by humans or consumed by AI agents.

```json
{
  "metadata": {
    "generated_at": "2026-04-21T10:00:00+00:00",
    "from_ref": "2510.0",
    "to_ref": "development",
    "repos": ["o3de/o3de", "o3de/o3de-extras"],
    "repo_paths": {
      "o3de/o3de": "/home/user/PROJECTS/o3de",
      "o3de/o3de-extras": "/home/user/PROJECTS/o3de-extras"
    },
    "schema_version": 2,
    "pr_count": 228,
    "categorization_summary": {
      "label": 152,
      "heuristic_title": 55,
      "heuristic_files": 17,
      "uncategorized": 4
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
| `flags` | Auto-detected flags: `cherry-pick`, `stabilization-sync`. Flagged PRs are excluded from rendered markdown. |
| `manual_override_sig` | Set this to reassign a PR to a different SIG. Preserved on re-runs. |
| `manual_override_description` | Set this to override the auto-generated description. Preserved on re-runs. |

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

To **adjust** an existing SIG's heuristics, edit `SIG_TITLE_KEYWORDS` and/or `SIG_FILE_PATH_PATTERNS`. To **add a new SIG**, you must update *all four* — otherwise the new SIG either won't render (missing display name) or won't be picked up at all (missing from canonical order).

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
python generate_sbom.py
```

The SBOM captures:
- Project metadata (name, version, license, repository URL)
- Python stdlib modules used as dependencies (13 modules)
- SHA-256 hashes of all source files for integrity verification
- Explicit declaration of zero external dependencies

## Running Tests

```bash
python -m pytest tests/ -v
```

163 unit tests covering input validation, multi-repo path parsing, SIG categorization (including deterministic tiebreaks), GraphQL variable shape, summary prompt building, summary generation (with timeout-bounds validation), markdown rendering, incremental merging (with drop-warning behavior), dry-run, atomic I/O, stderr token redaction, PR body size capping, and security controls.

A `Makefile` is provided for the common targets:

```bash
make test         # run pytest
make sbom         # regenerate sbom.cdx.json
make lint         # ruff (if installed)
make typecheck    # mypy (if installed)
```

## Security

This tool is designed with OWASP and NIST SP 800-53 security controls. See [ARCHITECTURE.md](ARCHITECTURE.md) for the full security model, threat analysis, trust boundaries, and input validation specifications. To report a vulnerability, see [SECURITY.md](SECURITY.md).

Key highlights:
- Zero external dependencies (Python stdlib only)
- All subprocess calls use list arguments (no `shell=True`)
- All subprocess output decoded with `encoding='utf-8', errors='replace'`
- All user inputs validated with regex before use
- GraphQL queries use server-side variables (`$owner`, `$name`) — no string interpolation
- GitHub auth delegated to `gh` CLI; stderr scrubbed for token shapes before logging
- Atomic file writes prevent data corruption
- PR titles sanitized to prevent markdown injection; PR bodies capped at 64KB before extraction
- Summary command runtime bounded (`--summary-timeout`, default 300s, range 10–3600s)
- CycloneDX SBOM with source file hashes for supply chain transparency
- GitHub Actions pinned to commit SHAs (not floating tags)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev workflow, dual-license policy, and the GitHub Actions SHA-pinning policy.

## License

Apache-2.0 OR MIT (see [LICENSE.txt](LICENSE.txt))
