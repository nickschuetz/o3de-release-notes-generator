# Release Runbook

Step-by-step procedure for producing O3DE release notes with this tool. Written
for the 26.10.0 cycle; the shape is the same for any release.

## 0. Know your refs, and why the tag alone is not enough

| Repo | 26.10.0 `--from-ref` | Notes |
|------|----------------------|-------|
| `o3de/o3de` | `2605.0` | Use the latest `2605.N` point-release tag if any have shipped |
| `o3de/o3de-extras` | `2510.2` | **Not tagged on the 2605 line.** Pass via `--repo-from-ref` |

`--to-ref` is `origin/development` until the stabilization branch is cut, then
`origin/stabilization/26100`.

**You must also pass `--exclude-json` pointing at the previous release's
report.** `2605.0` tags a commit on `origin/main`, which O3DE builds from
periodic "merge stabilization to main" commits, so its merge-base with
`development` is `57680ee42` (2025-07-29), before the 26.05 cycle began. The raw
window therefore spans two cycles:

| Window | PRs | Already in 26.05.0 | New |
|---|---|---|---|
| `o3de/o3de` `2605.0..development` | 369 | 188 | 181 |
| `o3de/o3de-extras` `2510.2..development` | 50 | 30 | 20 |

The duplicates are development-side merges of fixes that reached 26.05.0 by
cherry-pick into `stabilization/26050`: distinct commits, unreachable from the
tag. No other `--from-ref` fixes this (`origin/main` gives an identical 369/188),
and a date cutoff cannot either, because the two sets interleave. Changing
`--to-ref` to `origin/stabilization/26100` will not help; the overlap comes from
the `--from-ref` anchor.

Reports are named per release (`reports/26050_release_data.json`,
`reports/26100_release_data.json`), so each cycle's output never overwrites the
exclusion source it depends on.

**Retention:** keep the previous cycle's `*_release_data.json` checked in. It is
the `--exclude-json` source for the next cycle, and deleting it does not fail
loudly: the run succeeds and silently re-publishes the previous release's
content. The rendered `*_release_notes.md` and `*_pointrelease_audit.md` from
closed cycles are outputs, not inputs, and can be pruned once the notes are
published to docs.o3de.org, which is their canonical home. Hint files under
`reports/hints/` are reused across cycles for narrative continuity; keep them.

Spring releases (`xx.05.0`) are gaming-themed; fall releases (`xx.10.0`) are
robotics-themed. That shapes the narrative summary, not the tooling.

## 1. Refresh the clones

Stale clones are the most common cause of a wrong PR count. `git log` cannot see
commits you have not fetched, and missing tags fail the ref preflight.

```bash
for r in ~/PROJECTS/o3de ~/PROJECTS/o3de-extras; do
  git -C "$r" fetch --all --tags --prune
done
```

## 2. Dry-run first

No GitHub API calls, no files written. Confirms refs resolve, clone paths are
right, and the PR count is plausible.

```bash
python release_notes.py fetch \
  --from-ref 2605.0 \
  --to-ref origin/development \
  --repos o3de/o3de o3de/o3de-extras \
  --repo-path o3de/o3de=~/PROJECTS/o3de \
  --repo-path o3de/o3de-extras=~/PROJECTS/o3de-extras \
  --repo-from-ref o3de/o3de-extras=2510.2 \
  --exclude-json reports/26050_release_data.json \
  --output-json /tmp/unused.json \
  --dry-run
```

Check:

- Every repo reports a PR count. A zero count means the range is wrong.
- The `PR(s) found via merge commits` line appears for `o3de/o3de`. O3DE uses
  merge commits for a meaningful share of PRs; a zero there is suspicious.
- No ref-resolution errors. If a ref does not resolve, either fetch tags or give
  that repo its own ref with `--repo-from-ref` / `--repo-to-ref`.
- **The "already reported in a prior release, excluded" count is non-trivial.**
  For 26.10.0 it should be roughly 188 for `o3de` and 30 for `o3de-extras`. A
  count of zero means `--exclude-json` is missing or pointing at the wrong file,
  and the report will re-publish the previous release's content.

## 3. Generate

```bash
python release_notes.py generate \
  --from-ref 2605.0 \
  --to-ref origin/development \
  --repos o3de/o3de o3de/o3de-extras \
  --repo-path o3de/o3de=~/PROJECTS/o3de \
  --repo-path o3de/o3de-extras=~/PROJECTS/o3de-extras \
  --repo-from-ref o3de/o3de-extras=2510.2 \
  --exclude-json reports/26050_release_data.json \
  --output-json reports/26100_release_data.json \
  --output-md reports/26100_release_notes.md \
  --release-version 26.10.0 \
  --log-file reports/generate.log
```

Roughly one GraphQL request per 30 PRs, so a ~420-PR cycle is about 14 requests.

## 4. Read the reconciliation line

This is the most important check in the runbook.

```
Reconciliation: 419 PR(s) in JSON, 402 rendered
Excluded 17 PR(s) from the report: cherry-pick=12, release_machinery=1, uncategorized=4
```

- The counts are mutually exclusive and sum to the total. Nothing is dropped
  silently.
- A sudden jump in any excluded bucket means a heuristic has started
  over-matching. Investigate before publishing. A filter over-matching on labels
  is what removed 57 real PRs from the 26.05.0 notes.
- `uncategorized` should be small. Re-run `render` with `--include-uncategorized`
  to see them and assign each one via `manual_override_sig`.
- `duplicate` means two PRs carried the same title and the same changed files, so
  only one bullet was rendered. Each collapsed group is logged by number. Skim
  those lines: the rule is deliberately strict, but a curator is the last check
  on whether the two really were one change. `--include-duplicates` renders all
  of them if you disagree.

## 5. Triage

Inspect what was excluded:

```bash
python release_notes.py render \
  --input-json reports/26100_release_data.json \
  --output-md /tmp/triage.md \
  --release-version 26.10.0 \
  --include-uncategorized --include-release-machinery
```

Fix categorization in `reports/26100_release_data.json` by setting, per PR:

- `manual_override_sig` to reassign the SIG
- `manual_override_description` to rewrite the bullet

Both survive re-runs. **Editing `sig_category` or `description` directly does
not survive**: a PR that later disappears from `git log` is dropped unless it
carries a `manual_override_*` field, and the drop is logged as a WARNING.

## 6. Narrative summary

```bash
python release_notes.py render \
  --input-json reports/26100_release_data.json \
  --output-md reports/26100_release_notes.md \
  --release-version 26.10.0 \
  --generate-summary \
  --summary-hint @reports/hints/prior_release_themes.txt
```

Keep a hint file per cycle under `reports/hints/` so the theme and tone stay
stable across mid-cycle re-runs. 26.10.0 is a robotics-themed fall release.

Always read the generated narrative before publishing. It is model output
derived from untrusted PR titles; tag-like `<` is escaped so it cannot inject
raw HTML, but nothing validates the claims it makes.

## 7. Point-release audit (when applicable)

If `--from-ref` is a non-zero point-release tag (e.g. `2605.2`), the tool writes
`reports/26100_release_notes_pointrelease_audit.md`. Every bundled PR from each
cherry-pick container is marked ✓ (present) or ✗ (missing).

Investigate every ✗ before publishing. Suppress the sidecar with
`--no-pointrelease-audit` if it is not relevant.

## 8. Pre-publication checklist

- [ ] Clones fetched with `--tags` immediately before the run
- [ ] Dry-run PR counts plausible for both repos
- [ ] `--exclude-json` supplied, and its exclusion count is non-zero
- [ ] Spot-check that no PR in the report also appears in the previous cycle's report
- [ ] Reconciliation line read; every exclusion bucket understood
- [ ] `uncategorized` triaged to zero, or consciously accepted
- [ ] Point-release audit has no unexplained ✗ entries
- [ ] Narrative summary read end to end
- [ ] Spot-check a few bullets against their PRs on GitHub
- [ ] `metadata.tool_version` in the JSON matches the version you intended to run

## Re-running mid-cycle

Re-run the same command, including `--exclude-json`. `manual_override_*` fields
are re-applied on every run.

By default the full range is re-fetched. Add `--reuse-existing` to serve
label-categorised PRs from the previous report instead: on the 26.10.0 draft that
halved the request count (8 batches to 4) and produced byte-identical output.

PRs categorised heuristically or left uncategorised are always re-fetched, so a
`sig/*` label applied since the last run is picked up. That is deliberate: those
are precisely the PRs whose categorisation is most likely to be wrong and most
likely to improve.

## Maintaining the tool itself

```bash
make check    # pytest + ruff + mypy strict + SBOM freshness
make sbom     # regenerate sbom.cdx.json after touching any .py file
```

CI runs the same gates on Python 3.10 through 3.13.
