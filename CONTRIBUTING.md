# Contributing

Thanks for considering a contribution! This is a small, single-file tool — keeping it simple and dependency-free is an explicit design goal.

## Quick start

```bash
git clone https://github.com/nickschuetz/o3de_release_notes_generator
cd o3de_release_notes_generator

make test         # run pytest (you don't even need to install the project)
make sbom         # regenerate sbom.cdx.json
make lint         # ruff (skipped if not installed)
make typecheck    # mypy (skipped if not installed)
```

You only need Python 3.10+ on `PATH`. There is no `pip install` step because there are no runtime dependencies.

## Development workflow

1. **Open or claim an issue** before doing significant work, so duplicate effort can be avoided.
2. **Branch from `main`.** Use a descriptive branch name (`fix/title-tiebreak-determinism`, `feat/dry-run`, etc).
3. **Add or update tests** for any behavior change. The full suite must pass on Python 3.10, 3.11, and 3.12 — CI runs all three (`.github/workflows/test.yml`).
4. **Update documentation** when you add or change a flag, an environment expectation, or a public function. The relevant places are usually `README.md`, `ARCHITECTURE.md`, and `AGENTS.md`. If the change is user-visible, also add an entry to `CHANGELOG.md` under a new `[Unreleased]` heading or the next pending version.
5. **Open a PR** against `main`. Keep PRs focused and small where possible.

## Code conventions

These are not preferences — they are project invariants. PRs that violate them will be asked to revise.

- **Zero external dependencies.** Stdlib only. Do not add `pip` packages. If you genuinely need one, open an issue first to discuss.
- **No `shell=True`.** Every `subprocess.run` call uses list arguments, with `encoding='utf-8', errors='replace'`.
- **Validate untrusted input at the boundary.** Git refs, repo slugs, file paths, PR numbers, summary commands, and summary timeouts are all validated by named functions. Reuse them.
- **GraphQL goes through variables, not strings.** Owner/name/anything user-influenced gets passed via `gh api graphql -f key=value`, not interpolated into the query body.
- **No tokens in logs.** All subprocess stderr passes through `_safe_stderr()` before being logged.
- **Atomic writes.** Use `tempfile.mkstemp()` + `os.replace()` for any file you produce.
- **Deterministic output.** When tiebreaking between SIGs (labels or title keywords), use `SIG_CANONICAL_ORDER`. Do not introduce ordering that depends on dict iteration or API response order.
- **Comments explain why, not what.** Good identifier names already describe what the code does — comment only when the why is non-obvious (a hidden constraint, a subtle invariant, a workaround for a specific bug).

## Tests

```bash
python -m pytest tests/ -v
```

The test suite uses `pytest` and `unittest.mock`. **No network calls.** All `gh` / `git` / LLM invocations are mocked. If you need new test infrastructure, prefer adding a fixture to the existing file over creating a new file.

## Licensing

This project is dual-licensed under [Apache License 2.0](LICENSE_APACHE2.TXT) **OR** [MIT License](LICENSE_MIT.TXT) (your choice). **All contributions must be made under both licenses** — by submitting a PR you certify that you have the right to do so under both terms. This matches the licensing of the upstream Open 3D Engine project.

If your contribution is non-trivial and you have not contributed before, please add yourself to the contributor list (when one exists) or note your assent in the PR description: _"I, &lt;name&gt;, license my contribution under Apache-2.0 OR MIT."_

## Security issues

**Do not open a public GitHub issue for a security vulnerability.** See [SECURITY.md](SECURITY.md) for the disclosure process.

## GitHub Actions pinning policy

All GitHub Actions used in `.github/workflows/*.yml` are **pinned to commit SHAs**, not floating tags. The human-readable version (`v4.2.2` etc.) is tracked in a comment beside the SHA so the pin is auditable.

When updating an action:

1. Find the new commit SHA on the action's GitHub releases page.
2. Update **both** the SHA and the version comment.
3. Verify CI passes on the bump.

Dependabot will propose these updates automatically once `.github/dependabot.yml` is added (TODO — open a PR if you'd like to add it).

## Style

- Format: 4-space indents, ~100-column soft wrap. We do not currently enforce a formatter, but `ruff format` is welcome.
- Lint: `ruff check` is the configured linter (see `pyproject.toml`).
- Types: `mypy --strict` should pass. Add type hints to new code.
- Tests follow the existing class-per-feature pattern; one assertion per behavior is preferred.

## Changelog

We follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Add your entry under the next pending version's heading, in the appropriate `Added` / `Changed` / `Removed` / `Security` section.
