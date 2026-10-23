"""Apply hand-written bullet descriptions to the release data JSON.

Usage: python reports/overrides/apply.py reports/26100_release_data.json reports/overrides/26100_*.txt

At least one override file is required. Exclusions are authoritative (see
below), so a run with only the data file would clear every exclusion; the
script prints usage and exits 2 instead.

Each override file is a list of entries separated by blank lines. An entry's
first line is `<repo>#<number>`, the rest is the description. The text lands
in `manual_override_description`, which survives re-runs and takes effect on
the next render. An entry whose first line is `exclude <repo>#<number>` puts
the text in `manual_override_exclude` instead, and the PR leaves the report.
Exclusions are authoritative: any PR not named in an `exclude` entry has the
field cleared. The release data stays the single source of truth; these files
are the editing log.
"""
import json
import pathlib
import sys


Entries = dict[tuple[str, int], str]


def parse(path: pathlib.Path) -> tuple[Entries, Entries]:
    """Return (descriptions, exclusions) read from one file."""
    descriptions: Entries = {}
    exclusions: Entries = {}
    for block in path.read_text(encoding='utf-8').split('\n\n'):
        lines = [line.rstrip() for line in block.strip().splitlines() if line.strip()]
        if not lines or lines[0].startswith('#'):
            continue
        head, text = lines[0], ' '.join(line.strip() for line in lines[1:])
        target = descriptions
        if head.startswith('exclude '):
            target = exclusions
            head = head[len('exclude '):].strip()
        repo, _, number = head.rpartition('#')
        if not repo or not number.isdigit() or not text:
            raise SystemExit(f'{path}: malformed entry starting {head!r}')
        key = (repo if '/' in repo else f'o3de/{repo}', int(number))
        if key in target:
            raise SystemExit(f'{path}: duplicate entry for {head}')
        target[key] = text
    return descriptions, exclusions


def main() -> int:
    if len(sys.argv) < 3:
        print('usage: apply.py <release_data.json> <override.txt> [<override.txt> ...]\n'
              'Refusing to run without override files: exclusions are authoritative, so an\n'
              'empty set would clear every manual_override_exclude in the data file.',
              file=sys.stderr)
        return 2
    data_path = pathlib.Path(sys.argv[1])
    overrides: Entries = {}
    exclusions: Entries = {}
    for arg in sys.argv[2:]:
        descriptions, excluded = parse(pathlib.Path(arg))
        overrides.update(descriptions)
        exclusions.update(excluded)
    data = json.loads(data_path.read_text(encoding='utf-8'))
    by_key = {(p['repo'], p['number']): p for p in data['pull_requests']}
    missing = [k for k in list(overrides) + list(exclusions) if k not in by_key]
    if missing:
        raise SystemExit('not in the release data: ' + ', '.join(f'{r}#{n}' for r, n in missing))
    changed = 0
    for key, text in overrides.items():
        if by_key[key].get('manual_override_description') != text:
            by_key[key]['manual_override_description'] = text
            changed += 1
    excluded_changed = 0
    for key, pr in by_key.items():
        wanted = exclusions.get(key)
        if pr.get('manual_override_exclude') != wanted:
            pr['manual_override_exclude'] = wanted
            excluded_changed += 1
    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{len(overrides)} override(s) read, {changed} changed; '
          f'{len(exclusions)} exclusion(s) read, {excluded_changed} changed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
