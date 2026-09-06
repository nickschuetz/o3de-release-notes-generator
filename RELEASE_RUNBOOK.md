# Release Runbook

Step-by-step procedure for producing O3DE release notes with this tool. Written
for the 26.10.0 cycle; the shape is the same for any release.

## 0. Know your refs, and why the tag alone is not enough

| Repo | 26.10.0 `--from-ref` | Notes |
|------|----------------------|-------|
| `o3de/o3de` | `2605.0` | Use the latest `2605.N` point-release tag if any have shipped |
| `o3de/o3de-extras` | `2605.0` | Tagged on the 2605 line as of 2026-05-27 (`8e7f0f04`). No `--repo-from-ref` needed |

`--to-ref` is `origin/development` until the stabilization branch is cut, then
`origin/stabilization/26100`. Both were cut for 26.10.0 on 2026-08-11.

`o3de-extras` was untagged on the 2605 line for most of the cycle, and this
runbook told you to pass `--repo-from-ref o3de/o3de-extras=2510.2`. That is no
longer needed and is now slightly wrong: the wider window reaches back past
26.05.0 and relies entirely on `--exclude-json` to remove it, which pulls in any
PR that shipped in 26.05.0 but was never reported there (#1021 was one). Use the
release tag as the boundary and let exclusion handle only genuine overlap.

**You must also pass `--exclude-json` pointing at the previous release's
report.** `2605.0` tags a commit on `origin/main`, which O3DE builds from
periodic "merge stabilization to main" commits, so its merge-base with
`development` is `57680ee42` (2025-07-29), before the 26.05 cycle began. The raw
window therefore spans two cycles:

| Window | PRs | Already in 26.05.0 | New |
|---|---|---|---|
| `o3de/o3de` `2605.0..stabilization/26100` | 388 | 188 | 200 |
| `o3de/o3de-extras` `2605.0..stabilization/26100` | 22 | 1 | 21 |

(Measured 2026-08-20. The `o3de` figure grows as the cycle continues; the
188 already-reported count does not.)

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

## 0a. The 26.10.0 schedule

Authoritative source: [o3de/sig-release#372](https://github.com/o3de/sig-release/issues/372).
Release manager: @nickschuetz. Docs PM: @ShaunaGordon.

| Date | Milestone | What it means for the notes |
|---|---|---|
| Aug. 11, 2026 | Stabilization branches created | `--to-ref` switches to `origin/stabilization/26100` |
| Aug. 11 – Sept. 15 | Stabilization Phase I | Features still allowed via exception, so the draft moves a lot. Re-run weekly |
| Sept. 16, 2026 | Code freeze, Major bugs and below | Feature set is effectively final. Good point to start the narrative summary |
| Sept. 16 – Oct. 6 | Stabilization Phase II | Bug fixes only, by exception. Draft should be nearly stable |
| Oct. 7, 2026 | Code freeze, Critical and below | Only Blocker fixes land after this |
| Oct. 7 – Oct. 22 | QA final smoke test | Notes should be final in all but wording |
| Oct. 23, 2026 | Release considered stable | Freeze the notes |
| Oct. 28, 2026 | Release day; repos tagged | Tag `2610.0` becomes the next cycle's `--from-ref` |
| Oct. 29, 2026 | Marketing announcement | |

The Docs milestone "(Docs) Release Notes Finalized (features + known issues)"
is still **TBD** on the issue. That date is the real deadline for this tool's
output, so it is worth pinning early.

**Repo coverage is narrower than the release.** Release day tags `o3de`,
`o3de-multiplayersample`, `o3de-netsoaktest`, `o3de-extras`, and
`o3de-atom-sampleviewer`. The notes cover only the first and fourth, matching
26.05.0. As of 2026-08-20 the other three have almost nothing to report
(1, 0 and 0 merged PRs since 2026-05-27), so this is a known and currently
harmless gap rather than a silent one. Adding them is a `--repos` change plus
a `--repo-path`/`--repo-from-ref` per repo if that ever changes.

**Bug tracking:** fixes land against the
[Release/2610 milestone](https://github.com/o3de/o3de/milestone/17); stabilization
bugs carry `branch/stabilization` and sit on
[project board 89](https://github.com/orgs/o3de/projects/89). Exceptions are
tracked on [board 90](https://github.com/orgs/o3de/projects/90).

## 1. Refresh the clones

Stale clones are the most common cause of a wrong PR count. `git log` cannot see
commits you have not fetched, and missing tags fail the ref preflight.

```bash
for r in ~/PROJECTS/o3de ~/PROJECTS/o3de-extras; do
  git -C "$r" fetch --all --tags --prune
done
```

**Check two things about each clone before trusting any count.**

*Is it shallow?* A shallow clone answers `git log A..B` from whatever history it
holds, with no error. On 2026-08-20 a routine `fetch --all` on the o3de clone
re-fetched the branch refs under shallow rules and cut them to ~20 commits each,
while the tag kept its full 26,947. The window collapsed from ~200 PRs to 18 and
nothing in the output said why. The tool now warns during preflight, but verify:

```bash
for r in ~/PROJECTS/o3de ~/PROJECTS/o3de-extras; do
  echo "$r shallow=$(git -C "$r" rev-parse --is-shallow-repository)"
done
```

If shallow, deepen past the previous release before generating. A dated fetch is
far cheaper than `--unshallow` on a 2.4 GB repo:

```bash
git -C ~/PROJECTS/o3de fetch --shallow-since=2025-06-01 upstream \
  development stabilization/26100
```

Confirm the repair by checking that the merge-base resolves at all. It returns
nothing on a too-shallow clone:

```bash
git -C ~/PROJECTS/o3de merge-base 2605.0 origin/stabilization/26100
# expect 57680ee42f18d5952e4d4fa5ab52750edefb878e for the 26.10.0 window
```

*Where does `origin` point?* In a maintainer's clone `origin` is often a personal
fork and `o3de/o3de` is `upstream`. `--to-ref origin/development` then reads the
fork, which silently lags whenever you have not synced it. Either sync the fork,
or pass upstream refs explicitly:

```bash
git -C ~/PROJECTS/o3de remote -v   # confirm which remote is which
```

## 2. Dry-run first

No GitHub API calls, no files written. Confirms refs resolve, clone paths are
right, and the PR count is plausible.

```bash
python release_notes.py fetch \
  --from-ref 2605.0 \
  --to-ref origin/stabilization/26100 \
  --repos o3de/o3de o3de/o3de-extras \
  --repo-path o3de/o3de=~/PROJECTS/o3de \
  --repo-path o3de/o3de-extras=~/PROJECTS/o3de-extras \
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
- **The "already reported in a prior release, excluded" count is non-trivial
  for `o3de`.** For 26.10.0 it should be about 188. A count of zero means
  `--exclude-json` is missing or pointing at the wrong file, and the report will
  re-publish the previous release's content. For `o3de-extras` the expected
  count is now ~1, not 30: with `2605.0` as its `--from-ref` the window no
  longer reaches back past 26.05.0, so there is almost nothing to exclude. A
  large exclusion count there means the old `2510.2` boundary crept back in.
- **The total looks like a release, not a handful.** ~200 for `o3de`. A count in
  the low tens means a truncated clone (see step 1), not a quiet cycle.

## 3. Generate

```bash
python release_notes.py generate \
  --from-ref 2605.0 \
  --to-ref origin/stabilization/26100 \
  --repos o3de/o3de o3de/o3de-extras \
  --repo-path o3de/o3de=~/PROJECTS/o3de \
  --repo-path o3de/o3de-extras=~/PROJECTS/o3de-extras \
  --exclude-json reports/26050_release_data.json \
  --output-json reports/26100_release_data.json \
  --output-md reports/26100_release_notes.md \
  --release-version 26.10.0 \
  --log-file reports/generate.log
```

Roughly one GraphQL request per 30 PRs, so a ~420-PR cycle is about 14 requests.
Add `--reuse-existing` on mid-cycle re-runs to serve label-categorised PRs from
the previous report instead of re-fetching them.

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

## 7. Cherry-pick audit

The tool writes an audit sidecar in two situations:

| Trigger | Sidecar | Window scanned |
|---|---|---|
| `--to-ref` is a `stabilization/NNNNN` branch | `..._cherrypick_audit.md` | `--from-ref`..`--to-ref` |
| `--from-ref` is a non-zero point-release tag | `..._pointrelease_audit.md` | major tag..`--from-ref` |

**Why the stabilization case matters.** During stabilization, fixes reach the
release branch by cherry-pick. When a cherry-pick PR is *merged*, each picked
commit keeps its original `(#NNNN)` subject, so the fix enters the report under
its own number and filtering the container out is harmless. That is what
happened with #20006 / #19998 on 2026-08-12. When a container is *squashed*, it
carries only its own number, is filtered out as a cherry-pick, and takes every
fix it bundles with it. The sidecar exists to catch that.

Both outcomes are audited. A squashed container is recognised by the PR
numbers in its body (GitHub keeps the picked subjects there), so the title
wording does not matter; a merge-commit container is listed with a note and
its bundled fixes shown ✓. The merge button is still the thing to watch on a
cherry-pick PR against the release branch: **Create a merge commit** keeps
every fix under its own number, **Squash and merge** loses them all and the
sidecar turns red. `#20006` was merged the right way, and so was `#20091`
(11 fixes, merged 2026-09-04): the 2026-09-06 sidecar lists it as a merge
commit with all 11 ticked.

Each bundled PR is marked:

- ✓ present in the rendered report
- ⚠ collected but filtered out (reason shown). Verify the filter.
- ○ already reported in a prior release, so correctly absent
- ✗ in neither this report nor any prior one

Check every ⚠ and ✗ before publishing. A ✗ is not automatically a loss: the
window reaches back to the merge-base, so containers from earlier cycles appear
too. The 2026-09-03 run showed 9, all from the 26.05 and 25.10 cycles, and
#19777 among them turned out to be a genuine gap in the 26.05.0 notes rather
than anything owed to 26.10.0. A container that predates the branch cut
belongs to an earlier cycle by construction.

Suppress the sidecar with `--no-pointrelease-audit`.

## 7a. Track the sync labels

Two labels bracket the release branch, and they answer different questions.

### `need-sync/to-stabilization` — what is still owed to the release

[Open PRs with this label](https://github.com/o3de/o3de/issues?q=state%3Aopen%20label%3Aneed-sync%2Fto-stabilization)
are destined for this release but are not in it yet. This is the forward-looking
queue: the draft grows as each one is merged and cherry-picked.

```bash
# still owed to the release
gh api --paginate 'repos/o3de/o3de/issues?labels=need-sync/to-stabilization&state=all&per_page=100' \
  --jq '.[] | select(.pull_request != null) | "\(.number)\t\(.state)\t\(.title)"'
```

The dangerous state is **merged but not yet cherry-picked**. Such a PR is in
`development`, flagged as release content, and absent from the notes. As of
2026-09-06 that is `#20093`, `#20075` and `#20071` (merged Sep 4 and 5, after
`#20091` collected the previous eleven). When a cherry-pick lands, the label is swapped for
`sync/to-stabilization`: 44 closed PRs carry that one, none carry both, so a
merged PR still wearing `need-sync/to-stabilization` after its cherry-pick
merged is a labelling miss, not a missing fix. Compare the two windows by PR
number, not by commit SHA: a cherry-pick has a different SHA, so a SHA-based
diff reports fixes as pending that are already on the branch (`#19998` looks
pending that way and is not).

```bash
prs() { git log --format=%s "$1" | grep -oE '\(#[0-9]+\)$|^Merge pull request #[0-9]+' \
        | grep -oE '[0-9]+' | sort -un; }
comm -23 <(prs 2605.0..upstream/development) <(prs 2605.0..origin/stabilization/26100)
```

That currently yields 5: `#20003 #20004 #20005 #20008 #20013`. Only `#20013`
carries the label, so the rest are not (yet) claimed for this release.

**Run this against `upstream/development`, not `origin/development`.** The fork
lags, and it was 2 commits behind on 2026-08-20 — enough to hide `#20013`
entirely.

### `need-sync/to-development` — what came in through the back door

PRs merged **directly into the stabilization branch** carry this label so they
get ported back to `development`. They matter to the notes for a different
reason: they never pass through `development`, so a report generated with
`--to-ref origin/development` cannot see them at all.

That class was missed before. `#19777` merged to `stabilization/26050`, shipped
in 26.05.0 (its merge commit is an ancestor of the `2605.0` tag), and appears in
no report. `#20009` is the 26.10.0 equivalent and is in the draft under
SIG-Release, because this cycle generates from stabilization.

### Neither label is an exclusion signal

Both mark real product changes. A substring match on the similarly-named
`sync/to-stabilization` once deleted 57 real changes from a shipped report,
which is why cherry-pick detection uses title evidence and never labels.

## 8. Pre-publication checklist

- [ ] Clones fetched with `--tags` immediately before the run
- [ ] Neither clone is shallow, or it is deep enough that `merge-base` resolves
- [ ] `origin` verified as the intended remote, not an unsynced personal fork
- [ ] Dry-run PR counts plausible for both repos
- [ ] `--exclude-json` supplied, and its exclusion count is non-zero
- [ ] Spot-check that no PR in the report also appears in the previous cycle's report
- [ ] Reconciliation line read; every exclusion bucket understood
- [ ] `uncategorized` triaged to zero, or consciously accepted
- [ ] Point-release audit has no unexplained ✗ entries
- [ ] No **merged** PR still carries `need-sync/to-stabilization`. One that does
      was intended for this release and never cherry-picked, so it is missing
      from the notes and from the build
- [ ] Pending-cherry-pick list compared by PR number against `upstream/development`
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
