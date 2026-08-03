#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright Contributors to the Open 3D Engine

"""
Generates a CycloneDX 1.5 SBOM (JSON) for the o3de-release-notes-generator project.

This project has zero external dependencies; only Python stdlib modules are used.
The SBOM captures:
  - The project as the top-level component
  - Python stdlib modules as framework dependencies
  - SHA-256 hashes of all source files for integrity verification
  - Tool and metadata information
"""

import ast
import contextlib
import hashlib
import json
import os
import pathlib
import stat
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

PROJECT_NAME = 'o3de_release_notes_generator'
PROJECT_VERSION = '0.6.1-beta'
PROJECT_DESCRIPTION = 'Generates O3DE release notes from merged pull requests'
PROJECT_LICENSE_ID = 'Apache-2.0 OR MIT'
PROJECT_REPO = 'https://github.com/nickschuetz/o3de-release-notes-generator'
MIN_PYTHON_VERSION = '3.10'

SOURCE_FILES = [
    'release_notes.py',
    'generate_sbom.py',
    'tests/test_release_notes.py',
]

# Modules that are part of the project itself or of the test harness, not
# components of the shipped tool.
NON_COMPONENT_MODULES = frozenset({
    'release_notes',
    'generate_sbom',
    'pytest',
    'unittest',
})


def discover_stdlib_modules(project_dir: pathlib.Path) -> list[str]:
    """Parse SOURCE_FILES and return the stdlib modules they import.

    Derived rather than hand-listed: the previous static list had drifted and
    omitted `contextlib`, `shlex`, and `typing`, so the SBOM under-reported the
    very inventory it exists to attest to.
    """
    modules: set[str] = set()
    for relpath in SOURCE_FILES:
        filepath = project_dir / relpath
        if not filepath.exists():
            continue
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split('.')[0])
            # Relative imports (level > 0) are intra-project, not dependencies.
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split('.')[0])
    return sorted(modules - NON_COMPONENT_MODULES)


def _resolve_timestamp() -> str:
    """When this document was generated. Honours SOURCE_DATE_EPOCH.

    This is the one field that legitimately varies between runs, so it is
    excluded from the substantive comparison in `_substantive()`.
    """
    epoch = os.environ.get('SOURCE_DATE_EPOCH', '').strip()
    if epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _substantive(sbom: dict[str, Any]) -> dict[str, Any]:
    """The SBOM minus the fields that necessarily vary per run.

    Everything else is a pure function of repository content, so two checkouts
    of the same commit produce byte-identical substantive documents regardless
    of machine, interpreter build, or clock.
    """
    trimmed = {k: v for k, v in sbom.items() if k != 'serialNumber'}
    trimmed['metadata'] = {k: v for k, v in sbom['metadata'].items() if k != 'timestamp'}
    return trimmed


def sha256_file(filepath: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def generate_sbom(project_dir: pathlib.Path) -> dict[str, Any]:
    timestamp = _resolve_timestamp()
    stdlib_modules = discover_stdlib_modules(project_dir)

    file_components = []
    for relpath in SOURCE_FILES:
        filepath = project_dir / relpath
        if not filepath.exists():
            continue
        file_hash = sha256_file(filepath)
        file_components.append({
            'type': 'file',
            # bom-ref is what makes a component addressable in the dependency
            # graph. Without it the `dependsOn` entries below referenced
            # nothing and strict CycloneDX validation flagged dangling refs.
            'bom-ref': f'file:{relpath}',
            'name': relpath,
            'hashes': [{'alg': 'SHA-256', 'content': file_hash}],
        })

    stdlib_components = []
    for mod_name in stdlib_modules:
        stdlib_components.append({
            'type': 'library',
            'bom-ref': f'stdlib:{mod_name}',
            'name': mod_name,
            # The minimum supported interpreter, NOT platform.python_version().
            # Using the running interpreter made the document differ between a
            # 3.12 CI runner and a 3.14 workstation, so it could never be
            # verified as current.
            'version': MIN_PYTHON_VERSION,
            'scope': 'required',
            # `pkg:pypi/cpython-stdlib/...` pointed at a PyPI package that does
            # not exist, which makes scanners report a phantom component.
            # pkg:generic is the correct namespace for something that ships
            # with the interpreter rather than from a package index.
            'purl': f'pkg:generic/{mod_name}@{MIN_PYTHON_VERSION}?distro=cpython-stdlib',
            'description': f'Python stdlib module: {mod_name}',
            'properties': [
                {'name': 'cdx:source', 'value': 'python-stdlib'},
            ],
        })

    components = stdlib_components + file_components

    sbom = {
        '$schema': 'http://cyclonedx.org/schema/bom-1.5.schema.json',
        'bomFormat': 'CycloneDX',
        'specVersion': '1.5',
        'version': 1,
        'metadata': {
            'timestamp': timestamp,
            'tools': {
                'components': [
                    {
                        'type': 'application',
                        'name': 'generate_sbom.py',
                        'version': '1.0.0',
                        'description': 'Built-in SBOM generator for o3de-release-notes-generator',
                    },
                ],
            },
            'component': {
                'type': 'application',
                'bom-ref': PROJECT_NAME,
                'name': PROJECT_NAME,
                'version': PROJECT_VERSION,
                'description': PROJECT_DESCRIPTION,
                'licenses': [
                    {'expression': PROJECT_LICENSE_ID},
                ],
                'externalReferences': [
                    {
                        'type': 'vcs',
                        'url': PROJECT_REPO,
                    },
                ],
                'properties': [
                    {'name': 'cdx:python:minimumVersion', 'value': MIN_PYTHON_VERSION},
                    {'name': 'cdx:externalDependencies', 'value': 'none'},
                ],
            },
            'lifecycles': [
                {'phase': 'build'},
            ],
        },
        'components': components,
        'dependencies': [
            {
                'ref': PROJECT_NAME,
                'dependsOn': [c['bom-ref'] for c in components],
            },
        ],
    }

    # Serial number is derived from the SBOM's own content so that identical
    # inputs always produce an identical document.
    sbom['serialNumber'] = f'urn:uuid:{_generate_deterministic_uuid(content_digest(sbom))}'
    return sbom


def content_digest(sbom: dict[str, Any]) -> str:
    canonical = json.dumps(_substantive(sbom), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _generate_deterministic_uuid(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return (
        f'{h[:8]}-{h[8:12]}-4{h[13:16]}-'
        f'{"89ab"[int(h[16], 16) % 4]}{h[17:20]}-{h[20:32]}'
    )


# mkstemp() creates 0600 and os.replace() preserves that mode, which is why the
# committed sbom.cdx.json was owner-only on disk. Mirror the destination's mode
# instead, falling back to a sane default for a new file.
DEFAULT_OUTPUT_MODE = 0o644


def write_sbom_atomic(sbom: dict[str, Any], output_path: pathlib.Path) -> None:
    output_path = output_path.resolve()
    try:
        target_mode: int | None = stat.S_IMODE(output_path.stat().st_mode)
    except OSError:
        target_mode = None

    fd, tmp_path = tempfile.mkstemp(
        dir=str(output_path.parent),
        prefix='.sbom_',
        suffix='.json.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(sbom, f, indent=2, ensure_ascii=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, target_mode if target_mode is not None else DEFAULT_OUTPUT_MODE)
        os.replace(tmp_path, str(output_path))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _load_existing(path: pathlib.Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding='utf-8') as f:
            loaded: Any = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return loaded if isinstance(loaded, dict) and 'metadata' in loaded else None


def main() -> int:
    project_dir = pathlib.Path(__file__).parent.resolve()
    output_path = project_dir / 'sbom.cdx.json'

    check_only = '--check' in sys.argv[1:]

    sbom = generate_sbom(project_dir)
    current = _load_existing(output_path)
    up_to_date = current is not None and _substantive(current) == _substantive(sbom)

    if check_only:
        # Only possible because the substantive document is deterministic: a
        # mismatch now means the SBOM is genuinely stale, not merely
        # regenerated at a different time or on a different interpreter.
        if not up_to_date:
            print(f'SBOM is out of date: {output_path}', file=sys.stderr)
            print('Run `make sbom` (or `python generate_sbom.py`) and commit the result.',
                  file=sys.stderr)
            return 1
        print(f'SBOM is up to date: {output_path}')
        return 0

    if up_to_date:
        # Rewriting would only churn the timestamp and produce an empty-value
        # commit in CI on every push.
        print(f'SBOM already current, not rewritten: {output_path}')
        return 0

    write_sbom_atomic(sbom, output_path)

    stdlib_count = sum(1 for c in sbom['components'] if c['type'] == 'library')
    component_count = len(sbom['components'])
    print(f'SBOM generated: {output_path}')
    print('  Format: CycloneDX 1.5 (JSON)')
    print(f'  Components: {component_count} ({stdlib_count} stdlib, '
          f'{component_count - stdlib_count} source files)')
    print('  External dependencies: 0')

    return 0


if __name__ == '__main__':
    sys.exit(main())
