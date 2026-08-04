#!/usr/bin/env python3
#
# Copyright (c) Contributors to the Open 3D Engine Project.
# For complete copyright and license terms please see the LICENSE at the root of this distribution.
#
# SPDX-License-Identifier: Apache-2.0 OR MIT
#

import argparse
import contextlib
import json
import logging
import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, cast

LOG_FORMAT = '[%(levelname)s] %(name)s: %(message)s'
logger = logging.getLogger('o3de.release_notes')

__version__ = '0.8.1-beta'

# 6: adds metadata.reused_from_cache, recording how many PRs were served from
#    the previous report instead of re-fetched.
# 5: adds per-PR `files_truncated` and metadata.file_list_truncated, so a
#    curator can see which entries were categorised from a partial file list.
# 4: adds metadata.tool_version; `flags` no longer carries `stabilization-sync`
#    and descriptions are no longer truncated mid-sentence, so data written by
#    <=0.5.0-beta is structurally readable but semantically stale. Version 3
#    files still load (renderer ignores the legacy flag); re-fetch for accuracy.
SCHEMA_VERSION = 6

GIT_REF_PATTERN = re.compile(r'^[a-zA-Z0-9._/\-]+$')
REPO_SLUG_PATTERN = re.compile(r'^[a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+$')
REPO_PATH_MAPPING_PATTERN = re.compile(r'^([a-zA-Z0-9_.\-]+/[a-zA-Z0-9_.\-]+)=(.+)$')
PR_NUMBER_PATTERN = re.compile(r'\(#(\d+)\)')

# O3DE uses two merge strategies on `development`. Squash-merges put the PR
# number in the subject as `(#NNNN)`; merge-commit PRs produce
# `Merge pull request #NNNN from owner/branch` with no parentheses, and their
# constituent commits carry no PR reference at all. Matching only the squash
# form (and passing --no-merges to git log) silently loses every merge-commit
# PR: 19 of them in the 2605.0..development window alone.
MERGE_COMMIT_PR_PATTERN = re.compile(r'^Merge pull request #(\d+)\b')

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
        # Catch-alls for the two build-owned trees. Safe because matching is
        # longest-wins: 'cmake/LYTestWrappers.cmake' and 'scripts/ctest/' still
        # resolve to sig/testing, and 'scripts/o3de/' still resolves to
        # sig/core. Without these, files sitting directly in cmake/ or scripts/
        # (o3deConfigVersion.cmake, LYPython.cmake, 3rdPartyPackages.cmake,
        # o3de.sh) matched nothing and fell through to uncategorized.
        'cmake/',
        'scripts/',
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
    # Repository governance, owned by the TSC rather than by any SIG. The
    # release notes are organised entirely by SIG, so there is no correct
    # heading for this: filing it under sig/release or sig/docs-community would
    # credit a SIG with work it did not do. It is not an engine change, so it
    # does not belong in the notes at all.
    #
    # Classified here rather than left uncategorized so the exclusion is a
    # decision instead of a failure. "Uncategorized" is a triage signal, and a
    # PR that recurs there every cycle with the same answer trains curators to
    # skim the one list they most need to read.
    #
    # Deliberately the exact file, not `.github/`: workflows and issue
    # templates under that directory are real work by real SIGs.
    re.compile(r'^\.github/FUNDING\.yml$'),
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


def parse_repo_ref_mappings(
    entries: list[str] | None,
    default_ref: str,
    repos: list[str],
    flag_name: str,
) -> dict[str, str]:
    """Resolve per-repo git refs, falling back to the global ref.

    Release lines do not tag every repo. `o3de/o3de` carries `2605.0` but
    `o3de/o3de-extras` does not, so a single global --from-ref aborts the whole
    multi-repo run on the repo that lacks the tag.
    """
    mappings: dict[str, str] = {}

    for entry in entries or []:
        match = REPO_PATH_MAPPING_PATTERN.match(entry)
        if not match:
            raise ValueError(
                f'Invalid {flag_name} mapping: {entry!r}. Use owner/repo=REF format.'
            )
        slug, ref = match.group(1), match.group(2)
        validate_repo_slug(slug)
        mappings[slug] = validate_git_ref(ref)

    for repo in repos:
        if repo not in mappings:
            mappings[repo] = validate_git_ref(default_ref)

    return mappings


def ref_exists(repo_path: pathlib.Path, ref: str) -> bool:
    ref = validate_git_ref(ref)
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}'],
            cwd=str(repo_path.resolve()),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning('git rev-parse failed for %s in %s: %s', ref, repo_path, e)
        return False
    return result.returncode == 0


def verify_refs_exist(
    repo_path_map: dict[str, pathlib.Path],
    from_ref_map: dict[str, str],
    to_ref_map: dict[str, str],
    repos: list[str],
) -> list[str]:
    """Preflight every (repo, ref) pair and return human-readable problems.

    Catching this upfront turns a mid-run `git log` abort, after minutes of
    GitHub API calls, into an actionable error before any work starts.
    """
    problems: list[str] = []
    for repo_slug in repos:
        repo_path = repo_path_map.get(repo_slug)
        if repo_path is None:
            continue
        for label, ref in (('--from-ref', from_ref_map.get(repo_slug, '')),
                           ('--to-ref', to_ref_map.get(repo_slug, ''))):
            if not ref:
                continue
            if not ref_exists(repo_path, ref):
                problems.append(
                    f'{repo_slug}: {label} {ref!r} does not resolve in {repo_path}. '
                    f'Fetch tags (`git -C {repo_path} fetch --tags`) or override with '
                    f'--repo-from-ref/--repo-to-ref {repo_slug}=<ref>.'
                )
    return problems


MAX_STDERR_LOG_LEN = 200

# Defense-in-depth: scrub GitHub token shapes from stderr before logging.
# gh CLI is unlikely to print tokens, but if it ever does, we don't want them
# in CI logs.
# Classic tokens (ghp_/gho_/ghu_/ghs_/ghr_) and fine-grained PATs, which use a
# github_pat_ prefix and may contain underscores in the body.
GH_TOKEN_PATTERN = re.compile(
    r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'
)


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
) -> list[dict[str, Any]]:
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

    containers: list[dict[str, Any]] = []
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
    audit_data: dict[str, Any],
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
        "The bundled PRs are extracted from the container's commit body, then\n"
        "checked against what the report actually renders:\n"
        "\n"
        "- ✓ present in the rendered report, via its development-side merge\n"
        "- ⚠ collected but filtered OUT of the report (reason shown). These are\n"
        "  the dangerous ones: the fix shipped in the point release, so a reader\n"
        "  expects it here. Confirm the filter is right before publishing.\n"
        "- ✗ not found at all. Investigate.\n"
        "\n"
        "The ⚠ state exists because comparing against the collected JSON rather\n"
        "than the rendered output reports a green tick for a fix the reader will\n"
        "never see.\n"
    )

    grand_total_containers = 0
    grand_total_bundled = 0
    grand_total_present = 0
    grand_total_filtered = 0
    grand_total_missing = 0

    for repo_slug, repo_audit in audit_data.get('per_repo', {}).items():
        containers = repo_audit.get('containers', [])
        present = repo_audit.get('present_pr_numbers', set())
        filtered = repo_audit.get('filtered_pr_numbers', {})
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
                elif b in filtered:
                    grand_total_filtered += 1
                    lines.append(
                        f"  - ⚠ #{b}: collected but FILTERED OUT of the report "
                        f"({filtered[b]}); shipped in the point release, so verify"
                    )
                else:
                    grand_total_missing += 1
                    lines.append(f"  - ✗ #{b}: NOT found at all (investigate)")

    lines.append('')
    verdict = (
        "All bundled fixes are present in the rendered report."
        if not grand_total_filtered and not grand_total_missing
        else "**Action required before publishing.**"
    )
    lines.append(
        f"---\n\n"
        f"**Summary:** {grand_total_containers} container(s) checked, "
        f"{grand_total_bundled} bundled PR reference(s) parsed: "
        f"{grand_total_present} rendered, "
        f"{grand_total_filtered} filtered out, "
        f"{grand_total_missing} not found. {verdict}\n"
    )
    content = '\n'.join(lines)
    write_markdown_atomic(content, output_path)


def is_release_machinery(pr_data: dict[str, Any]) -> bool:
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
    return all(
        any(p.search(fpath) for p in RELEASE_MACHINERY_FILE_PATTERNS)
        for fpath in files
    )


def extract_pr_numbers_from_git_log(
    repo_path: pathlib.Path,
    from_ref: str,
    to_ref: str,
) -> list[int]:
    from_ref = validate_git_ref(from_ref)
    to_ref = validate_git_ref(to_ref)

    # Merge commits are deliberately included: they are the only place a
    # merge-commit PR's number appears. Duplicates across the two patterns are
    # collapsed by the set.
    try:
        result = subprocess.run(
            ['git', 'log', '--format=%s', f'{from_ref}..{to_ref}'],
            cwd=str(repo_path.resolve()),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as e:
        raise RuntimeError(f'git log {from_ref}..{to_ref} failed in {repo_path}: {e}') from e
    if result.returncode != 0:
        logger.error('git log failed: %s', _safe_stderr(result.stderr))
        raise RuntimeError(f'git log failed with exit code {result.returncode}')

    pr_numbers = set()
    merge_commit_prs = 0
    for line in result.stdout.splitlines():
        for match in PR_NUMBER_PATTERN.finditer(line):
            pr_numbers.add(int(match.group(1)))
        merge_match = MERGE_COMMIT_PR_PATTERN.match(line)
        if merge_match:
            number = int(merge_match.group(1))
            if number not in pr_numbers:
                merge_commit_prs += 1
            pr_numbers.add(number)

    if merge_commit_prs:
        logger.info(
            '%d PR(s) found via merge commits (`Merge pull request #N`) in %s',
            merge_commit_prs, repo_path,
        )

    return sorted(pr_numbers)


# GraphQL page sizes. The truncation check below reads these, so changing a
# page size cannot leave the check testing the old bound.
FILES_PAGE_SIZE = 100
LABELS_PAGE_SIZE = 20

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
            f'    labels(first: {LABELS_PAGE_SIZE}) {{ nodes {{ name }} }}\n'
            f'    files(first: {FILES_PAGE_SIZE}) {{ nodes {{ path }} }}\n'
            f'  }}'
        )

    return (
        'query($owner: String!, $name: String!) {\n'
        '  repository(owner: $owner, name: $name) {\n'
        + '\n'.join(fragments) +
        '\n  }\n'
        '}'
    )


class GhCommandError(RuntimeError):
    """A `gh` invocation failed. Carries the scrubbed stderr for classification."""

    def __init__(self, message: str, stderr: str = '') -> None:
        super().__init__(message)
        self.stderr = stderr


# A PR number that GitHub cannot resolve is permanent: retrying cannot help.
# It usually means the number came from an issue reference in a commit subject,
# e.g. "Fix prefab path expansion (#18886) (#19254)" where only the second is
# the PR. Parse the offending numbers out so the batch can drop them and retry,
# instead of degrading to one request per PR.
UNRESOLVABLE_PR_PATTERN = re.compile(
    r'Could not resolve to a PullRequest with the number of (\d+)', re.IGNORECASE,
)

# Failures worth retrying. Anything else is treated as permanent.
TRANSIENT_ERROR_MARKERS = (
    'rate limit', 'secondary rate', 'abuse detection',
    'timed out', 'timeout', 'connection reset', 'connection refused',
    'temporary failure', 'bad gateway', 'service unavailable',
    '502', '503', '504',
)

MAX_BATCH_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0


def _unresolvable_pr_numbers(stderr: str) -> set[int]:
    return {int(m.group(1)) for m in UNRESOLVABLE_PR_PATTERN.finditer(stderr or '')}


def _is_transient_error(stderr: str) -> bool:
    lowered = (stderr or '').lower()
    return any(marker in lowered for marker in TRANSIENT_ERROR_MARKERS)


def _backoff_seconds(attempt: int) -> float:
    """Exponential, capped. attempt is 0-based."""
    return float(min(BACKOFF_BASE_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS))


def _run_gh_command(args: list[str], timeout: int = 30) -> dict[str, Any]:
    # A timeout or a missing binary must surface as RuntimeError like any other
    # gh failure. Letting TimeoutExpired escape aborted the whole run with a
    # traceback and discarded every batch already fetched.
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise GhCommandError(f'gh command timed out after {timeout}s', 'timed out') from e
    except (subprocess.SubprocessError, OSError) as e:
        raise GhCommandError(f'gh command failed to run: {e}', str(e)) from e
    if result.returncode != 0:
        stderr = _safe_stderr(result.stderr)
        if 'rate limit' in stderr.lower() or '403' in stderr:
            logger.error('GitHub API rate limit exceeded. Backing off.')
        else:
            logger.error('gh command failed: %s', stderr)
        raise GhCommandError(f'gh command failed with exit code {result.returncode}', stderr)

    try:
        return cast(dict[str, Any], json.loads(result.stdout))
    except json.JSONDecodeError as e:
        raise GhCommandError(f'gh returned non-JSON output: {e}', str(e)) from e


def _check_gh_available() -> bool:
    if not shutil.which('gh'):
        logger.error('gh CLI is required but not found. Install from https://cli.github.com/')
        return False

    try:
        result = subprocess.run(
            ['gh', 'auth', 'status'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError) as e:
        logger.error('Could not run `gh auth status`: %s', e)
        return False
    if result.returncode != 0:
        logger.error('gh CLI is not authenticated. Run: gh auth login')
        return False

    return True


MAX_PR_NUMBER = 999999


def _fetch_batch_with_retry(
    batch: list[int],
    batch_num: int,
    owner: str,
    repo: str,
) -> dict[str, Any] | None:
    """Fetch one batch, handling the two failure modes that are worth handling.

    Returns the response, or None when the batch could not be salvaged and the
    caller should fall back to one request per PR.

    An unresolvable PR number is permanent, so the batch drops it and retries
    immediately: previously a single bad number (an issue reference picked up
    from a commit subject) failed the whole batch and cost 30 individual
    requests. A transient failure backs off exponentially instead of instantly
    degrading to 30 requests, which is the worst possible response to a rate
    limit.
    """
    remaining = list(batch)

    for attempt in range(MAX_BATCH_ATTEMPTS):
        if not remaining:
            return None
        try:
            return _run_gh_command(
                ['gh', 'api', 'graphql',
                 '-f', f'query={_build_graphql_query(remaining)}',
                 '-f', f'owner={owner}',
                 '-f', f'name={repo}'],
                timeout=60,
            )
        except GhCommandError as e:
            unresolvable = _unresolvable_pr_numbers(e.stderr) & set(remaining)
            if unresolvable:
                remaining = [n for n in remaining if n not in unresolvable]
                logger.warning(
                    'Batch %d: %s not resolvable as pull request(s) (likely an issue '
                    'reference in a commit subject); dropping and retrying %d PR(s)',
                    batch_num, ', '.join(f'#{n}' for n in sorted(unresolvable)), len(remaining),
                )
                continue
            if _is_transient_error(e.stderr) and attempt < MAX_BATCH_ATTEMPTS - 1:
                delay = _backoff_seconds(attempt)
                logger.warning(
                    'Batch %d failed transiently (attempt %d/%d); retrying in %.0fs',
                    batch_num, attempt + 1, MAX_BATCH_ATTEMPTS, delay,
                )
                time.sleep(delay)
                continue
            return None
    return None


def fetch_pr_metadata_batch(
    repo_slug: str,
    pr_numbers: list[int],
    batch_size: int = 30,
) -> list[dict[str, Any]]:
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

        data = _fetch_batch_with_retry(batch, batch_num, owner, repo)
        if data is None:
            logger.warning('Batch %d unrecoverable, trying individual PRs', batch_num)
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


def files_possibly_truncated(pr_data: dict[str, Any]) -> bool:
    """True when the PR's file list hit the GraphQL page size and may be partial.

    Derived from the stored list, so it also answers correctly for JSON written
    before `files_truncated` existed.
    """
    return len(pr_data.get('files', []) or []) >= FILES_PAGE_SIZE


def _normalize_pr_data(raw: dict[str, Any], repo_slug: str) -> dict[str, Any]:
    file_nodes = raw.get('files', {}).get('nodes', [])
    truncated = len(file_nodes) >= FILES_PAGE_SIZE
    if truncated:
        logger.warning('PR #%d in %s has %d+ changed files; file list may be truncated',
                        raw.get('number', 0), repo_slug, FILES_PAGE_SIZE)
    return {
        'files_truncated': truncated,
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
    sig_labels = [lbl for lbl in labels if lbl.startswith('sig/') and lbl in SIG_CANONICAL_ORDER]
    if not sig_labels:
        return None
    if 'sig/release' in sig_labels and len(sig_labels) > 1:
        sig_labels = [lbl for lbl in sig_labels if lbl != 'sig/release']
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


def categorize_pr(pr_data: dict[str, Any]) -> tuple[str, str]:
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


# Flags that remove a PR from the rendered report and the summary prompt.
# `stabilization-sync` is deliberately absent: it used to be set by a substring
# match on any label containing "sync", which matched O3DE's *workflow-tracking*
# labels (`sync/to-stabilization`, `sync/to-development`,
# `need-sync/to-development`). Those labels live on the ORIGINAL substantive PR,
# not on a sync container, so the filter deleted 57 real changes (22% of the
# corpus) from the 26.05.0 notes. Old JSON files may still carry the flag; by
# keeping it out of this set they now render correctly without a re-fetch.
EXCLUDED_FLAGS = frozenset({'cherry-pick'})


def is_excluded_by_flags(pr_data: dict[str, Any]) -> bool:
    return bool(EXCLUDED_FLAGS.intersection(pr_data.get('flags', []) or []))


def detect_pr_flags(pr_data: dict[str, Any]) -> list[str]:
    """Detect flags on a PR. Only title evidence is trusted for cherry-pick
    containers.

    Labels are NOT used: no O3DE label distinguishes a sync container from a
    normal PR. In the 26.05.0 corpus `sync/to-stabilization` appeared on 30
    ordinary PRs and on 2 containers, making it useless as an exclusion signal.
    """
    flags = []
    title = pr_data.get('title', '')
    for pattern in CHERRY_PICK_PATTERNS:
        if pattern.search(title):
            flags.append('cherry-pick')
            break

    return flags


MARKDOWN_ESCAPE_CHARS = '[]|`'

# Markdown renderers used to publish O3DE release notes (Hugo/goldmark, GitHub)
# pass raw HTML straight through, so an untrusted PR title containing
# `<img src=x onerror=...>` would become live HTML on o3de.org. Escape only
# tag-*like* `<` so ordinary arrows in titles ("fix 64->32 narrowing",
# "Move camera passes ROS2->ROS2Sensors") stay readable in the raw markdown.
HTML_TAG_OPENER_PATTERN = re.compile(r'<(?=[a-zA-Z/!?])')

TRAILING_PR_REF_PATTERN = re.compile(r'\(#\d+\)\s*$')


def _escape_markdown(text: str) -> str:
    escaped = ''.join(f'\\{ch}' if ch in MARKDOWN_ESCAPE_CHARS else ch for ch in text)
    return HTML_TAG_OPENER_PATTERN.sub('\\\\<', escaped)


def _strip_title_decorations(title: str) -> str:
    """Remove the trailing `(#NNNN)` ref and any leading `#` heading markers.

    Kept separate from escaping so callers that compose a longer string can
    strip once and escape once. Escaping twice turns `\\[` into `\\\\[`, which
    markdown renders as a literal backslash followed by an *unescaped* bracket,
    defeating the escape it was meant to apply.
    """
    title = TRAILING_PR_REF_PATTERN.sub('', title.strip()).strip()
    return title.lstrip('#').strip()


def _sanitize_pr_title_for_markdown(title: str) -> str:
    result = _escape_markdown(_strip_title_decorations(title))
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

# Upper bound for a rendered bullet's description. Longer first paragraphs fall
# back to the PR title rather than being truncated mid-sentence.
MIN_DESCRIPTION_CHARS = 20
MAX_DESCRIPTION_CHARS = 300


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

    if (len(first_paragraph) <= MIN_DESCRIPTION_CHARS
            or len(first_paragraph) > MAX_DESCRIPTION_CHARS):
        return sanitized_title

    title_words = set(re.findall(r'[a-zA-Z]{3,}', title.lower()))
    para_words = set(re.findall(r'[a-zA-Z]{3,}', first_paragraph.lower()))
    overlap = title_words & para_words

    if len(title_words) > 0 and len(overlap) / len(title_words) < 0.2:
        # Compose from the RAW title, not the already-escaped one, so the result
        # passes through _sanitize_pr_title_for_markdown exactly once.
        combined = f'{_strip_title_decorations(title)}: {first_paragraph}'
        if len(combined) <= MAX_DESCRIPTION_CHARS:
            return _sanitize_pr_title_for_markdown(combined)
        return sanitized_title

    return _sanitize_pr_title_for_markdown(first_paragraph)


def _extract_first_paragraph(body: str) -> str:
    lines = body.split('\n')
    paragraph_lines: list[str] = []
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

    # Returned untruncated on purpose. _build_pr_description owns the length
    # policy: a paragraph longer than MAX_DESCRIPTION_CHARS falls back to the
    # title. Truncating here instead made that guard dead code (the result was
    # always exactly 300 chars), which is how mid-sentence descriptions ending
    # in a severed URL reached the 26.05.0 notes. The 64KB body cap upstream
    # keeps this bounded.
    return ' '.join(paragraph_lines)


def _format_pr_reference(repo_slug: str, pr_number: int, url: str = '') -> str:
    repo_name = repo_slug.split('/')[-1]
    label = f'{repo_name}#{pr_number}'
    if url:
        return f'[{label}]({url})'
    return f'[{label}](https://github.com/{repo_slug}/pull/{pr_number})'


def merge_with_existing(
    new_prs: list[dict[str, Any]],
    existing_json_path: pathlib.Path | None,
) -> list[dict[str, Any]]:
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
    pr_list: list[dict[str, Any]],
    version: str,
    hint: str = '',
    include_release_machinery: bool = False,
) -> str:
    by_sig: dict[str, list[str]] = {}
    # Third consumer of classify_for_report, for the same reason as the other
    # two: this was a private copy of the filter chain and drifted from it.
    # Duplicates matter here beyond tidiness. The same title listed twice reads
    # to the model as two independent changes and inflates that area's apparent
    # weight in the narrative.
    reasons = classify_reasons(
        pr_list,
        include_uncategorized=False,
        include_release_machinery=include_release_machinery,
    )
    for pr, reason in zip(pr_list, reasons, strict=True):
        if reason is not None:
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
    # The narrative is inserted verbatim into the published markdown. A PR title
    # carrying a prompt injection could steer the model into emitting raw HTML,
    # so neutralise tag openers here too. Markdown emphasis is left intact.
    return HTML_TAG_OPENER_PATTERN.sub('\\\\<', '\n'.join(lines).strip())


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
    pr_list: list[dict[str, Any]],
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


def _normalize_title_for_dedupe(title: str) -> str:
    """Fold a title to a comparison key: whitespace-collapsed and case-insensitive."""
    return ' '.join((title or '').split()).casefold()


def _duplicate_index_groups(pr_list: list[dict[str, Any]]) -> list[list[int]]:
    """Positions of PRs that are the same change, in groups of 2 or more.

    Evidence required: same repo, same normalized title, and the same set of
    changed files. Title alone is too weak over a 200-PR window, where generic
    subjects like "Fix build error" recur on unrelated work; deleting a real
    change is a far worse outcome than printing a bullet twice.

    A PR with no recorded file list is never grouped. Absent evidence is not
    evidence of sameness, and the collapse is only justified by the positive
    kind. All four duplicate groups in the 26.10.0 window satisfy the stricter
    rule, each also sharing an author.

    Indices rather than PR dicts because membership decisions are positional.
    Keying them by (repo, number) would collapse any two entries sharing a key,
    and the caller cannot assume they never do.
    """
    groups: dict[tuple[str, str, frozenset[str]], list[int]] = {}
    for index, pr in enumerate(pr_list):
        title = _normalize_title_for_dedupe(pr.get('title', ''))
        files = frozenset(pr.get('files') or [])
        if not title or not files:
            continue
        groups.setdefault((pr.get('repo', ''), title, files), []).append(index)
    return [
        sorted(indices, key=lambda i: pr_list[i].get('number', 0))
        for _, indices in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1]))
        if len(indices) > 1
    ]


def find_duplicate_pr_groups(
    pr_list: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Group PRs that describe the same change: same repo, same normalized title.

    O3DE's workflow produces genuine duplicates. A fix authored once can land as
    two merged PRs (a resubmission, or the same change proposed against two
    branches), and both then appear in the window with distinct numbers. In the
    26.10.0 draft that is four groups covering eight PRs, two of which rendered
    as adjacent identical bullets.

    Deliberately scoped to a single repo: `o3de` and `o3de-extras` can carry
    genuinely different changes under the same generic title, and collapsing
    across repos would delete real content. Groups are returned sorted, each
    ordered by PR number, so callers get a deterministic survivor.
    """
    return [[pr_list[i] for i in indices] for indices in _duplicate_index_groups(pr_list)]


def classify_reasons(
    pr_list: list[dict[str, Any]],
    include_uncategorized: bool = False,
    include_release_machinery: bool = False,
    include_duplicates: bool = False,
) -> list[str | None]:
    """Per-PR reason for exclusion, aligned position-for-position with `pr_list`.

    The single source of truth for report membership. `render_markdown`, the
    summary prompt, the reconciliation counts, and the point-release audit all
    read it, so they cannot drift. They previously did: the audit consulted the
    collected JSON while the renderer applied filters the audit knew nothing
    about, so a filtered-out PR was reported as present.

    Positional, not keyed by (repo, number), so that two entries sharing a key
    each get their own decision instead of one silently inheriting the other's.
    """
    reasons: list[str | None] = []
    for pr in pr_list:
        excluded_flags = sorted(EXCLUDED_FLAGS.intersection(pr.get('flags', []) or []))
        if excluded_flags:
            reasons.append(excluded_flags[0])
        elif not include_release_machinery and pr.get('release_machinery'):
            reasons.append('release_machinery')
        elif not include_uncategorized and pr.get('sig_category', 'uncategorized') == 'uncategorized':
            reasons.append('uncategorized')
        else:
            reasons.append(None)

    if not include_duplicates:
        # Applied last, and only among PRs that would otherwise render. A
        # duplicate of an already-excluded PR must keep the more specific
        # reason: reporting a cherry-pick as a duplicate would tell a curator
        # to look for an original that is itself not in the report.
        for indices in _duplicate_index_groups(pr_list):
            survivors = [i for i in indices if reasons[i] is None]
            # Prefer a PR that carries a real SIG over one that does not, then
            # the lower number. When a duplicate pair straddles the two, keeping
            # the categorized member preserves a bullet in the right section;
            # keeping the other would file the change under Uncategorized or
            # drop it, losing content the report already had.
            survivors.sort(key=lambda i: (
                pr_list[i].get('sig_category', 'uncategorized') == 'uncategorized',
                pr_list[i].get('number', 0),
            ))
            for i in survivors[1:]:
                reasons[i] = 'duplicate'

    return reasons


def classify_for_report(
    pr_list: list[dict[str, Any]],
    include_uncategorized: bool = False,
    include_release_machinery: bool = False,
    include_duplicates: bool = False,
) -> dict[tuple[str, int], str | None]:
    """`classify_reasons` keyed by (repo, number), for the point-release audit.

    The audit looks PRs up by number, so it needs the mapping. Callers that
    iterate a PR list should use `classify_reasons` instead and stay positional.
    """
    reasons = classify_reasons(
        pr_list, include_uncategorized, include_release_machinery, include_duplicates,
    )
    return {
        (pr.get('repo', ''), pr.get('number', 0)): reason
        for pr, reason in zip(pr_list, reasons, strict=True)
    }


def log_duplicate_groups(
    pr_list: list[dict[str, Any]],
    include_uncategorized: bool = False,
    include_release_machinery: bool = False,
) -> None:
    """Name every collapsed duplicate, rather than only counting them.

    A count tells a curator that something was dropped; it does not let them
    check whether the tool was right. Two PRs sharing a title are strong
    evidence of the same change, not proof, so the pairs are printed.
    """
    reasons = classify_reasons(pr_list, include_uncategorized, include_release_machinery)
    for indices in _duplicate_index_groups(pr_list):
        collapsed = [i for i in indices if reasons[i] == 'duplicate']
        kept = [i for i in indices if reasons[i] is None]
        if not collapsed or not kept:
            continue
        survivor = pr_list[kept[0]]
        logger.warning(
            'Duplicate title in %s: kept #%d, collapsed %s (%r). '
            'Re-run render with --include-duplicates to keep all of them.',
            survivor.get('repo', ''), survivor.get('number', 0),
            ', '.join(f"#{pr_list[i].get('number', 0)}" for i in collapsed),
            (survivor.get('title', '') or '')[:70],
        )


def summarize_render_coverage(
    pr_list: list[dict[str, Any]],
    include_uncategorized: bool = False,
    include_release_machinery: bool = False,
    include_duplicates: bool = False,
) -> dict[str, int]:
    """Account for every PR in the input: how many reach the report, and why the
    rest do not.

    Reasons are evaluated in the same precedence order `render_markdown` applies
    and are mutually exclusive, so `rendered` plus every `excluded_*` count sums
    to `total`. Curators get an explicit reconciliation instead of having to
    notice that a number looks low; the 57-PR `stabilization-sync` regression in
    26.05.0 went unnoticed precisely because nothing reported this.
    """
    counts: dict[str, int] = {'total': len(pr_list), 'rendered': 0}
    for reason in classify_reasons(
        pr_list, include_uncategorized, include_release_machinery, include_duplicates,
    ):
        if reason is None:
            counts['rendered'] += 1
        else:
            counts[f'excluded_{reason}'] = counts.get(f'excluded_{reason}', 0) + 1
    return counts


def log_render_coverage(counts: dict[str, int]) -> None:
    """Emit the reconciliation line, at WARNING when anything was dropped."""
    logger.info(
        'Reconciliation: %d PR(s) in JSON, %d rendered',
        counts.get('total', 0), counts.get('rendered', 0),
    )
    excluded = {
        k[len('excluded_'):]: v
        for k, v in sorted(counts.items())
        if k.startswith('excluded_') and v
    }
    if excluded:
        logger.warning(
            'Excluded %d PR(s) from the report: %s. '
            'Re-run render with --include-uncategorized / --include-release-machinery '
            'to inspect them.',
            sum(excluded.values()),
            ', '.join(f'{k}={v}' for k, v in excluded.items()),
        )


def render_markdown(
    pr_list: list[dict[str, Any]],
    version: str,
    include_uncategorized: bool = False,
    summary: str | None = None,
    include_release_machinery: bool = False,
    include_duplicates: bool = False,
) -> str:
    by_sig: dict[str, list[dict[str, Any]]] = {}
    uncategorized = []

    # Membership comes from classify_for_report rather than a second copy of the
    # filter chain. This function used to re-implement it, which is how the
    # point-release audit and the renderer disagreed about what was in the
    # report; a filter added to one was invisible to the other. The flags are
    # passed through unchanged so this call and the one behind the
    # reconciliation counts classify identically.
    reasons = classify_reasons(
        pr_list,
        include_uncategorized=include_uncategorized,
        include_release_machinery=include_release_machinery,
        include_duplicates=include_duplicates,
    )

    for pr, reason in zip(pr_list, reasons, strict=True):
        if reason is not None:
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


# tempfile.mkstemp() creates files 0600. os.replace() preserves the temp file's
# mode, so without an explicit chmod every output this tool writes ends up
# owner-only, even when replacing a world-readable file (the committed
# sbom.cdx.json was 0600 on disk for exactly this reason).
DEFAULT_OUTPUT_MODE = 0o644


def write_text_atomic(content: str, path: pathlib.Path, suffix: str) -> None:
    """Write `content` to `path` atomically, durably, and without changing its
    permissions.

    fsync before the rename is what makes the SC-28 claim real: os.replace()
    alone is atomic with respect to *other readers*, but on a crash the renamed
    inode can still be empty if its data never reached disk.
    """
    path = path.resolve()
    try:
        target_mode: int | None = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        target_mode = None

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix='.release_notes_',
        suffix=suffix,
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, target_mode if target_mode is not None else DEFAULT_OUTPUT_MODE)
        os.replace(tmp_path, str(path))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def write_json_atomic(data: dict[str, Any], path: pathlib.Path) -> None:
    content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + '\n'
    write_text_atomic(content, path, '.json.tmp')


def write_markdown_atomic(content: str, path: pathlib.Path) -> None:
    write_text_atomic(content, path, '.md.tmp')


def load_existing_json(path: pathlib.Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding='utf-8') as f:
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


def _apply_prior_release_exclusion(
    pr_numbers: list[int],
    repo_slug: str,
    prior_keys: set[tuple[str, int]],
) -> tuple[list[int], int]:
    if not prior_keys:
        return pr_numbers, 0
    kept = [n for n in pr_numbers if (repo_slug, n) not in prior_keys]
    return kept, len(pr_numbers) - len(kept)


def load_prior_release_pr_keys(paths: list[str]) -> tuple[set[tuple[str, int]], list[str]]:
    """Collect (repo, pr_number) pairs already reported in prior release JSONs.

    Deliberately lenient about schema: only `repo` and `number` are read, and
    those exist in every schema version, so an old report is still usable as an
    exclusion source. Returns the keys plus the sources that actually loaded.

    Why this exists: O3DE's `main` line is built from periodic "merge
    stabilization to main" commits, so a release tag like `2605.0` shares only
    an ancient merge-base with `development` (2025-07-29 for 2605.0). A window
    of `2605.0..development` therefore spans two release cycles. The duplicates
    are the development-side merges of fixes that reached the previous release
    by cherry-pick into its stabilization branch: distinct commits, distinct
    SHAs, unreachable from the tag. Neither ancestry nor a date cutoff can
    separate them (the two sets interleave in time), so the only reliable
    signal is whether the PR was already reported.
    """
    keys: set[tuple[str, int]] = set()
    loaded: list[str] = []

    for raw_path in paths:
        path = pathlib.Path(raw_path).resolve()
        if not path.is_file():
            logger.error('--exclude-json not found: %s', path)
            continue
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error('Could not read --exclude-json %s: %s', path, e)
            continue
        if not isinstance(data, dict) or not isinstance(data.get('pull_requests'), list):
            logger.error('--exclude-json %s has no pull_requests list, ignoring', path)
            continue

        before = len(keys)
        for pr in data['pull_requests']:
            if not isinstance(pr, dict):
                continue
            repo = pr.get('repo', '')
            number = pr.get('number')
            if repo and isinstance(number, int):
                keys.add((repo, number))
        loaded.append(str(path))
        logger.info(
            'Exclusion source %s: %d PR(s) already reported (%d new to the set)',
            path, len(data['pull_requests']), len(keys) - before,
        )

    return keys, loaded


# Only label-categorised PRs are cacheable. A PR that fell to a heuristic, or
# failed to categorise at all, is exactly the one whose SIG label may have been
# applied since the last run: caching it would freeze a wrong answer for the
# rest of the cycle. In the 26.10.0 draft that is 120 of 200 cacheable and 80
# always re-fetched, which is the right side of the trade.
CACHEABLE_CATEGORIZATION_SOURCES = frozenset({'label'})


def select_cacheable_prs(existing: dict[str, Any] | None) -> dict[tuple[str, int], dict[str, Any]]:
    if not existing:
        return {}
    return {
        (pr.get('repo', ''), pr.get('number', 0)): pr
        for pr in existing.get('pull_requests', [])
        if pr.get('categorization_source') in CACHEABLE_CATEGORIZATION_SOURCES
    }


def rederive_pr_fields(pr: dict[str, Any]) -> dict[str, Any]:
    """Recompute every derived field from the cached raw GitHub fields.

    Reusing a cached PR must not also reuse conclusions drawn by an older
    version of this tool. Title, body, labels and files are what GitHub gave us;
    everything else is ours to recompute, so a heuristic change applies to
    cached entries on the next run without a re-fetch.
    """
    sig, source = categorize_pr(pr)
    pr['sig_category'] = sig
    pr['categorization_source'] = source
    pr['description'] = _build_pr_description(pr.get('title', ''), pr.get('body', ''))
    pr['flags'] = detect_pr_flags(pr)
    pr['release_machinery'] = is_release_machinery(pr)
    pr['files_truncated'] = files_possibly_truncated(pr)
    return pr


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

    try:
        from_ref_map = parse_repo_ref_mappings(
            getattr(args, 'repo_from_ref', None), args.from_ref, args.repos, '--repo-from-ref',
        )
        to_ref_map = parse_repo_ref_mappings(
            getattr(args, 'repo_to_ref', None), args.to_ref, args.repos, '--repo-to-ref',
        )
    except ValueError as e:
        logger.error('%s', e)
        return 1

    problems = verify_refs_exist(repo_path_map, from_ref_map, to_ref_map, args.repos)
    if problems:
        for problem in problems:
            logger.error('%s', problem)
        return 1

    exclude_paths = list(getattr(args, 'exclude_json', None) or [])
    # Pointing --exclude-json at this run's own output would exclude everything
    # on the second run and quietly empty the report.
    output_json_resolved = pathlib.Path(args.output_json).resolve()
    for raw in exclude_paths:
        if pathlib.Path(raw).resolve() == output_json_resolved:
            logger.error(
                '--exclude-json %s is this run\'s --output-json. That would exclude every '
                'PR on the next run. Point it at a PRIOR release report instead.', raw,
            )
            return 1
    prior_keys, exclude_sources = load_prior_release_pr_keys(exclude_paths)
    if exclude_paths and not exclude_sources:
        logger.error('No usable --exclude-json source loaded; refusing to continue.')
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
            repo_from_ref = from_ref_map[repo_slug]
            repo_to_ref = to_ref_map[repo_slug]
            try:
                pr_numbers = extract_pr_numbers_from_git_log(
                    local_path, repo_from_ref, repo_to_ref)
            except (RuntimeError, ValueError) as e:
                logger.error('%s', e)
                return 1
            pr_numbers, dropped = _apply_prior_release_exclusion(
                pr_numbers, repo_slug, prior_keys)
            if dropped:
                logger.info(
                    '[dry-run] %s: %d PR(s) already reported in a prior release, excluded',
                    repo_slug, dropped,
                )
            logger.info(
                '[dry-run] %s: %d PRs would be fetched between %s..%s (%s)',
                repo_slug, len(pr_numbers), repo_from_ref, repo_to_ref, local_path,
            )
            if pr_numbers:
                preview = ', '.join(f'#{n}' for n in pr_numbers[:10])
                more = f' ... and {len(pr_numbers) - 10} more' if len(pr_numbers) > 10 else ''
                logger.info('[dry-run] %s PR numbers: %s%s', repo_slug, preview, more)
        logger.info('[dry-run] No GitHub API calls made; no files written.')
        return 0

    output_json = validate_output_path(pathlib.Path(args.output_json))

    reuse_existing = getattr(args, 'reuse_existing', False)
    cacheable = (
        select_cacheable_prs(load_existing_json(output_json))
        if reuse_existing and output_json.exists() else {}
    )
    if reuse_existing and not cacheable:
        logger.info('--reuse-existing: no cacheable PRs in %s; fetching everything',
                    output_json)

    all_prs: list[dict[str, Any]] = []
    excluded_per_repo: dict[str, int] = {}
    reused_per_repo: dict[str, int] = {}
    for repo_slug in args.repos:
        try:
            validate_repo_slug(repo_slug)
        except ValueError as e:
            logger.error('%s', e)
            return 1

        local_path = repo_path_map[repo_slug]
        repo_from_ref = from_ref_map[repo_slug]
        repo_to_ref = to_ref_map[repo_slug]
        logger.info('Extracting PR numbers from git log for %s (%s..%s) at %s',
                     repo_slug, repo_from_ref, repo_to_ref, local_path)
        try:
            pr_numbers = extract_pr_numbers_from_git_log(local_path, repo_from_ref, repo_to_ref)
        except (RuntimeError, ValueError) as e:
            logger.error('%s', e)
            return 1

        logger.info('Found %d PRs in %s', len(pr_numbers), repo_slug)

        pr_numbers, dropped = _apply_prior_release_exclusion(pr_numbers, repo_slug, prior_keys)
        if dropped:
            excluded_per_repo[repo_slug] = dropped
            logger.info(
                '%s: excluded %d PR(s) already reported in a prior release; %d remain',
                repo_slug, dropped, len(pr_numbers),
            )

        if not pr_numbers:
            logger.warning('No PRs found in %s between %s and %s',
                           repo_slug, repo_from_ref, repo_to_ref)
            continue

        reused = [cacheable[(repo_slug, n)] for n in pr_numbers
                  if (repo_slug, n) in cacheable]
        if reused:
            reused_per_repo[repo_slug] = len(reused)
            pr_numbers = [n for n in pr_numbers if (repo_slug, n) not in cacheable]
            logger.info(
                '%s: reused %d label-categorised PR(s) from the previous report; '
                'fetching %d (heuristic and uncategorised PRs are always re-fetched '
                'so newly applied SIG labels are picked up)',
                repo_slug, len(reused), len(pr_numbers),
            )
            all_prs.extend(rederive_pr_fields(pr) for pr in reused)

        if not pr_numbers:
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

    # A previous run's output may still hold PRs that are now excluded. Filter
    # after the merge too, so the exclusion holds regardless of how a PR got in.
    if prior_keys:
        kept = [pr for pr in merged
                if (pr.get('repo', ''), pr.get('number', 0)) not in prior_keys]
        carried_over = len(merged) - len(kept)
        if carried_over:
            logger.info(
                'Excluded %d already-reported PR(s) carried over from the existing JSON',
                carried_over,
            )
        merged = kept

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
        # Backfill for JSON written before schema 5. Derivable from the stored
        # list, so no re-fetch is needed.
        if 'files_truncated' not in pr:
            pr['files_truncated'] = files_possibly_truncated(pr)

    # Feature #2: per-repo merge-base + effective window, computed best-effort.
    merge_bases: dict[str, dict[str, Any]] = {}
    effective_window_start = None
    for repo_slug, rpath in repo_path_map.items():
        mb = extract_merge_base(
            rpath,
            from_ref_map.get(repo_slug, args.from_ref),
            to_ref_map.get(repo_slug, args.to_ref),
        )
        if mb is None:
            continue
        sha, date = mb
        merge_bases[repo_slug] = {'sha': sha, 'committer_date': date}
        if date and (effective_window_start is None or date < effective_window_start):
            effective_window_start = date

    metadata: dict[str, Any] = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'from_ref': args.from_ref,
        'to_ref': args.to_ref,
        'repos': args.repos,
        'repo_paths': {k: str(v) for k, v in repo_path_map.items()},
        'schema_version': SCHEMA_VERSION,
        'tool_version': __version__,
        'pr_count': len(merged),
        'categorization_summary': cat_counts,
        'release_machinery_count': machinery_count,
    }
    # GitHub caps the files connection at FILES_PAGE_SIZE, so a large PR's file
    # list may be partial. That only changes an outcome when the file heuristic
    # actually decided the SIG, which is the subset worth a curator's attention.
    truncated = [f"{pr['repo']}#{pr['number']}" for pr in merged if pr.get('files_truncated')]
    decided_on_partial = [
        f"{pr['repo']}#{pr['number']}" for pr in merged
        if pr.get('files_truncated') and pr.get('categorization_source') == 'heuristic_files'
    ]
    if truncated:
        metadata['file_list_truncated'] = {
            'page_size': FILES_PAGE_SIZE,
            'count': len(truncated),
            'prs': truncated,
            'categorized_from_partial_files': decided_on_partial,
        }
        logger.info('%d PR(s) hit the %d-file page cap; file list may be partial',
                    len(truncated), FILES_PAGE_SIZE)
        if decided_on_partial:
            logger.warning(
                '%d PR(s) were categorised by the file heuristic from a truncated '
                'file list; verify their SIG before publishing: %s',
                len(decided_on_partial), ', '.join(decided_on_partial),
            )

    if reused_per_repo:
        metadata['reused_from_cache'] = {
            'per_repo': reused_per_repo,
            'total': sum(reused_per_repo.values()),
            'policy': 'label-categorised PRs only; all others re-fetched',
        }

    if exclude_sources:
        metadata['excluded_prior_releases'] = {
            'sources': exclude_sources,
            'per_repo': excluded_per_repo,
            'total': sum(excluded_per_repo.values()),
        }
    if any(v != args.from_ref for v in from_ref_map.values()) or \
            any(v != args.to_ref for v in to_ref_map.values()):
        metadata['repo_refs'] = {
            slug: {'from_ref': from_ref_map[slug], 'to_ref': to_ref_map[slug]}
            for slug in args.repos
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
    merged: list[dict[str, Any]],
    repo_path_map: dict[str, pathlib.Path],
    output_json: pathlib.Path,
) -> None:
    """Run the point-release audit when --from-ref is a non-zero point release.
    Writes a sidecar `<output_md_stem>_pointrelease_audit.md` next to the
    markdown output, or next to the JSON if --output-md isn't set yet."""
    parsed = parse_point_release_tag(args.from_ref)
    if parsed is None or parsed[1] == 0:
        return
    audit_per_repo: dict[str, dict[str, Any]] = {}
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
        # Classify against what the report will actually render, using the
        # render flags when this ran as `generate` and render defaults otherwise.
        classification = classify_for_report(
            merged,
            include_uncategorized=getattr(args, 'include_uncategorized', False),
            include_release_machinery=getattr(args, 'include_release_machinery', False),
            # A bundled fix collapsed as a duplicate still reaches the reader,
            # via the bullet for its twin. Counting it as absent would raise
            # "action required" for content that is present, and a checklist
            # that cries wolf stops being read.
            include_duplicates=True,
        )
        present_numbers = {
            number for (repo, number), reason in classification.items()
            if repo == repo_slug and reason is None
        }
        filtered_numbers = {
            number: reason for (repo, number), reason in classification.items()
            if repo == repo_slug and reason is not None
        }
        audit_per_repo[repo_slug] = {
            'containers': containers,
            'present_pr_numbers': present_numbers,
            'filtered_pr_numbers': filtered_numbers,
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

    include_duplicates = getattr(args, 'include_duplicates', False)

    content = render_markdown(
        data['pull_requests'],
        args.release_version,
        include_uncategorized=args.include_uncategorized,
        summary=summary,
        include_release_machinery=include_release_machinery,
        include_duplicates=include_duplicates,
    )

    if not include_duplicates:
        log_duplicate_groups(
            data['pull_requests'],
            include_uncategorized=args.include_uncategorized,
            include_release_machinery=include_release_machinery,
        )

    log_render_coverage(summarize_render_coverage(
        data['pull_requests'],
        include_uncategorized=args.include_uncategorized,
        include_release_machinery=include_release_machinery,
        include_duplicates=include_duplicates,
    ))

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
    # action='extend' so BOTH documented forms accumulate:
    #   --repo-path a=/x b=/y      and      --repo-path a=/x --repo-path b=/y
    # With bare nargs='*' the second form silently kept only the last flag, so
    # the multi-repo example in the README quietly fell back to
    # --default-repo-path for every repo but one.
    parser.add_argument('--repos', nargs='+', action='extend', default=None,
                        help='GitHub repos in owner/repo format (default: o3de/o3de)')
    parser.add_argument('--repo-path', nargs='*', action='extend', default=None,
                        help='Per-repo local clone paths as owner/repo=/path/to/clone '
                             '(repeatable)')
    parser.add_argument('--default-repo-path', default='.',
                        help='Default local clone path for repos without explicit mapping (default: .)')
    parser.add_argument('--repo-from-ref', nargs='*', action='extend', default=None,
                        help='Per-repo override for --from-ref as owner/repo=REF. Use when a '
                             'release tag exists in some repos but not others (o3de/o3de-extras '
                             'is not tagged on every line).')
    parser.add_argument('--repo-to-ref', nargs='*', action='extend', default=None,
                        help='Per-repo override for --to-ref as owner/repo=REF')
    parser.add_argument('--output-json', required=True,
                        help='Output JSON file path')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show which PRs would be fetched (from git log) and exit '
                             'without calling the GitHub API or writing any files')
    parser.add_argument('--reuse-existing', action='store_true',
                        help='Reuse PR data already in --output-json instead of re-fetching '
                             'it. Only PRs categorised by GitHub label are reused; anything '
                             'categorised heuristically or left uncategorised is always '
                             're-fetched, so a SIG label applied since the last run is picked '
                             'up. Derived fields are recomputed for reused PRs.')
    parser.add_argument('--exclude-json', nargs='*', action='extend', default=None,
                        help='Path(s) to prior release report JSON(s). PRs already reported '
                             'there are dropped from this window and never fetched. Needed '
                             'because a release tag on the main line shares only an ancient '
                             'merge-base with development, so the raw window spans two '
                             'cycles. (repeatable)')
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
    parser.add_argument('--include-duplicates', action='store_true',
                        help='Keep every PR sharing a title within a repo. Default: off, which '
                             'renders one bullet per distinct title and logs each collapsed '
                             'group so the choice can be checked.')


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
    if not log_file:
        return
    # --log-file was the only output path that skipped validation, so a typo in
    # a directory name failed late with a bare OSError instead of the same
    # "parent directory does not exist" message every other path gives.
    # Failing to open a log must never abort a run, so this degrades to
    # stderr-only rather than raising.
    try:
        resolved = validate_output_path(pathlib.Path(log_file))
    except ValueError as e:
        logger.error('Invalid --log-file path: %s. Continuing with stderr only.', e)
        return
    try:
        handler = logging.FileHandler(str(resolved), mode='a', encoding='utf-8')
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(handler)
    except OSError as e:
        logger.error('Could not open log file %s: %s. Continuing with stderr only.', resolved, e)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog='release_notes',
        description='Generate O3DE release notes from merged pull requests',
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    add_parser_args(parser)
    args = parser.parse_args()

    _configure_logging(args.verbose, getattr(args, 'log_file', None))

    if getattr(args, 'repos', None) is None:
        args.repos = list(DEFAULT_REPOS)

    return cast(int, args.func(args))


if __name__ == '__main__':
    sys.exit(main())
