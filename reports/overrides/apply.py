"""Apply hand-written bullet descriptions to the release data JSON.

Usage: python reports/overrides/apply.py reports/26100_release_data.json reports/overrides/26100_*.txt

Each override file is a list of entries separated by blank lines. An entry's
first line is `<repo>#<number>`, the rest is the description. The text lands
in `manual_override_description`, which survives re-runs and takes effect on
the next render. The release data stays the single source of truth; these
files are the editing log.
"""
import json
import pathlib
import sys


def parse(path: pathlib.Path) -> dict[tuple[str, int], str]:
    entries: dict[tuple[str, int], str] = {}
    for block in path.read_text(encoding='utf-8').split('\n\n'):
        lines = [line.rstrip() for line in block.strip().splitlines() if line.strip()]
        if not lines or lines[0].startswith('#'):
            continue
        head, text = lines[0], ' '.join(line.strip() for line in lines[1:])
        repo, _, number = head.rpartition('#')
        if not repo or not number.isdigit() or not text:
            raise SystemExit(f'{path}: malformed entry starting {head!r}')
        key = (repo if '/' in repo else f'o3de/{repo}', int(number))
        if key in entries:
            raise SystemExit(f'{path}: duplicate entry for {head}')
        entries[key] = text
    return entries


def main() -> int:
    data_path = pathlib.Path(sys.argv[1])
    overrides: dict[tuple[str, int], str] = {}
    for arg in sys.argv[2:]:
        overrides.update(parse(pathlib.Path(arg)))
    data = json.loads(data_path.read_text(encoding='utf-8'))
    by_key = {(p['repo'], p['number']): p for p in data['pull_requests']}
    missing = [k for k in overrides if k not in by_key]
    if missing:
        raise SystemExit('not in the release data: ' + ', '.join(f'{r}#{n}' for r, n in missing))
    changed = 0
    for key, text in overrides.items():
        if by_key[key].get('manual_override_description') != text:
            by_key[key]['manual_override_description'] = text
            changed += 1
    data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{len(overrides)} override(s) read, {changed} changed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
