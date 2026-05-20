#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright 2026 Nick Schuetz

import argparse
import json
import logging
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

LOG_FORMAT = '[%(levelname)s] %(name)s: %(message)s'
logger = logging.getLogger('o3de.release_notes')

__version__ = '0.5.0-beta'

SCHEMA_VERSION = 3

GIT_REF_PATTERN = re.compile(r'^[a-zA-Z0-9._/\-]+$')
REPO_SLUG_PATTERN = re.compile(r'^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$')
REPO_PATH_MAPPING_PATTERN = re.compile(r'^([a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+)=(.+)$')
PR_NUMBER_PATTERN = re.compile(r'\(#(\d+)\)')

DEFAULT_REPOS = ['o3de/o3de']

SIG_CANONICAL_ORDER = [
    'sig/build',
    'sig/content',
    'sig/core',
    'sig/docs-community',
    'sig/graphics-audio',
    'sig/network',
    'sig/platform',
    'sig/release',
    'sig/security',
    'sig/simulation',
    'sig/testing',
    'sig/ui-ux',
]

SIG_DISPLAY_NAMES = {
    'sig/build': 'SIG-Build',
    'sig/content': 'SIG-Content',
    'sig/core': 'SIG-Core',
    'sig/docs-community': 'SIG-Docs-Community',
    'sig/graphics-audio': 'SIG-Graphics-Audio',
    'sig/network': 'SIG-Network',
    'sig/platform': 'SIG-Platform',
    'sig/release': 'SIG-Release',
    'sig/security': 'SIG-Security',
    'sig/simulation': 'SIG-Simulation',
    'sig/testing': 'SIG-Testing',
    'sig/ui-ux': 'SIG-UI-UX',
}

SIG_TITLE_KEYWORDS = {
    'sig/build': [
        'cmake', 'compiler', ' ci ', ' ci/', 'ci:', 'automated review', ' ar ',
        'workflow', 'installer', 'ninja', 'build error', 'build fix', 'compile',
        'linker', 'linking', 'monolithic', 'ccache', 'sccache', 'gradle',
        'clang', 'msvc', 'gcc', 'xcode', 'msbuild', 'vcpkg', 'conan',
        'github actions', 'gha ', 'pipeline', '3p ', 'third-party',
        'third party', '3rdparty', 'fetchpackage', 'fetchcontent',
    ],
    'sig/content': [
        'editor', 'asset processor', 'asset browser', 'assetprocessor',
        'prefab', 'scriptcanvas', 'script canvas', 'lua editor', 'lua script',
        'outliner', 'inspector', 'lyshine', 'ui canvas', 'viewport',
        'entity inspector', 'component inspector', 'project manager',
        'material editor', 'scene settings', 'fbx', 'gltf', 'glb',
        'asset bundl', 'asset editor', 'asset import',
        'emotionx', 'emotionfx', 'emfx', 'motion', 'animation graph',
    ],
    'sig/core': [
        'azcore', 'azframework', 'aztoolsframework', 'azstd', 'az::',
        'settings registry', 'settingsregistry', 'allocator', 'rtti',
        'behaviorcontext', 'behavior context', 'serializ', 'reflect',
        'component descriptor', 'az_component', 'az_class', 'az_type',
        'json', 'xml', 'streamer', 'io scheduler', 'module',
        'gem.json', 'engine.json', 'o3de cli', 'register',
        'std::move', 'std::array', 'std::span',
    ],
    'sig/graphics-audio': [
        'atom', ' rhi', 'vulkan', 'dx12', 'directx', 'metal',
        'shader', 'material', 'render', 'pass ', 'pass:', 'passes',
        'light', 'lighting', 'shadow', 'texture', 'mesh',
        'ray trac', 'raytrac', 'tlas', 'blas', 'acceleration structure',
        'bloom', 'ssao', 'ssr', 'hdr', 'tonemapp', 'exposure',
        'srg', 'drawsrg', 'materialsrg', 'azsl',
        'diffuse probe', 'global illumination', 'skybox', 'sky atmosphere',
        'skyatmosphere', 'fog', 'particle', 'openparticle',
        'terrain', 'stars', 'miniaudio', 'audio',
        'imgui', 'meshlet', 'lod', 'occlusion', 'culling',
        'unlit', 'emissive', 'irradiance', 'parallax',
    ],
    'sig/network': [
        'network', 'multiplayer', 'netbind', 'replica', 'replication',
    ],
    'sig/platform': [
        'android', ' ios', 'macos', 'mac ', 'linux', 'wayland', 'xcb',
        'emscripten', 'wasm', 'webassembly', 'windows platform',
        'platform tab', 'arm64', 'aarch64', 'x86_64',
        'objective-c', 'apple',
    ],
    'sig/simulation': [
        'physx', 'physics', 'rigid body', 'collider', 'articulation',
        'recast', 'navigation', 'navmesh', 'detour',
        'hinge', 'joint', 'ragdoll', 'character controller',
        'ros2', 'ros 2', 'robot', 'gripper', 'simulation interface',
    ],
    'sig/security': [
        'security', 'bounds check', 'cve', 'owasp', 'vulnerability',
        'buffer overflow', 'out of bounds', 'oom dos', 'sanitiz',
    ],
    'sig/testing': [
        'googletest', 'gtest', 'gmock', 'benchmark', 'unit test',
        'test fix', 'test compilation', 'ctest', 'asan', 'tsan',
    ],
}

SIG_FILE_PATH_PATTERNS = {
    'sig/testing': [
        'cmake/LYTestWrappers.cmake',
        'Code/Framework/AzTest',
        'Code/Tools/AzTestRunner/',
        'Tools/LyTestTools/',
        'Tools/RemoteConsole/',
        'scripts/ctest/',
    ],
    'sig/core': [
        'Code/CrashHandler/',
        'Code/Framework/AzCore/',
        'Code/Framework/AzFramework/',
        'Code/Framework/AzGameFramework/',
        'Code/LauncherUnified/',
        'engine.json',
        'Gems/Archive/',
        'Gems/Compression/',
        'Gems/CrashReporting/',
        'Gems/ImGui/',
        'Gems/LmbrCentral/',
        'Gems/Profiler/',
        'Registry/',
        'scripts/lldb/',
        'scripts/o3de/',
        'Code/Legacy/',
        'Code/Tools/SerializeContextTools/',
        'Templates/',
        'Tools/EventLogTool/',
    ],
    'sig/content': [
        'Code/Framework/AzToolsFramework/',
        'Code/Tools/',
        'Code/Framework/AzQtComponents/',
        'Code/Editor/',
        'Gems/EditorPythonBindings/',
        'Gems/GraphCanvas/',
        'Gems/GraphModel/',
        'Gems/LandscapeCanvas/',
        'Gems/QtForPython/',
        'Gems/LyShine/',
        'Gems/ScriptCanvas/',
        'Gems/ScriptEvents/',
        'Gems/SceneProcessing/',
        'Gems/WhiteBox/',
        'Gems/Prefab/',
        'Code/Framework/AzManipulatorTestFramework/',
        'Tools/',
    ],
    'sig/simulation': [
        'Code/Framework/AzCore/AzCore/Math/',
        'Code/Framework/AzFramework/AzFramework/Physics/',
        'Gems/MotionMatching/',
        'Gems/NvCloth/',
        'Gems/PhysX/',
        'Gems/PhysXDebug/',
        'Gems/EMotionFX/',
        'Gems/RecastNavigation/',
        'Gems/ROS2/',
        'Gems/ROS2Sensors/',
        'Gems/ROS2Controllers/',
        'Gems/SimulationInterfaces/',
    ],
    'sig/build': [
        'cmake/Platform/',
        'cmake/Packaging/',
        'scripts/build/',
        'scripts/commit_validation/',
        'scripts/license_scanner/',
        'scripts/signer/',
        '.github/workflows/',
        'python/',
    ],
    'sig/network': [
        'Code/Framework/AzFramework/AzFramework/Network/',
        'Code/Framework/AzNetworking/',
        'Code/Tools/AWSNativeSDKInit/',
        'Gems/AWSClientAuth/',
        'Gems/AWSCore/',
        'Gems/AWSGameLift/',
        'Gems/AWSMetrics/',
        'Gems/HttpRequestor/',
        'Gems/Metastream/',
        'Gems/Multiplayer/',
        'Gems/MultiplayerCompression/',
        'Gems/Twitch/',
    ],
    'sig/graphics-audio': [
        'Gems/Atom/',
        'Gems/AtomLyIntegration/',
        'Gems/AtomTressFX/',
        'Gems/Terrain/',
        'Gems/Audio/',
        'Gems/Microphone/',
        'Gems/DiffuseProbeGrid/',
        'Gems/Stars/',
        'Gems/SkyAtmosphere/',
        'Gems/OpenParticleSystem/',
        'Gems/MiniAudio/',
    ],
    'sig/platform': [
        'restricted/',
    ],
}

CHERRY_PICK_PATTERNS = [
    re.compile(r'cherry[\s-]*pick', re.IGNORECASE),
    re.compile(r'merge\s+stabilization', re.IGNORECASE),
    re.compile(r'merge\s+from\s+stabilization', re.IGNORECASE),
    re.compile(r'merge\s+changes\s+from\s+stabilization', re.IGNORECASE),
    re.compile(r'\[stabilization\]', re.IGNORECASE),
    re.compile(r'sync.*to.*development', re.IGNORECASE),
]

# Containers are commit/PR titles that bundle multiple cherry-picks from another
# branch, distinct from plain "cherry-pick" because we expect their bodies to
# enumerate the bundled PR numbers via the `(#NNNN)` convention.
POINTRELEASE_CONTAINER_PATTERNS = [
    re.compile(r'cherry[\s-]*pick.+(?:from|point[\s-]*release|dev|development)', re.IGNORECASE),
    re.compile(r'merg(?:e|ing).*point[\s-]*release', re.IGNORECASE),
    re.compile(r'merg(?:e|ing).*upstream.*point[\s-]*release', re.IGNORECASE),
]

# Matches X.Y.Z-style point-release tags (e.g., 2510.2, 2605.1). Only used to
# detect when --from-ref points at a point release so we can scan its
# predecessors for cherry-pick containers. Year + month encoded in X, patch in Z.
POINT_RELEASE_TAG_PATTERN = re.compile(r'^(\d{2,4})\.(\d+)$')

# Release-engineering PRs that aren't product changes (version bumps, point-
# release branch admin, GPG key rotations, SBOM/dependency-only auto-updates).
# Matched against the PR title. We require AT LEAST ONE of these patterns AND
# typically a small/narrow file set; see is_release_machinery for the conjunction.
RELEASE_MACHINERY_TITLE_PATTERNS = [
    re.compile(r'^update\s+(?:version|copyright)', re.IGNORECASE),
    re.compile(r'^update\s+(?:linux\s+)?gpg\s+key', re.IGNORECASE),
    re.compile(r'^update\s+sbom\b', re.IGNORECASE),
    re.compile(r'^point[\s-]*release\b', re.IGNORECASE),
    re.compile(r'\bmerge\b.*\bpoint[\s-]*release\b', re.IGNORECASE),
    re.compile(r'\bmerging[_\s]*point[\s-]*release\b', re.IGNORECASE),
    re.compile(r'\bcherry[\s-]*pick.*\bpoint[\s-]*release\b', re.IGNORECASE),
    re.compile(r'\bmerging[_\s]+pointrelease', re.IGNORECASE),
    re.compile(r'\bcherrypick\d*\s+from\s+dev\s+to\s+pointrelease', re.IGNORECASE),
    re.compile(r'\badd\s+point[\s-]*release\s+branch\s+to\s+ar\b', re.IGNORECASE),
]

# Files whose presence-only (i.e. when ALL changed files match one of these
# patterns) indicates a non-product PR. Deliberately narrow: only files whose
# diff is unambiguous machinery (version bumps, SBOMs). We do NOT include
# `.github/workflows/` here. Workflow-only PRs are often substantive CI
# improvements (e.g. "Add check for adequate free space in linux AR workspace")
# that curators want to keep, and we'd rather under-flag than incorrectly
# exclude real content. Title patterns above carry the bulk of the load.
RELEASE_MACHINERY_FILE_PATTERNS = [
    re.compile(r'(^|/)engine\.json$'),
    re.compile(r'^sbom\.cdx\.json$'),
    re.compile(r'/version\.txt$'),
]


def validate_git_ref(ref: str) -> str:
    if not ref or len(ref) > 256:
        raise ValueError(f'Invalid git reference: length must be 1-256, got {len(ref) if ref else 0}')
    if not GIT_REF_PATTERN.match(ref):
        raise ValueError(f'Invalid git reference: {ref!r} contains disallowed characters')
    if ref.startswith('-'):
        raise ValueError(f'Invalid git reference: {ref!r} must not start with a hyphen')
    return ref


def validate_repo_slug(slug: str) -> str:
    if not slug or len(slug) > 128:
        raise ValueError(f'Invalid repo slug: length must be 1-128, got {len(slug) if slug else 0}')
    if not REPO_SLUG_PATTERN.match(slug):
        raise ValueError(f'Invalid repo slug: {slug!r} must be in owner/repo format')
    return slug


def validate_output_path(path: pathlib.Path, base_dir: pathlib.Path | None = None) -> pathlib.Path:
    resolved = path.resolve()
    if base_dir is not None:
        base_resolved = base_dir.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise ValueError(f'Path traversal detected: {resolved} is outside {base_resolved}')
    if not resolved.parent.exists():
        raise ValueError(f'Parent directory does not exist: {resolved.parent}')
    return resolved


def parse_repo_path_mappings(
    repo_paths: list[str] | None,
    default_path: str,
    repos: list[str],
) -> dict[str, pathlib.Path]:
    default = pathlib.Path(default_path).resolve()
    mappings: dict[str, pathlib.Path] = {}

    if repo_paths:
        for entry in repo_paths:
            match = REPO_PATH_MAPPING_PATTERN.match(entry)
            if match:
                slug, path_str = match.group(1), match.group(2)
                validate_repo_slug(slug)
                mappings[slug] = pathlib.Path(path_str).resolve()
            else:
                raise ValueError(
                    f'Invalid --repo-path mapping: {entry!r}. '
                    f'Use owner/repo=/path/to/clone format.'
                )

    for repo in repos:
        if repo not in mappings:
            mappings[repo] = default

    return mappings


MAX_STDERR_LOG_LEN = 200

# Defense-in-depth: scrub GitHub token shapes from stderr before logging.
# gh CLI is unlikely to print tokens, but if it ever does, we don't want them
# in CI logs.
GH_TOKEN_PATTERN = re.compile(r'\bgh[pousr]_[A-Za-z0-9]{20,}\b')


def _safe_stderr(text: str) -> str:
    redacted = GH_TOKEN_PATTERN.sub('<redacted-token>', text)
    return redacted.strip()[:MAX_STDERR_LOG_LEN]


def parse_point_release_tag(ref: str) -> tuple[int, int] | None:
    """Return (major_token, patch) if ref looks like a point-release tag, else None.

    The major_token is the integer before the dot (e.g. 2510 in '2510.2'); the
    O3DE convention encodes year and month there, but for our purposes it's an
    opaque key used to group sibling tags.
    """
    if not ref:
        return None
    m = POINT_RELEASE_TAG_PATTERN.match(ref.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def find_sibling_point_release_tags(repo_path: pathlib.Path, ref: str) -> list[str]:
    """Given a point-release tag, return all sibling tags sharing the same major
    token (e.g. given '2510.2' returns ['2510.0', '2510.1', '2510.2'])."""
    parsed = parse_point_release_tag(ref)
    if parsed is None:
        return []
    major_token = parsed[0]
    try:
        result = subprocess.run(
            ['git', 'tag', '-l', f'{major_token}.*'],
            cwd=str(repo_path.resolve()),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning('git tag failed for %s: %s', repo_path, e)
        return []
    if result.returncode != 0:
        return []
    tags = []
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if parse_point_release_tag(candidate) is not None:
            tags.append(candidate)
    tags.sort(key=lambda t: parse_point_release_tag(t) or (0, 0))
    return tags


def extract_merge_base(
    repo_path: pathlib.Path,
    from_ref: str,
    to_ref: str,
) -> tuple[str, str] | None:
    """Return (sha, committer_date_iso) of the merge-base, or None on failure.

    Used to anchor the "effective window" of the diff in release_data.json
    metadata. Silently degrades to None if git fails; callers should treat
    this metadata as best-effort.
    """
    from_ref = validate_git_ref(from_ref)
    to_ref = validate_git_ref(to_ref)
    try:
        mb = subprocess.run(
            ['git', 'merge-base', from_ref, to_ref],
            cwd=str(repo_path.resolve()),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning('git merge-base failed for %s: %s', repo_path, e)
        return None
    if mb.returncode != 0:
        logger.warning('git merge-base %s..%s failed in %s: %s',
                       from_ref, to_ref, repo_path, _safe_stderr(mb.stderr))
        return None
    sha = mb.stdout.strip()
    if not sha:
        return None
    try:
        show = subprocess.run(
            ['git', 'show', '-s', '--format=%cI', sha],
            cwd=str(repo_path.resolve()),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        return (sha, '')
    date = show.stdout.strip() if show.returncode == 0 else ''
    return (sha, date)


# Maximum bytes we'll read from a single commit body when scanning for bundled
# PR references in a cherry-pick container. Bounds memory if a malformed commit
# has an enormous body.
MAX_CONTAINER_BODY_BYTES = 32768


def extract_pointrelease_containers(
    repo_path: pathlib.Path,
    predecessor_tag: str,
    from_ref: str,
) -> list[dict]:
    """Walk commits between predecessor_tag and from_ref looking for cherry-pick
    containers (PRs whose title matches POINTRELEASE_CONTAINER_PATTERNS) and
    extract the bundled PR numbers from each commit's body.

    Returns a list of {container_pr, title, bundled_prs: [int, ...]} dicts.
    """
    predecessor_tag = validate_git_ref(predecessor_tag)
    from_ref = validate_git_ref(from_ref)
    sep = '@@CONTAINER_BOUNDARY@@'
    try:
        result = subprocess.run(
            ['git', 'log', f'--format=%H%n%s%n%b%n{sep}',
             f'{predecessor_tag}..{from_ref}'],
            cwd=str(repo_path.resolve()),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning('git log failed when scanning containers in %s: %s', repo_path, e)
        return []
    if result.returncode != 0:
        logger.warning(
            'Container scan: git log %s..%s in %s returned %d',
            predecessor_tag, from_ref, repo_path, result.returncode,
        )
        return []

    containers: list[dict] = []
    chunks = result.stdout.split(sep + '\n')
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.split('\n', 2)
        if len(lines) < 2:
            continue
        sha = lines[0].strip()
        title = lines[1].strip()
        body = lines[2] if len(lines) > 2 else ''
        if len(body) > MAX_CONTAINER_BODY_BYTES:
            body = body[:MAX_CONTAINER_BODY_BYTES]

        if not any(p.search(title) for p in POINTRELEASE_CONTAINER_PATTERNS):
            continue

        # PR number in the title itself is the container PR (e.g. "(#19506)").
        # Bundled PRs come from the body.
        title_match = PR_NUMBER_PATTERN.search(title)
        container_pr = int(title_match.group(1)) if title_match else None
        bundled = set()
        for m in PR_NUMBER_PATTERN.finditer(body):
            n = int(m.group(1))
            if n != container_pr:
                bundled.add(n)
        containers.append({
            'container_pr': container_pr,
            'container_sha': sha,
            'title': title,
            'bundled_prs': sorted(bundled),
        })
    return containers


def write_pointrelease_audit(
    audit_data: dict,
    output_path: pathlib.Path,
) -> None:
    """Write a human-readable audit sidecar listing each container and showing
    whether its bundled PRs are accounted for in the rendered report set.

    audit_data must contain:
      - from_ref, to_ref, predecessor_tag
      - per_repo: {repo_slug: {containers: [...], present_pr_numbers: set[int]}}
    """
    lines: list[str] = []
    lines.append(f"# Point-release audit for {audit_data.get('to_ref', '')}\n")
    lines.append(
        f"Predecessor major tag: `{audit_data.get('predecessor_tag', '')}`  \n"
        f"From-ref (point release): `{audit_data.get('from_ref', '')}`  \n"
        f"To-ref (next major): `{audit_data.get('to_ref', '')}`\n"
    )
    lines.append(
        "Each entry below is a cherry-pick container PR found on the previous\n"
        "stabilization branch between the predecessor major tag and the from-ref.\n"
        "The bundled PRs are extracted from the container's commit body. A ✓\n"
        "means the bundled PR appears in the rendered report (via its\n"
        "development-side merge); a ✗ means it is missing and worth\n"
        "investigating.\n"
    )

    grand_total_containers = 0
    grand_total_bundled = 0
    grand_total_present = 0

    for repo_slug, repo_audit in audit_data.get('per_repo', {}).items():
        containers = repo_audit.get('containers', [])
        present = repo_audit.get('present_pr_numbers', set())
        lines.append(f"\n## {repo_slug}\n")
        if not containers:
            lines.append("_No cherry-pick containers found in this repo._\n")
            continue
        for entry in containers:
            cpr = entry.get('container_pr')
            cpr_label = f"#{cpr}" if cpr else f"sha:{entry.get('container_sha','')[:8]}"
            bundled = entry.get('bundled_prs', [])
            grand_total_containers += 1
            grand_total_bundled += len(bundled)
            lines.append(f"- **{cpr_label}**: {entry.get('title', '')}")
            if not bundled:
                lines.append("  - _(no bundled PRs parsed from body)_")
                continue
            for b in bundled:
                if b in present:
                    grand_total_present += 1
                    lines.append(f"  - ✓ #{b}: present in report via dev-side merge")
                else:
                    lines.append(f"  - ✗ #{b}: NOT in report (investigate)")

    lines.append('')
    lines.append(
        f"---\n\n"
        f"**Summary:** {grand_total_containers} container(s) checked, "
        f"{grand_total_bundled} bundled PR reference(s) parsed, "
        f"{grand_total_present} accounted for in the rendered report.\n"
    )
    content = '\n'.join(lines)
    write_markdown_atomic(content, output_path)


def is_release_machinery(pr_data: dict) -> bool:
    """Heuristically detect release-engineering PRs that aren't product changes.

    True when EITHER:
      - the title matches one of RELEASE_MACHINERY_TITLE_PATTERNS, OR
      - every changed file matches one of RELEASE_MACHINERY_FILE_PATTERNS
        (and there is at least one file).

    The file-only path catches version-bump / SBOM / workflow-only PRs whose
    titles don't fit a fixed pattern.
    """
    title = pr_data.get('title', '') or ''
    if any(p.search(title) for p in RELEASE_MACHINERY_TITLE_PATTERNS):
        return True

    files = pr_data.get('files', []) or []
    if not files:
        return False
    for fpath in files:
        if not any(p.search(fpath) for p in RELEASE_MACHINERY_FILE_PATTERNS):
            return False
    return True


def extract_pr_numbers_from_git_log(
    repo_path: pathlib.Path,
    from_ref: str,
    to_ref: str,
) -> list[int]:
    from_ref = validate_git_ref(from_ref)
    to_ref = validate_git_ref(to_ref)

    result = subprocess.run(
        ['git', 'log', '--format=%s', f'{from_ref}..{to_ref}', '--no-merges'],
        cwd=str(repo_path.resolve()),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=60,
    )
    if result.returncode != 0:
        logger.error('git log failed: %s', _safe_stderr(result.stderr))
        raise RuntimeError(f'git log failed with exit code {result.returncode}')

    pr_numbers = set()
    for line in result.stdout.splitlines():
        for match in PR_NUMBER_PATTERN.finditer(line):
            pr_numbers.add(int(match.group(1)))

    return sorted(pr_numbers)


def _build_graphql_query(pr_numbers: list[int]) -> str:
    # Owner/name are GraphQL variables ($owner, $name); never interpolated as
    # strings. PR numbers are integer-validated before they reach this function
    # and become GraphQL aliases (pr_<n>), which require literal numbers.
    fragments = []
    for num in pr_numbers:
        fragments.append(
            f'  pr_{num}: pullRequest(number: {int(num)}) {{\n'
            f'    number\n'
            f'    title\n'
            f'    body\n'
            f'    mergedAt\n'
            f'    url\n'
            f'    author {{ login }}\n'
            f'    labels(first: 20) {{ nodes {{ name }} }}\n'
            f'    files(first: 100) {{ nodes {{ path }} }}\n'
            f'  }}'
        )

    return (
        'query($owner: String!, $name: String!) {\n'
        '  repository(owner: $owner, name: $name) {\n'
        + '\n'.join(fragments) +
        '\n  }\n'
        '}'
    )


def _run_gh_command(args: list[str], timeout: int = 30) -> dict:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = _safe_stderr(result.stderr)
        if 'rate limit' in stderr.lower() or '403' in stderr:
            logger.error('GitHub API rate limit exceeded. Try again later.')
        else:
            logger.error('gh command failed: %s', stderr)
        raise RuntimeError(f'gh command failed with exit code {result.returncode}')

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f'gh returned non-JSON output: {e}') from e


def _check_gh_available() -> bool:
    if not shutil.which('gh'):
        logger.error('gh CLI is required but not found. Install from https://cli.github.com/')
        return False

    result = subprocess.run(
        ['gh', 'auth', 'status'],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=10,
    )
    if result.returncode != 0:
        logger.error('gh CLI is not authenticated. Run: gh auth login')
        return False

    return True


MAX_PR_NUMBER = 999999


def fetch_pr_metadata_batch(
    repo_slug: str,
    pr_numbers: list[int],
    batch_size: int = 30,
) -> list[dict]:
    repo_slug = validate_repo_slug(repo_slug)
    if batch_size <= 0 or batch_size > 100:
        raise ValueError(f'batch_size must be 1-100, got {batch_size}')
    if not pr_numbers:
        return []
    for num in pr_numbers:
        if not isinstance(num, int) or num <= 0 or num > MAX_PR_NUMBER:
            raise ValueError(f'Invalid PR number: {num}')
    owner, repo = repo_slug.split('/')

    all_prs = []
    total = len(pr_numbers)

    for i in range(0, total, batch_size):
        batch = pr_numbers[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size
        logger.info('Fetching PRs batch %d/%d (%d PRs)', batch_num, total_batches, len(batch))

        query = _build_graphql_query(batch)
        try:
            data = _run_gh_command(
                ['gh', 'api', 'graphql',
                 '-f', f'query={query}',
                 '-f', f'owner={owner}',
                 '-f', f'name={repo}'],
                timeout=60,
            )
        except RuntimeError:
            logger.warning('Batch %d failed, trying individual PRs', batch_num)
            for num in batch:
                try:
                    single_query = _build_graphql_query([num])
                    data = _run_gh_command(
                        ['gh', 'api', 'graphql',
                         '-f', f'query={single_query}',
                         '-f', f'owner={owner}',
                         '-f', f'name={repo}'],
                        timeout=30,
                    )
                    pr_data = data.get('data', {}).get('repository', {}).get(f'pr_{num}')
                    if pr_data:
                        all_prs.append(_normalize_pr_data(pr_data, repo_slug))
                except RuntimeError:
                    logger.warning('Failed to fetch PR #%d, skipping', num)
            continue

        if 'errors' in data:
            for err in data['errors']:
                logger.warning('GraphQL error: %s', err.get('message', 'unknown'))

        repo_data = data.get('data', {}).get('repository', {})
        for num in batch:
            pr_data = repo_data.get(f'pr_{num}')
            if pr_data:
                all_prs.append(_normalize_pr_data(pr_data, repo_slug))
            else:
                logger.warning('PR #%d not found in %s', num, repo_slug)

    return all_prs


def _normalize_pr_data(raw: dict, repo_slug: str) -> dict:
    file_nodes = raw.get('files', {}).get('nodes', [])
    if len(file_nodes) >= 100:
        logger.warning('PR #%d in %s has 100+ changed files; file list may be truncated',
                        raw.get('number', 0), repo_slug)
    return {
        'number': raw.get('number', 0),
        'repo': repo_slug,
        'title': raw.get('title', ''),
        'body': raw.get('body', ''),
        'url': raw.get('url', ''),
        'author': raw.get('author', {}).get('login', 'unknown') if raw.get('author') else 'unknown',
        'merged_at': raw.get('mergedAt', ''),
        'labels': [n['name'] for n in raw.get('labels', {}).get('nodes', [])],
        'files': [n['path'] for n in file_nodes],
    }


def _categorize_by_labels(labels: list[str]) -> str | None:
    sig_labels = [l for l in labels if l.startswith('sig/') and l in SIG_CANONICAL_ORDER]
    if not sig_labels:
        return None
    if 'sig/release' in sig_labels and len(sig_labels) > 1:
        sig_labels = [l for l in sig_labels if l != 'sig/release']
    # Deterministic: when a PR carries multiple SIG labels, pick the one earliest
    # in SIG_CANONICAL_ORDER. Without this sort, GitHub's label-return order
    # decides, which is not stable across runs.
    sig_labels.sort(key=SIG_CANONICAL_ORDER.index)
    return sig_labels[0]


def _categorize_by_title(title: str) -> str | None:
    title_lower = f' {title.lower()} '
    best_sig = None
    best_count = 0
    best_priority = len(SIG_CANONICAL_ORDER)
    for sig, keywords in SIG_TITLE_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw.lower() in title_lower)
        if count == 0:
            continue
        priority = SIG_CANONICAL_ORDER.index(sig) if sig in SIG_CANONICAL_ORDER else len(SIG_CANONICAL_ORDER)
        # Prefer higher count; on ties, prefer the SIG earlier in the canonical
        # order. Without an explicit tiebreak the choice depends on dict
        # iteration order, which is not a reliable contract.
        if count > best_count or (count == best_count and priority < best_priority):
            best_count = count
            best_sig = sig
            best_priority = priority
    return best_sig


def _categorize_by_files(file_paths: list[str]) -> str | None:
    sig_counts: dict[str, int] = {}
    for fpath in file_paths:
        best_sig = None
        best_len = 0
        for sig, patterns in SIG_FILE_PATH_PATTERNS.items():
            for pattern in patterns:
                if fpath.startswith(pattern) and len(pattern) > best_len:
                    best_sig = sig
                    best_len = len(pattern)
        if best_sig:
            sig_counts[best_sig] = sig_counts.get(best_sig, 0) + 1
    if not sig_counts:
        return None
    max_count = max(sig_counts.values())
    tied = [sig for sig, cnt in sig_counts.items() if cnt == max_count]
    if len(tied) == 1:
        return tied[0]
    for sig in SIG_CANONICAL_ORDER:
        if sig in tied:
            return sig
    return tied[0]


def categorize_pr(pr_data: dict) -> tuple[str, str]:
    sig = _categorize_by_labels(pr_data.get('labels', []))
    if sig:
        return sig, 'label'

    sig = _categorize_by_title(pr_data.get('title', ''))
    if sig:
        return sig, 'heuristic_title'

    sig = _categorize_by_files(pr_data.get('files', []))
    if sig:
        return sig, 'heuristic_files'

    return 'uncategorized', 'uncategorized'


def detect_pr_flags(pr_data: dict) -> list[str]:
    flags = []
    title = pr_data.get('title', '')
    for pattern in CHERRY_PICK_PATTERNS:
        if pattern.search(title):
            flags.append('cherry-pick')
            break

    labels = pr_data.get('labels', [])
    if any('sync' in l for l in labels):
        flags.append('stabilization-sync')

    return flags


def _sanitize_pr_title_for_markdown(title: str) -> str:
    title = title.strip()
    title = re.sub(r'\(#\d+\)\s*$', '', title).strip()
    title = title.lstrip('#').strip()
    sanitized = []
    for ch in title:
        if ch in '[]|`':
            sanitized.append(f'\\{ch}')
        else:
            sanitized.append(ch)
    result = ''.join(sanitized)
    if result and not result.endswith('.'):
        result += '.'
    return result


PR_BODY_NOISE_PATTERNS = [
    re.compile(r'^#{1,4}\s*(what|how|why|description|summary|context|test|checklist|todo|link|related|change)', re.IGNORECASE),
    re.compile(r'^-\s*\[[ x]\]', re.IGNORECASE),
    re.compile(r'^---+$'),
    re.compile(r'^<!--'),
    re.compile(r'^!\['),
    re.compile(r'^<img\s', re.IGNORECASE),
    re.compile(r'^https?://'),
    re.compile(r'^\*\*Full Changelog\*\*'),
    re.compile(r'^Signed-off-by:', re.IGNORECASE),
    re.compile(r'^Related\s*(to\s*)?:?\s*$', re.IGNORECASE),
    re.compile(r'^\*\s*$'),
    re.compile(r'^-\s*https?://'),
    re.compile(r'^Automated PR', re.IGNORECASE),
    re.compile(r'^\[?screenshot', re.IGNORECASE),
    re.compile(r'^!\[image\]', re.IGNORECASE),
]

BULLET_PATTERN = re.compile(r'^[\-\*]\s+')


MAX_PR_BODY_BYTES = 65536


def _build_pr_description(title: str, body: str) -> str:
    sanitized_title = _sanitize_pr_title_for_markdown(title)
    if not body or not body.strip():
        return sanitized_title

    # Defense-in-depth: cap body before extraction so a pathological PR body
    # cannot blow up regex / string ops. The first paragraph is itself capped
    # at 300 chars downstream, but capping early keeps memory/CPU bounded.
    if len(body) > MAX_PR_BODY_BYTES:
        body = body[:MAX_PR_BODY_BYTES]

    first_paragraph = _extract_first_paragraph(body)
    if not first_paragraph:
        return sanitized_title

    if len(first_paragraph) <= 20 or len(first_paragraph) > 300:
        return sanitized_title

    title_words = set(re.findall(r'[a-zA-Z]{3,}', title.lower()))
    para_words = set(re.findall(r'[a-zA-Z]{3,}', first_paragraph.lower()))
    overlap = title_words & para_words

    if len(title_words) > 0 and len(overlap) / len(title_words) < 0.2:
        combined = f'{sanitized_title.rstrip(".")}: {first_paragraph}'
        if len(combined) <= 300:
            return _sanitize_pr_title_for_markdown(combined)
        return sanitized_title

    return _sanitize_pr_title_for_markdown(first_paragraph)


def _extract_first_paragraph(body: str) -> str:
    lines = body.split('\n')
    paragraph_lines = []
    is_bullet_list = False

    for line in lines:
        stripped = line.strip()
        if any(p.match(stripped) for p in PR_BODY_NOISE_PATTERNS):
            if paragraph_lines:
                break
            continue
        if not stripped:
            if paragraph_lines:
                break
            continue

        if BULLET_PATTERN.match(stripped):
            is_bullet_list = True

        paragraph_lines.append(stripped)

    if not paragraph_lines:
        return ''

    if is_bullet_list:
        return ''

    paragraph = ' '.join(paragraph_lines)
    if len(paragraph) > 300:
        paragraph = paragraph[:297] + '...'
    return paragraph


def _format_pr_reference(repo_slug: str, pr_number: int, url: str = '') -> str:
    repo_name = repo_slug.split('/')[-1]
    label = f'{repo_name}#{pr_number}'
    if url:
        return f'[{label}]({url})'
    return f'[{label}](https://github.com/{repo_slug}/pull/{pr_number})'


def merge_with_existing(
    new_prs: list[dict],
    existing_json_path: pathlib.Path | None,
) -> list[dict]:
    if existing_json_path is None or not existing_json_path.exists():
        return new_prs

    existing_data = load_existing_json(existing_json_path)
    if existing_data is None:
        return new_prs

    existing_by_key = {}
    for pr in existing_data.get('pull_requests', []):
        key = (pr.get('repo', ''), pr.get('number', 0))
        existing_by_key[key] = pr

    merged = []
    for pr in new_prs:
        key = (pr.get('repo', ''), pr.get('number', 0))
        existing = existing_by_key.pop(key, None)
        if existing:
            if existing.get('manual_override_sig'):
                pr['sig_category'] = existing['manual_override_sig']
                pr['categorization_source'] = 'manual_override'
                pr['manual_override_sig'] = existing['manual_override_sig']
            if existing.get('manual_override_description'):
                pr['description'] = existing['manual_override_description']
                pr['manual_override_description'] = existing['manual_override_description']
        merged.append(pr)

    dropped_without_overrides = 0
    for pr in existing_by_key.values():
        if pr.get('manual_override_sig') or pr.get('manual_override_description'):
            merged.append(pr)
        else:
            dropped_without_overrides += 1

    if dropped_without_overrides:
        # PRs that were in the existing JSON but no longer appear in git log
        # are dropped unless they carry a manual_override_*. Edits to
        # `description` or `sig_category` made directly (without setting the
        # corresponding override field) are silently lost. Log a warning so
        # users notice when this happens.
        logger.warning(
            'Dropped %d PR(s) from previous JSON (no longer in git log; no manual_override_* set). '
            'Set manual_override_sig / manual_override_description to preserve direct edits.',
            dropped_without_overrides,
        )

    merged.sort(key=lambda p: (p.get('repo', ''), p.get('number', 0)))
    return merged


def _build_summary_prompt(
    pr_list: list[dict],
    version: str,
    hint: str = '',
    include_release_machinery: bool = False,
) -> str:
    by_sig: dict[str, list[str]] = {}
    for pr in pr_list:
        flags = pr.get('flags', [])
        if 'cherry-pick' in flags or 'stabilization-sync' in flags:
            continue
        if not include_release_machinery and pr.get('release_machinery'):
            continue
        sig = pr.get('sig_category', 'uncategorized')
        if sig == 'uncategorized':
            continue
        display = SIG_DISPLAY_NAMES.get(sig, sig)
        by_sig.setdefault(display, []).append(pr.get('title', ''))

    sig_summary = ''
    for sig in sorted(by_sig):
        titles = by_sig[sig]
        sig_summary += f'\n{sig} ({len(titles)} changes):\n'
        for t in titles[:15]:
            sig_summary += f'  - {t}\n'
        if len(titles) > 15:
            sig_summary += f'  - ... and {len(titles) - 15} more\n'

    total = sum(len(v) for v in by_sig.values())

    hint_section = ''
    if hint:
        hint_section = (
            f'\nAdditional guidance from the release manager:\n'
            f'{hint}\n\n'
            f'Incorporate this guidance into the narrative where appropriate.\n'
        )

    return (
        f'Write a narrative summary for the O3DE (Open 3D Engine) {version} release notes. '
        f'This release contains {total} changes across {len(by_sig)} SIGs '
        f'(Special Interest Groups).\n\n'
        f'The summary should be 2-3 paragraphs that:\n'
        f'1. Open with a high-level statement about the release\n'
        f'2. Highlight the most significant new features and improvements\n'
        f'3. Mention key themes (e.g., platform support, deprecations, new gems)\n'
        f'4. Thank the community contributors\n\n'
        f'Write in the style of previous O3DE release notes: professional, '
        f'concise, and community-oriented. Do not use markdown headers or bullet '
        f'points. Output only the narrative paragraphs, nothing else.\n'
        f'{hint_section}\n'
        f'Here are the changes grouped by SIG:\n{sig_summary}'
    )


ANSI_ESCAPE_PATTERN = re.compile(r'(\x1b\[[\?]?[0-9;]*[a-zA-Z]|\x1b\].*?\x07|\x1b[()][A-Z0-9])')


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub('', text)


SUMMARY_PREAMBLE_PATTERNS = [
    re.compile(r'^(here\'?s?|below is|the following is|there\'?s?).*', re.IGNORECASE),
    re.compile(r'^(sure|certainly|of course)[,!.].*', re.IGNORECASE),
    re.compile(r'^(i\'ve|i have)\s+(reviewed|read|analyzed|looked|written|created|prepared|updated).*', re.IGNORECASE),
]

SUMMARY_POSTAMBLE_PATTERNS = [
    re.compile(r'^(three|two|four|the above|i incorporated|i\'ve incorporated|note:)', re.IGNORECASE),
    re.compile(r'^(this summary|the summary|these paragraphs|i followed|i used|per your)', re.IGNORECASE),
]


def _clean_summary(text: str) -> str:
    lines = text.split('\n')
    cleaned = True
    while cleaned:
        cleaned = False
        while lines and lines[0].strip() in ('---', ''):
            lines.pop(0)
            cleaned = True
        while lines and lines[-1].strip() in ('---', ''):
            lines.pop()
            cleaned = True
        while lines:
            first = lines[0].strip()
            if any(p.match(first) for p in SUMMARY_PREAMBLE_PATTERNS):
                lines.pop(0)
                cleaned = True
                continue
            break
        while lines:
            last = lines[-1].strip()
            if not last:
                lines.pop()
                cleaned = True
                continue
            if any(p.match(last) for p in SUMMARY_POSTAMBLE_PATTERNS):
                lines.pop()
                cleaned = True
                continue
            break
    return '\n'.join(lines).strip()


def _resolve_hint(hint: str) -> str:
    if not hint:
        return ''
    if hint.startswith('@'):
        filepath = pathlib.Path(hint[1:]).resolve()
        if not filepath.is_file():
            logger.error('Summary hint file not found: %s', filepath)
            return ''
        try:
            return filepath.read_text(encoding='utf-8').strip()
        except OSError as e:
            logger.error('Failed to read summary hint file: %s', e)
            return ''
    return hint


DEFAULT_SUMMARY_TIMEOUT = 300
MIN_SUMMARY_TIMEOUT = 10
MAX_SUMMARY_TIMEOUT = 3600


def generate_summary(
    pr_list: list[dict],
    version: str,
    summary_cmd: str,
    hint: str = '',
    timeout: int = DEFAULT_SUMMARY_TIMEOUT,
    include_release_machinery: bool = False,
) -> str | None:
    if timeout < MIN_SUMMARY_TIMEOUT or timeout > MAX_SUMMARY_TIMEOUT:
        logger.error('Invalid summary timeout: %d (must be %d-%d)', timeout, MIN_SUMMARY_TIMEOUT, MAX_SUMMARY_TIMEOUT)
        return None

    resolved_hint = _resolve_hint(hint)
    prompt = _build_summary_prompt(
        pr_list, version, hint=resolved_hint,
        include_release_machinery=include_release_machinery,
    )

    try:
        cmd_parts = shlex.split(summary_cmd)
    except ValueError as e:
        logger.error('Invalid summary command syntax: %s', e)
        return None

    if not cmd_parts:
        logger.error('Empty summary command')
        return None

    executable = cmd_parts[0]

    if not shutil.which(executable):
        logger.error('Summary command not found: %s', executable)
        return None

    logger.info('Generating narrative summary using: %s (timeout=%ds)', executable, timeout)

    try:
        result = subprocess.run(
            cmd_parts,
            input=prompt,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.error('Summary generation failed: %s', _safe_stderr(result.stderr))
            return None

        summary = _strip_ansi(result.stdout).strip()
        if not summary:
            logger.warning('Summary command returned empty output')
            return None

        summary = _clean_summary(summary)
        return summary

    except subprocess.TimeoutExpired:
        logger.error('Summary generation timed out after %ds', timeout)
        return None
    except OSError as e:
        logger.error('Failed to run summary command: %s', e)
        return None


# qwen2.5:14b is the practical default: good quality at ~12GB VRAM. Users with
# more headroom can switch to qwen2.5:32b; users without a GPU can switch to
# `claude -p`. See README for the full table.
DEFAULT_SUMMARY_CMD = 'ollama run --nowordwrap qwen2.5:14b'


def render_markdown(
    pr_list: list[dict],
    version: str,
    include_uncategorized: bool = False,
    summary: str | None = None,
    include_release_machinery: bool = False,
) -> str:
    by_sig: dict[str, list[dict]] = {}
    uncategorized = []

    for pr in pr_list:
        flags = pr.get('flags', [])
        if 'cherry-pick' in flags or 'stabilization-sync' in flags:
            continue
        if not include_release_machinery and pr.get('release_machinery'):
            continue

        sig = pr.get('sig_category', 'uncategorized')
        if sig == 'uncategorized':
            uncategorized.append(pr)
        else:
            by_sig.setdefault(sig, []).append(pr)

    lines = []
    lines.append(f'# {version} Release Notes')
    lines.append('')

    if summary:
        lines.append(summary)
    else:
        lines.append(f'The O3DE {version} release includes bug fixes, performance enhancements, '
                     f'and new features across the engine.')
        lines.append('')
        lines.append('<!-- TODO: Write a narrative summary of the release highlights -->')

    lines.append('')
    lines.append('# Full list of changes')
    lines.append('')

    for sig in SIG_CANONICAL_ORDER:
        prs = by_sig.get(sig, [])
        if not prs:
            continue

        display_name = SIG_DISPLAY_NAMES.get(sig, sig)
        lines.append(f'## {display_name}')

        prs.sort(key=lambda p: p.get('number', 0))
        for pr in prs:
            desc = pr.get('description', '') or _sanitize_pr_title_for_markdown(pr.get('title', ''))
            ref = _format_pr_reference(pr.get('repo', ''), pr.get('number', 0), pr.get('url', ''))
            lines.append(f'- {desc} {ref}')

        lines.append('')

    if include_uncategorized and uncategorized:
        lines.append('## Uncategorized')
        lines.append('')
        lines.append('<!-- These PRs could not be automatically categorized. '
                     'Please assign them to the correct SIG section. -->')
        uncategorized.sort(key=lambda p: p.get('number', 0))
        for pr in uncategorized:
            desc = _sanitize_pr_title_for_markdown(pr.get('title', ''))
            ref = _format_pr_reference(pr.get('repo', ''), pr.get('number', 0), pr.get('url', ''))
            lines.append(f'- {desc} {ref}')
        lines.append('')

    return '\n'.join(lines) + '\n'


def write_json_atomic(data: dict, path: pathlib.Path) -> None:
    path = path.resolve()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix='.release_notes_',
        suffix='.json.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write('\n')
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_markdown_atomic(content: str, path: pathlib.Path) -> None:
    path = path.resolve()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix='.release_notes_',
        suffix='.md.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_existing_json(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict) or 'pull_requests' not in data:
            logger.warning('Existing JSON at %s has unexpected structure, ignoring', path)
            return None
        sv = data.get('metadata', {}).get('schema_version', 0)
        if sv not in (SCHEMA_VERSION, SCHEMA_VERSION - 1):
            logger.warning('Schema version mismatch (got %d, expected %d), re-fetching', sv, SCHEMA_VERSION)
            return None
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning('Failed to load existing JSON at %s: %s', path, e)
        return None


def _run_fetch(args: argparse.Namespace) -> int:
    dry_run = getattr(args, 'dry_run', False)

    if not dry_run and not _check_gh_available():
        return 1

    try:
        repo_path_map = parse_repo_path_mappings(
            args.repo_path,
            args.default_repo_path,
            args.repos,
        )
    except ValueError as e:
        logger.error('%s', e)
        return 1

    for slug, rpath in repo_path_map.items():
        if not (rpath / '.git').exists():
            logger.error('Not a git repository: %s (for %s)', rpath, slug)
            return 1

    # Feature #3: point-release awareness. If --from-ref looks like a point
    # release (X.Y.N with N>0), surface the sibling tags and the implicit
    # equivalence with the major tag, computed against the first repo. The same
    # principle holds across all repos that share the release cadence.
    _emit_point_release_awareness_log(
        args.from_ref, args.to_ref, repo_path_map, args.repos,
    )

    if dry_run:
        for repo_slug in args.repos:
            try:
                validate_repo_slug(repo_slug)
            except ValueError as e:
                logger.error('%s', e)
                return 1
            local_path = repo_path_map[repo_slug]
            try:
                pr_numbers = extract_pr_numbers_from_git_log(local_path, args.from_ref, args.to_ref)
            except (RuntimeError, ValueError) as e:
                logger.error('%s', e)
                return 1
            logger.info(
                '[dry-run] %s: %d PRs would be fetched between %s..%s (%s)',
                repo_slug, len(pr_numbers), args.from_ref, args.to_ref, local_path,
            )
            if pr_numbers:
                preview = ', '.join(f'#{n}' for n in pr_numbers[:10])
                more = f' ... and {len(pr_numbers) - 10} more' if len(pr_numbers) > 10 else ''
                logger.info('[dry-run] %s PR numbers: %s%s', repo_slug, preview, more)
        logger.info('[dry-run] No GitHub API calls made; no files written.')
        return 0

    output_json = validate_output_path(pathlib.Path(args.output_json))

    all_prs = []
    for repo_slug in args.repos:
        try:
            validate_repo_slug(repo_slug)
        except ValueError as e:
            logger.error('%s', e)
            return 1

        local_path = repo_path_map[repo_slug]
        logger.info('Extracting PR numbers from git log for %s (%s..%s) at %s',
                     repo_slug, args.from_ref, args.to_ref, local_path)
        try:
            pr_numbers = extract_pr_numbers_from_git_log(local_path, args.from_ref, args.to_ref)
        except (RuntimeError, ValueError) as e:
            logger.error('%s', e)
            return 1

        logger.info('Found %d PRs in %s', len(pr_numbers), repo_slug)

        if not pr_numbers:
            logger.warning('No PRs found in %s between %s and %s', repo_slug, args.from_ref, args.to_ref)
            continue

        logger.info('Fetching PR metadata from GitHub for %s', repo_slug)
        fetched = fetch_pr_metadata_batch(repo_slug, pr_numbers)

        for pr in fetched:
            sig, source = categorize_pr(pr)
            pr['sig_category'] = sig
            pr['categorization_source'] = source
            pr['description'] = _build_pr_description(pr.get('title', ''), pr.get('body', ''))
            pr['flags'] = detect_pr_flags(pr)
            pr['release_machinery'] = is_release_machinery(pr)
            pr['manual_override_sig'] = None
            pr['manual_override_description'] = None

        all_prs.extend(fetched)

    existing_path = output_json if output_json.exists() else None
    merged = merge_with_existing(all_prs, existing_path)

    cat_counts: dict[str, int] = {}
    machinery_count = 0
    for pr in merged:
        src = pr.get('categorization_source', 'unknown')
        cat_counts[src] = cat_counts.get(src, 0) + 1
        # Backfill release_machinery on PRs that came in via merge_with_existing
        # from a previous (older) JSON that pre-dates this field.
        if 'release_machinery' not in pr:
            pr['release_machinery'] = is_release_machinery(pr)
        if pr.get('release_machinery'):
            machinery_count += 1

    # Feature #2: per-repo merge-base + effective window, computed best-effort.
    merge_bases: dict[str, dict] = {}
    effective_window_start = None
    for repo_slug, rpath in repo_path_map.items():
        mb = extract_merge_base(rpath, args.from_ref, args.to_ref)
        if mb is None:
            continue
        sha, date = mb
        merge_bases[repo_slug] = {'sha': sha, 'committer_date': date}
        if date and (effective_window_start is None or date < effective_window_start):
            effective_window_start = date

    metadata: dict = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'from_ref': args.from_ref,
        'to_ref': args.to_ref,
        'repos': args.repos,
        'repo_paths': {k: str(v) for k, v in repo_path_map.items()},
        'schema_version': SCHEMA_VERSION,
        'pr_count': len(merged),
        'categorization_summary': cat_counts,
        'release_machinery_count': machinery_count,
    }
    if merge_bases:
        metadata['merge_bases'] = merge_bases
    if effective_window_start:
        metadata['effective_window'] = {
            'start': effective_window_start,
            'end': metadata['generated_at'],
        }

    output_data = {'metadata': metadata, 'pull_requests': merged}

    write_json_atomic(output_data, output_json)
    logger.info('Wrote %d PRs to %s', len(merged), output_json)
    logger.info('Categorization: %s', ', '.join(f'{k}={v}' for k, v in sorted(cat_counts.items())))
    if machinery_count:
        logger.info(
            'Release machinery: %d PR(s) flagged (e.g. version bumps, point-release wrappers)',
            machinery_count,
        )

    # Feature #1: point-release audit sidecar. Only runs when from-ref is a
    # point-release tag with a known predecessor sibling.
    if not getattr(args, 'no_pointrelease_audit', False):
        _maybe_write_pointrelease_audit(args, merged, repo_path_map, output_json)

    return 0


def _emit_point_release_awareness_log(
    from_ref: str,
    to_ref: str,
    repo_path_map: dict[str, pathlib.Path],
    repos: list[str],
) -> None:
    """One INFO line explaining the merge-base equivalence between a major tag
    and its point-release siblings. Only emitted when --from-ref looks like a
    point release after the .0 (i.e., X.Y.N with N>0)."""
    parsed = parse_point_release_tag(from_ref)
    if parsed is None or parsed[1] == 0:
        return
    if not repos:
        return
    first_repo = repos[0]
    rpath = repo_path_map.get(first_repo)
    if rpath is None:
        return
    siblings = find_sibling_point_release_tags(rpath, from_ref)
    earlier = [t for t in siblings if t != from_ref and (parse_point_release_tag(t) or (0, 0))[1] < parsed[1]]
    if not earlier:
        return
    major_tag = next((t for t in earlier if (parse_point_release_tag(t) or (0, 0))[1] == 0), None)
    if major_tag is None:
        return
    mb_major = extract_merge_base(rpath, major_tag, to_ref)
    mb_point = extract_merge_base(rpath, from_ref, to_ref)
    if mb_major and mb_point and mb_major[0] == mb_point[0]:
        logger.info(
            'Point releases on %s line: %s. They share the same merge base with %s as %s (%s); '
            'cherry-picks onto the %s branch are correctly excluded; bundled fixes appear via '
            'their development-side merges. --from-ref %s and --from-ref %s yield identical PR sets.',
            parsed[0],
            ', '.join(earlier),
            to_ref,
            major_tag,
            mb_major[0][:10],
            parsed[0],
            major_tag,
            from_ref,
        )


def _maybe_write_pointrelease_audit(
    args: argparse.Namespace,
    merged: list[dict],
    repo_path_map: dict[str, pathlib.Path],
    output_json: pathlib.Path,
) -> None:
    """Run the point-release audit when --from-ref is a non-zero point release.
    Writes a sidecar `<output_md_stem>_pointrelease_audit.md` next to the
    markdown output, or next to the JSON if --output-md isn't set yet."""
    parsed = parse_point_release_tag(args.from_ref)
    if parsed is None or parsed[1] == 0:
        return
    audit_per_repo: dict[str, dict] = {}
    any_container = False
    for repo_slug, rpath in repo_path_map.items():
        siblings = find_sibling_point_release_tags(rpath, args.from_ref)
        major_tag = next(
            (t for t in siblings if (parse_point_release_tag(t) or (0, 0))[1] == 0),
            None,
        )
        if major_tag is None:
            continue
        containers = extract_pointrelease_containers(rpath, major_tag, args.from_ref)
        if not containers:
            continue
        any_container = True
        present_numbers = {pr.get('number') for pr in merged if pr.get('repo') == repo_slug}
        audit_per_repo[repo_slug] = {
            'containers': containers,
            'present_pr_numbers': present_numbers,
            'predecessor_tag': major_tag,
        }

    if not any_container:
        return

    # Sidecar path: derive from --output-md when available; otherwise sit next
    # to the JSON. Same stem as the markdown report so the pair is easy to find.
    output_md = getattr(args, 'output_md', None)
    if output_md:
        md_path = pathlib.Path(output_md).resolve()
        audit_path = md_path.with_name(md_path.stem + '_pointrelease_audit.md')
    else:
        audit_path = output_json.with_name(output_json.stem + '_pointrelease_audit.md')

    audit_data = {
        'from_ref': args.from_ref,
        'to_ref': args.to_ref,
        'predecessor_tag': next(iter(audit_per_repo.values()))['predecessor_tag'],
        'per_repo': audit_per_repo,
    }
    try:
        write_pointrelease_audit(audit_data, audit_path)
        logger.info('Wrote point-release audit sidecar to %s', audit_path)
    except OSError as e:
        logger.warning('Could not write audit sidecar: %s', e)


def _run_render(args: argparse.Namespace) -> int:
    input_json = pathlib.Path(args.input_json).resolve()
    if not input_json.exists():
        logger.error('Input JSON not found: %s', input_json)
        return 1

    output_md = validate_output_path(pathlib.Path(args.output_md))

    data = load_existing_json(input_json)
    if data is None:
        logger.error('Failed to load valid JSON from %s', input_json)
        return 1

    include_release_machinery = getattr(args, 'include_release_machinery', False)
    summary = None
    if getattr(args, 'generate_summary', False):
        summary_cmd = getattr(args, 'summary_cmd', DEFAULT_SUMMARY_CMD)
        summary_hint = getattr(args, 'summary_hint', '') or ''
        summary_timeout = getattr(args, 'summary_timeout', DEFAULT_SUMMARY_TIMEOUT)
        summary = generate_summary(
            data['pull_requests'], args.release_version, summary_cmd,
            hint=summary_hint, timeout=summary_timeout,
            include_release_machinery=include_release_machinery,
        )
        if summary:
            logger.info('Generated narrative summary (%d chars)', len(summary))
        else:
            logger.warning('Summary generation failed, using placeholder')

    content = render_markdown(
        data['pull_requests'],
        args.release_version,
        include_uncategorized=args.include_uncategorized,
        summary=summary,
        include_release_machinery=include_release_machinery,
    )

    write_markdown_atomic(content, output_md)
    logger.info('Wrote release notes to %s', output_md)

    return 0


def _run_generate(args: argparse.Namespace) -> int:
    rc = _run_fetch(args)
    if rc != 0:
        return rc
    if getattr(args, 'dry_run', False):
        return 0
    args.input_json = args.output_json
    return _run_render(args)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )
    parser.add_argument(
        '--log-file',
        default=None,
        help='Append logs to this file in addition to stderr',
    )


def _add_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--from-ref', required=True,
                        help='Starting git reference (tag or commit)')
    parser.add_argument('--to-ref', required=True,
                        help='Ending git reference (branch or tag)')
    parser.add_argument('--repos', nargs='+', default=DEFAULT_REPOS,
                        help='GitHub repos in owner/repo format (default: o3de/o3de)')
    parser.add_argument('--repo-path', nargs='*', default=None,
                        help='Per-repo local clone paths as owner/repo=/path/to/clone')
    parser.add_argument('--default-repo-path', default='.',
                        help='Default local clone path for repos without explicit mapping (default: .)')
    parser.add_argument('--output-json', required=True,
                        help='Output JSON file path')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show which PRs would be fetched (from git log) and exit '
                             'without calling the GitHub API or writing any files')
    parser.add_argument('--no-pointrelease-audit', action='store_true',
                        help='Skip the point-release audit sidecar even when --from-ref '
                             'looks like a point-release tag')


def _add_render_args(parser: argparse.ArgumentParser, require_input_json: bool = True) -> None:
    if require_input_json:
        parser.add_argument('--input-json', required=True,
                            help='Input JSON file path')
    parser.add_argument('--output-md', required=True,
                        help='Output markdown file path')
    parser.add_argument('--release-version', required=True, dest='release_version',
                        help='Release version string (e.g. 26.05.0)')
    parser.add_argument('--include-uncategorized', action='store_true',
                        help='Include uncategorized PRs in output')
    parser.add_argument('--generate-summary', action='store_true', default=False,
                        help='Generate a narrative summary using an LLM (default: off)')
    parser.add_argument('--summary-cmd', default=DEFAULT_SUMMARY_CMD,
                        help=f'Command to generate summary (default: {DEFAULT_SUMMARY_CMD})')
    parser.add_argument('--summary-hint', default='',
                        help='Narrative guidance for the LLM: inline text or @filepath to read from a file')
    parser.add_argument('--summary-timeout', type=int, default=DEFAULT_SUMMARY_TIMEOUT,
                        help=f'Timeout (seconds) for the summary command '
                             f'(default: {DEFAULT_SUMMARY_TIMEOUT}; range: '
                             f'{MIN_SUMMARY_TIMEOUT}-{MAX_SUMMARY_TIMEOUT})')
    parser.add_argument('--include-release-machinery', action='store_true',
                        help='Include release-engineering PRs (version bumps, SBOM auto-updates, '
                             'point-release branch admin, etc.) in the rendered output. '
                             'Default: off for major releases; turn on for point-release notes '
                             'where this IS the content.')


def add_parser_args(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest='subcommand', required=True)

    fetch_parser = subparsers.add_parser('fetch', help='Fetch PR data from GitHub into JSON')
    _add_fetch_args(fetch_parser)
    _add_common_args(fetch_parser)
    fetch_parser.set_defaults(func=_run_fetch)

    render_parser = subparsers.add_parser('render', help='Render markdown from JSON')
    _add_render_args(render_parser)
    _add_common_args(render_parser)
    render_parser.set_defaults(func=_run_render)

    gen_parser = subparsers.add_parser('generate', help='Fetch and render in one step')
    _add_fetch_args(gen_parser)
    _add_render_args(gen_parser, require_input_json=False)
    _add_common_args(gen_parser)
    gen_parser.set_defaults(func=_run_generate)


def _configure_logging(verbose: bool, log_file: str | None) -> None:
    logging.basicConfig(format=LOG_FORMAT)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if log_file:
        try:
            handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(handler)
        except OSError as e:
            logger.error('Could not open log file %s: %s', log_file, e)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='release_notes',
        description='Generate O3DE release notes from merged pull requests',
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    add_parser_args(parser)
    args = parser.parse_args()

    _configure_logging(args.verbose, getattr(args, 'log_file', None))

    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
