#!/usr/bin/env python3
#
# Copyright (c) Contributors to the Open 3D Engine Project.
# For complete copyright and license terms please see the LICENSE at the root of this distribution.
#
# SPDX-License-Identifier: Apache-2.0 OR MIT
#

import json
import logging
import pathlib
import re
import stat
import subprocess
import sys
from unittest import mock

import pytest

import generate_sbom
import release_notes


class TestValidateGitRef:
    def test_valid_tag(self):
        assert release_notes.validate_git_ref('2510.0') == '2510.0'

    def test_valid_branch(self):
        assert release_notes.validate_git_ref('development') == 'development'

    def test_valid_branch_with_slash(self):
        assert release_notes.validate_git_ref('stabilization/26050') == 'stabilization/26050'

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match='length must be'):
            release_notes.validate_git_ref('')

    def test_none_raises(self):
        with pytest.raises(ValueError):
            release_notes.validate_git_ref(None)

    def test_shell_injection_raises(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('; rm -rf /')

    def test_backtick_injection_raises(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('`whoami`')

    def test_flag_like_with_equals_raises(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('--exec=evil')

    def test_flag_like_raises(self):
        with pytest.raises(ValueError, match='must not start with a hyphen'):
            release_notes.validate_git_ref('--all')

    def test_too_long_raises(self):
        with pytest.raises(ValueError, match='length must be'):
            release_notes.validate_git_ref('a' * 257)

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('main branch')

    def test_dollar_sign_rejected(self):
        with pytest.raises(ValueError, match='disallowed characters'):
            release_notes.validate_git_ref('$HOME')


class TestValidateRepoSlug:
    def test_valid_slug(self):
        assert release_notes.validate_repo_slug('o3de/o3de') == 'o3de/o3de'

    def test_valid_slug_with_hyphens(self):
        assert release_notes.validate_repo_slug('nick-s/o3de-extras') == 'nick-s/o3de-extras'

    def test_missing_slash_raises(self):
        with pytest.raises(ValueError, match='owner/repo'):
            release_notes.validate_repo_slug('justarepo')

    def test_too_many_slashes_raises(self):
        with pytest.raises(ValueError, match='owner/repo'):
            release_notes.validate_repo_slug('a/b/c')

    def test_empty_raises(self):
        with pytest.raises(ValueError, match='length must be'):
            release_notes.validate_repo_slug('')

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match='owner/repo'):
            release_notes.validate_repo_slug('my org/my repo')


class TestValidateOutputPath:
    def test_valid_path(self, tmp_path):
        out = tmp_path / 'output.json'
        result = release_notes.validate_output_path(out)
        assert result == out.resolve()

    def test_traversal_detected(self, tmp_path):
        sneaky = tmp_path / '..' / '..' / 'etc' / 'passwd'
        with pytest.raises(ValueError, match='traversal'):
            release_notes.validate_output_path(sneaky, base_dir=tmp_path)

    def test_sibling_directory_rejected(self, tmp_path):
        base = tmp_path / 'safe'
        base.mkdir()
        sibling = tmp_path / 'safe_evil'
        sibling.mkdir()
        target = sibling / 'file.json'
        with pytest.raises(ValueError, match='traversal'):
            release_notes.validate_output_path(target, base_dir=base)

    def test_missing_parent_raises(self, tmp_path):
        bad = tmp_path / 'nonexistent' / 'dir' / 'file.json'
        with pytest.raises(ValueError, match='Parent directory'):
            release_notes.validate_output_path(bad)


class TestExtractPrNumbers:
    def test_extracts_numbers(self, tmp_path):
        git_output = (
            'Fix choppy mouse movement (#19709)\n'
            'Cherry pick fixes from stabilization (#19697)\n'
            'Remove system cmake dependency (#19704)\n'
            'Generic Asset Group (#19678)\n'
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(
                returncode=0,
                stdout=git_output,
                stderr='',
            )
            result = release_notes.extract_pr_numbers_from_git_log(
                tmp_path, '2510.0', 'development'
            )
        assert result == [19678, 19697, 19704, 19709]

    def test_deduplicates(self, tmp_path):
        git_output = 'Same PR (#123)\nSame PR again (#123)\n'
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=git_output, stderr='')
            result = release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert result == [123]

    def test_no_prs_found(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout='no pr refs here\n', stderr='')
            result = release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert result == []

    def test_git_failure_raises(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=128, stdout='', stderr='fatal: bad ref')
            with pytest.raises(RuntimeError, match='git log failed'):
                release_notes.extract_pr_numbers_from_git_log(tmp_path, 'bad', 'ref')

    def test_extracts_merge_commit_prs(self, tmp_path):
        # O3DE `development` uses merge commits for a large minority of PRs.
        # Their number appears only in the merge subject, without parentheses.
        git_output = (
            'Merge pull request #19882 from o3de/imgui-console-input-bug\n'
            'Fixes a bug where the imgui console consumes input events\n'
            'Squash merged thing (#19900)\n'
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=git_output, stderr='')
            result = release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert result == [19882, 19900]

    def test_merge_commits_are_not_excluded_from_git_log(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout='', stderr='')
            release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert '--no-merges' not in mock_run.call_args[0][0]

    def test_merge_pattern_requires_line_start(self, tmp_path):
        # "reverts Merge pull request #1" in prose must not mint a PR number.
        git_output = 'Revert of Merge pull request #123 from someone\n'
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=git_output, stderr='')
            result = release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert result == []

    def test_merge_and_squash_reference_deduplicate(self, tmp_path):
        git_output = (
            'Merge pull request #500 from o3de/thing\n'
            'Thing (#500)\n'
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout=git_output, stderr='')
            result = release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')
        assert result == [500]

    def test_timeout_surfaces_as_runtime_error(self, tmp_path):
        with mock.patch('release_notes.subprocess.run',
                        side_effect=subprocess.TimeoutExpired('git', 60)), \
             pytest.raises(RuntimeError, match='git log'):
            release_notes.extract_pr_numbers_from_git_log(tmp_path, 'a', 'b')


class TestCategorizeByLabels:
    def test_sig_label(self):
        assert release_notes._categorize_by_labels(['sig/build']) == 'sig/build'

    def test_multiple_sig_labels_deterministic(self):
        # Order of labels from GitHub is not guaranteed, so the result must
        # depend only on SIG_CANONICAL_ORDER, not on label-list order.
        result1 = release_notes._categorize_by_labels(['sig/core', 'sig/platform'])
        result2 = release_notes._categorize_by_labels(['sig/platform', 'sig/core'])
        assert result1 == result2 == 'sig/core'

    def test_canonical_order_wins(self):
        # sig/build comes before sig/core in SIG_CANONICAL_ORDER.
        result = release_notes._categorize_by_labels(['sig/core', 'sig/build'])
        assert result == 'sig/build'
        result = release_notes._categorize_by_labels(['sig/build', 'sig/core'])
        assert result == 'sig/build'

    def test_sig_release_deprioritized(self):
        result = release_notes._categorize_by_labels(['sig/release', 'sig/build'])
        assert result == 'sig/build'

    def test_only_sig_release(self):
        assert release_notes._categorize_by_labels(['sig/release']) == 'sig/release'

    def test_no_sig_labels(self):
        assert release_notes._categorize_by_labels(['bug', 'enhancement']) is None

    def test_empty_labels(self):
        assert release_notes._categorize_by_labels([]) is None


class TestCategorizeByTitle:
    @pytest.mark.parametrize('title,expected_sig', [
        ('Fix CMake warning in project build', 'sig/build'),
        ('Fix Vulkan crash on startup', 'sig/graphics-audio'),
        ('Update AzCore allocator', 'sig/core'),
        ('Fix prefab override in inspector', 'sig/content'),
        ('Add PhysX articulation offset', 'sig/simulation'),
        ('Initial Wayland support', 'sig/platform'),
        ('Security: Add bounds check on componentInputCount', 'sig/security'),
        ('Update GoogleTest to always build static', 'sig/testing'),
        ('Fix shader compilation error in Atom', 'sig/graphics-audio'),
        ('Asset Processor dependency fixes', 'sig/content'),
    ])
    def test_keyword_matching(self, title, expected_sig):
        result = release_notes._categorize_by_title(title)
        assert result == expected_sig, f'Expected {expected_sig} for {title!r}, got {result}'

    def test_no_match(self):
        assert release_notes._categorize_by_title('Miscellaneous cleanup') is None

    def test_tie_resolved_by_canonical_order(self):
        # Construct a title that hits exactly one keyword in two different SIG
        # buckets so they tie on count. The result must be the SIG that comes
        # first in SIG_CANONICAL_ORDER, regardless of dict insertion order.
        # 'cmake' → sig/build; 'physx' → sig/simulation.
        # sig/build appears earlier in SIG_CANONICAL_ORDER → wins.
        result = release_notes._categorize_by_title('cmake physx integration')
        assert result == 'sig/build'


class TestCategorizeByFiles:
    def test_azcore_files(self):
        files = ['Code/Framework/AzCore/AzCore/Module/Module.cpp']
        assert release_notes._categorize_by_files(files) == 'sig/core'

    def test_atom_files(self):
        files = ['Gems/Atom/RHI/Vulkan/Code/Source/RHI/Device.cpp']
        assert release_notes._categorize_by_files(files) == 'sig/graphics-audio'

    def test_cmake_files(self):
        files = ['cmake/Platform/Linux/CMakeLists.txt']
        assert release_notes._categorize_by_files(files) == 'sig/build'

    def test_mixed_files_majority_wins(self):
        files = [
            'Gems/Atom/RHI/Code/Source/A.cpp',
            'Gems/Atom/RHI/Code/Source/B.cpp',
            'Code/Framework/AzCore/AzCore/C.cpp',
        ]
        assert release_notes._categorize_by_files(files) == 'sig/graphics-audio'

    def test_no_match(self):
        files = ['some/random/path.txt']
        assert release_notes._categorize_by_files(files) is None

    def test_empty_files(self):
        assert release_notes._categorize_by_files([]) is None


class TestCategorizePriority:
    def test_label_takes_precedence(self):
        pr = {
            'labels': ['sig/core'],
            'title': 'Fix Vulkan crash',
            'files': ['Gems/Atom/RHI/Vulkan/Code/Source/Device.cpp'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'sig/core'
        assert source == 'label'

    def test_title_over_files(self):
        pr = {
            'labels': [],
            'title': 'Fix CMake build error',
            'files': ['Code/Framework/AzCore/AzCore/Module.cpp'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'sig/build'
        assert source == 'heuristic_title'

    def test_files_fallback(self):
        pr = {
            'labels': [],
            'title': 'Miscellaneous fix',
            'files': ['Gems/PhysX/Code/Source/RigidBody.cpp'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'sig/simulation'
        assert source == 'heuristic_files'

    def test_uncategorized_fallback(self):
        pr = {
            'labels': [],
            'title': 'Miscellaneous cleanup',
            'files': ['random/path.txt'],
        }
        sig, source = release_notes.categorize_pr(pr)
        assert sig == 'uncategorized'
        assert source == 'uncategorized'


class TestDetectPrFlags:
    def test_cherry_pick(self):
        pr = {'title': 'Cherry pick fixes from stabilization/26050', 'labels': []}
        assert 'cherry-pick' in release_notes.detect_pr_flags(pr)

    def test_merge_stabilization(self):
        pr = {'title': 'Merge stabilization 26050 to dev', 'labels': []}
        assert 'cherry-pick' in release_notes.detect_pr_flags(pr)

    def test_normal_pr(self):
        pr = {'title': 'Fix a bug in rendering', 'labels': []}
        assert release_notes.detect_pr_flags(pr) == []

    @pytest.mark.parametrize('label', [
        'sync/to-development',
        'sync/to-stabilization',
        'need-sync/to-development',
    ])
    def test_workflow_sync_labels_do_not_flag(self, label):
        # Regression: these labels live on the ORIGINAL substantive PR, not on a
        # sync container. Flagging them dropped 57 real changes (22% of the
        # corpus) from the 26.05.0 release notes.
        pr = {'title': 'Fixes blendshapes ("morph targets") not working', 'labels': [label]}
        assert release_notes.detect_pr_flags(pr) == []

    def test_sync_labelled_pr_still_renders(self):
        pr = {
            'number': 19151, 'repo': 'o3de/o3de', 'url': '',
            'title': 'Fixes blendshapes not working',
            'labels': ['sig/graphics-audio', 'sync/to-stabilization'],
            'sig_category': 'sig/graphics-audio', 'description': 'Fixes blendshapes not working.',
        }
        pr['flags'] = release_notes.detect_pr_flags(pr)
        md = release_notes.render_markdown([pr], '26.10.0')
        assert 'Fixes blendshapes not working' in md

    def test_legacy_sync_flag_in_old_json_no_longer_excludes(self):
        # JSON written by <=0.5.0-beta carries the bad flag. Rendering such a
        # file must not keep dropping the PR; no re-fetch should be required.
        pr = {
            'number': 19151, 'repo': 'o3de/o3de', 'url': '',
            'title': 'Fixes blendshapes not working',
            'sig_category': 'sig/graphics-audio', 'description': 'Fixes blendshapes not working.',
            'flags': ['stabilization-sync'],
        }
        md = release_notes.render_markdown([pr], '26.10.0')
        assert 'Fixes blendshapes not working' in md


class TestSanitizePrTitle:
    def test_removes_trailing_pr_ref(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix bug (#19709)')
        assert result == 'Fix bug.'

    def test_strips_leading_hash(self):
        result = release_notes._sanitize_pr_title_for_markdown('## Fix something')
        assert result == 'Fix something.'

    def test_escapes_brackets(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix [some] issue')
        assert '\\[' in result
        assert '\\]' in result

    def test_escapes_backticks(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix `code` issue')
        assert '\\`' in result

    def test_escapes_pipes(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix A | B issue')
        assert '\\|' in result

    def test_adds_period(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix something')
        assert result.endswith('.')

    def test_no_double_period(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix something.')
        assert not result.endswith('..')


class TestFormatPrReference:
    def test_with_url(self):
        result = release_notes._format_pr_reference('o3de/o3de', 19709, 'https://github.com/o3de/o3de/pull/19709')
        assert result == '[o3de#19709](https://github.com/o3de/o3de/pull/19709)'

    def test_without_url_constructs_link(self):
        result = release_notes._format_pr_reference('o3de/o3de', 19709)
        assert result == '[o3de#19709](https://github.com/o3de/o3de/pull/19709)'

    def test_extras_repo(self):
        result = release_notes._format_pr_reference('o3de/o3de-extras', 1045, 'https://github.com/o3de/o3de-extras/pull/1045')
        assert result == '[o3de-extras#1045](https://github.com/o3de/o3de-extras/pull/1045)'

    def test_fork_without_url(self):
        result = release_notes._format_pr_reference('nickschuetz/o3de', 19709)
        assert result == '[o3de#19709](https://github.com/nickschuetz/o3de/pull/19709)'


class TestBuildGraphqlQuery:
    def test_single_pr(self):
        query = release_notes._build_graphql_query([19709])
        assert 'pr_19709' in query
        assert 'pullRequest(number: 19709)' in query
        assert 'repository(owner: $owner, name: $name)' in query

    def test_multiple_prs(self):
        query = release_notes._build_graphql_query([100, 200, 300])
        assert 'pr_100' in query
        assert 'pr_200' in query
        assert 'pr_300' in query

    def test_includes_required_fields(self):
        query = release_notes._build_graphql_query([1])
        for field in ['number', 'title', 'mergedAt', 'url', 'author', 'labels', 'files']:
            assert field in query

    def test_uses_graphql_variables(self):
        # The owner/name must be GraphQL variables, never string-interpolated.
        query = release_notes._build_graphql_query([1])
        assert 'query($owner: String!, $name: String!)' in query
        # No raw string-interpolated owner/name should appear
        assert 'owner: "' not in query
        assert 'name: "' not in query


class TestRenderMarkdown:
    def _make_pr(self, number, sig, title='Fix something', repo='o3de/o3de', flags=None):
        return {
            'number': number,
            'repo': repo,
            'title': title,
            'sig_category': sig,
            'categorization_source': 'label',
            'description': release_notes._sanitize_pr_title_for_markdown(title),
            'flags': flags or [],
        }

    def test_basic_structure(self):
        prs = [self._make_pr(1, 'sig/build', 'Fix cmake')]
        result = release_notes.render_markdown(prs, '26.05.0')
        assert '# 26.05.0 Release Notes' in result
        assert '## SIG-Build' in result
        assert '[o3de#1](' in result

    def test_sig_ordering(self):
        prs = [
            self._make_pr(1, 'sig/simulation'),
            self._make_pr(2, 'sig/build'),
        ]
        result = release_notes.render_markdown(prs, '1.0')
        build_pos = result.index('SIG-Build')
        sim_pos = result.index('SIG-Simulation')
        assert build_pos < sim_pos

    def test_cherry_picks_filtered(self):
        prs = [
            self._make_pr(1, 'sig/build', 'Fix cmake'),
            self._make_pr(2, 'sig/build', 'Cherry pick fix', flags=['cherry-pick']),
        ]
        result = release_notes.render_markdown(prs, '1.0')
        assert '[o3de#1](' in result
        assert '[o3de#2](' not in result

    def test_uncategorized_hidden_by_default(self):
        prs = [self._make_pr(1, 'uncategorized')]
        result = release_notes.render_markdown(prs, '1.0')
        assert 'Uncategorized' not in result

    def test_uncategorized_shown_when_requested(self):
        prs = [self._make_pr(1, 'uncategorized')]
        result = release_notes.render_markdown(prs, '1.0', include_uncategorized=True)
        assert '## Uncategorized' in result

    def test_empty_sigs_omitted(self):
        prs = [self._make_pr(1, 'sig/build')]
        result = release_notes.render_markdown(prs, '1.0')
        assert 'SIG-Network' not in result


class TestMergeWithExisting:
    def test_no_existing(self):
        new = [{'number': 1, 'repo': 'o3de/o3de', 'sig_category': 'sig/build'}]
        result = release_notes.merge_with_existing(new, None)
        assert result == new

    def test_preserves_manual_override_sig(self, tmp_path):
        existing = {
            'metadata': {'schema_version': release_notes.SCHEMA_VERSION - 1},
            'pull_requests': [{
                'number': 1,
                'repo': 'o3de/o3de',
                'sig_category': 'sig/core',
                'manual_override_sig': 'sig/core',
                'manual_override_description': None,
            }],
        }
        json_path = tmp_path / 'existing.json'
        json_path.write_text(json.dumps(existing))

        new = [{'number': 1, 'repo': 'o3de/o3de', 'sig_category': 'sig/build'}]
        result = release_notes.merge_with_existing(new, json_path)
        assert result[0]['sig_category'] == 'sig/core'
        assert result[0]['categorization_source'] == 'manual_override'

    def test_preserves_manual_override_description(self, tmp_path):
        existing = {
            'metadata': {'schema_version': release_notes.SCHEMA_VERSION - 1},
            'pull_requests': [{
                'number': 1,
                'repo': 'o3de/o3de',
                'description': 'Custom description.',
                'manual_override_sig': None,
                'manual_override_description': 'Custom description.',
            }],
        }
        json_path = tmp_path / 'existing.json'
        json_path.write_text(json.dumps(existing))

        new = [{'number': 1, 'repo': 'o3de/o3de', 'description': 'Auto description.'}]
        result = release_notes.merge_with_existing(new, json_path)
        assert result[0]['description'] == 'Custom description.'

    def test_adds_new_prs(self, tmp_path):
        existing = {
            'metadata': {'schema_version': release_notes.SCHEMA_VERSION - 1},
            'pull_requests': [{
                'number': 1, 'repo': 'o3de/o3de',
                'manual_override_sig': None, 'manual_override_description': None,
            }],
        }
        json_path = tmp_path / 'existing.json'
        json_path.write_text(json.dumps(existing))

        new = [
            {'number': 1, 'repo': 'o3de/o3de'},
            {'number': 2, 'repo': 'o3de/o3de'},
        ]
        result = release_notes.merge_with_existing(new, json_path)
        numbers = [p['number'] for p in result]
        assert 1 in numbers
        assert 2 in numbers


class TestAtomicWrite:
    def test_write_json(self, tmp_path):
        data = {'test': True}
        out = tmp_path / 'test.json'
        release_notes.write_json_atomic(data, out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded == {'test': True}

    def test_write_markdown(self, tmp_path):
        content = '# Test\nHello world\n'
        out = tmp_path / 'test.md'
        release_notes.write_markdown_atomic(content, out)
        assert out.exists()
        assert out.read_text() == content

    def test_overwrites_existing(self, tmp_path):
        out = tmp_path / 'test.json'
        out.write_text('{"old": true}')
        release_notes.write_json_atomic({'new': True}, out)
        loaded = json.loads(out.read_text())
        assert loaded == {'new': True}


class TestLoadExistingJson:
    def test_valid_file(self, tmp_path):
        data = {'metadata': {'schema_version': release_notes.SCHEMA_VERSION}, 'pull_requests': []}
        path = tmp_path / 'data.json'
        path.write_text(json.dumps(data))
        result = release_notes.load_existing_json(path)
        assert result is not None
        assert result['pull_requests'] == []

    def test_previous_schema_version_accepted(self, tmp_path):
        data = {'metadata': {'schema_version': release_notes.SCHEMA_VERSION - 1}, 'pull_requests': []}
        path = tmp_path / 'data.json'
        path.write_text(json.dumps(data))
        result = release_notes.load_existing_json(path)
        assert result is not None

    def test_missing_file(self, tmp_path):
        result = release_notes.load_existing_json(tmp_path / 'missing.json')
        assert result is None

    def test_corrupt_json(self, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{not valid json')
        result = release_notes.load_existing_json(path)
        assert result is None

    def test_wrong_schema_version(self, tmp_path):
        data = {'metadata': {'schema_version': 999}, 'pull_requests': []}
        path = tmp_path / 'data.json'
        path.write_text(json.dumps(data))
        result = release_notes.load_existing_json(path)
        assert result is None

    def test_missing_pull_requests_key(self, tmp_path):
        path = tmp_path / 'data.json'
        path.write_text('{"metadata": {}}')
        result = release_notes.load_existing_json(path)
        assert result is None


class TestParseRepoPathMappings:
    def test_default_path_for_all_repos(self):
        result = release_notes.parse_repo_path_mappings(
            None, '/default', ['o3de/o3de', 'o3de/o3de-extras']
        )
        assert result['o3de/o3de'] == pathlib.Path('/default').resolve()
        assert result['o3de/o3de-extras'] == pathlib.Path('/default').resolve()

    def test_explicit_mapping(self):
        result = release_notes.parse_repo_path_mappings(
            ['o3de/o3de-extras=/home/user/extras'],
            '/default',
            ['o3de/o3de', 'o3de/o3de-extras'],
        )
        assert result['o3de/o3de'] == pathlib.Path('/default').resolve()
        assert result['o3de/o3de-extras'] == pathlib.Path('/home/user/extras').resolve()

    def test_all_explicit(self):
        result = release_notes.parse_repo_path_mappings(
            ['o3de/o3de=/a', 'o3de/o3de-extras=/b'],
            '/default',
            ['o3de/o3de', 'o3de/o3de-extras'],
        )
        assert result['o3de/o3de'] == pathlib.Path('/a').resolve()
        assert result['o3de/o3de-extras'] == pathlib.Path('/b').resolve()

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match='Invalid --repo-path mapping'):
            release_notes.parse_repo_path_mappings(
                ['not-a-valid-mapping'],
                '/default',
                ['o3de/o3de'],
            )

    def test_empty_repo_paths(self):
        result = release_notes.parse_repo_path_mappings(
            [], '/default', ['o3de/o3de']
        )
        assert result['o3de/o3de'] == pathlib.Path('/default').resolve()


class TestBuildSummaryPrompt:
    def test_includes_version(self):
        prs = [{'title': 'Fix bug', 'sig_category': 'sig/build', 'flags': []}]
        prompt = release_notes._build_summary_prompt(prs, '26.05.0')
        assert '26.05.0' in prompt

    def test_includes_sig_groups(self):
        prs = [
            {'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []},
            {'title': 'Fix vulkan', 'sig_category': 'sig/graphics-audio', 'flags': []},
        ]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert 'SIG-Build' in prompt
        assert 'SIG-Graphics-Audio' in prompt

    def test_excludes_cherry_picks(self):
        prs = [
            {'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []},
            {'title': 'Cherry pick', 'sig_category': 'sig/build', 'flags': ['cherry-pick']},
        ]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert 'Fix cmake' in prompt
        assert 'Cherry pick' not in prompt

    def test_excludes_uncategorized(self):
        prs = [
            {'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []},
            {'title': 'Unknown', 'sig_category': 'uncategorized', 'flags': []},
        ]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert 'Fix cmake' in prompt
        assert 'Unknown' not in prompt

    def test_truncates_long_sig(self):
        prs = [{'title': f'PR {i}', 'sig_category': 'sig/build', 'flags': []} for i in range(20)]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert '... and 5 more' in prompt

    def test_with_hint(self):
        prs = [{'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []}]
        prompt = release_notes._build_summary_prompt(prs, '1.0', hint='Focus on build improvements')
        assert 'Focus on build improvements' in prompt
        assert 'Additional guidance' in prompt

    def test_without_hint(self):
        prs = [{'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []}]
        prompt = release_notes._build_summary_prompt(prs, '1.0')
        assert 'Additional guidance' not in prompt

    def test_empty_hint_ignored(self):
        prs = [{'title': 'Fix cmake', 'sig_category': 'sig/build', 'flags': []}]
        prompt = release_notes._build_summary_prompt(prs, '1.0', hint='')
        assert 'Additional guidance' not in prompt


class TestResolveHint:
    def test_inline_text(self):
        assert release_notes._resolve_hint('Focus on platform changes') == 'Focus on platform changes'

    def test_empty_string(self):
        assert release_notes._resolve_hint('') == ''

    def test_file_reference(self, tmp_path):
        hint_file = tmp_path / 'hint.txt'
        hint_file.write_text('Emphasize Wayland and ARM64 support.', encoding='utf-8')
        result = release_notes._resolve_hint(f'@{hint_file}')
        assert result == 'Emphasize Wayland and ARM64 support.'

    def test_file_not_found(self, tmp_path):
        result = release_notes._resolve_hint(f'@{tmp_path}/nonexistent.txt')
        assert result == ''

    def test_file_with_whitespace(self, tmp_path):
        hint_file = tmp_path / 'hint.txt'
        hint_file.write_text('\n  Focus on breaking changes.  \n', encoding='utf-8')
        result = release_notes._resolve_hint(f'@{hint_file}')
        assert result == 'Focus on breaking changes.'


class TestPrNumberValidation:
    def test_valid_pr_numbers(self):
        with mock.patch('release_notes._run_gh_command') as mock_cmd:
            mock_cmd.return_value = {'data': {'repository': {}}}
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [1, 100, 99999])

    def test_zero_pr_number_raises(self):
        with pytest.raises(ValueError, match='Invalid PR number'):
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [0])

    def test_negative_pr_number_raises(self):
        with pytest.raises(ValueError, match='Invalid PR number'):
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [-1])

    def test_huge_pr_number_raises(self):
        with pytest.raises(ValueError, match='Invalid PR number'):
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [9999999])

    def test_empty_list_returns_empty(self):
        result = release_notes.fetch_pr_metadata_batch('o3de/o3de', [])
        assert result == []

    def test_invalid_batch_size_raises(self):
        with pytest.raises(ValueError, match='batch_size'):
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [1], batch_size=0)

    def test_batch_size_over_100_raises(self):
        with pytest.raises(ValueError, match='batch_size'):
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [1], batch_size=101)


class TestSanitizeEdgeCases:
    def test_unicode_emoji(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix bug 🐛 in renderer')
        assert '🐛' in result
        assert result.endswith('.')

    def test_very_long_title(self):
        long_title = 'Fix ' + 'a' * 2000
        result = release_notes._sanitize_pr_title_for_markdown(long_title)
        assert isinstance(result, str)
        assert len(result) > 2000

    def test_only_whitespace(self):
        result = release_notes._sanitize_pr_title_for_markdown('   ')
        assert result == ''

    def test_empty_string(self):
        result = release_notes._sanitize_pr_title_for_markdown('')
        assert result == ''


class TestBuildPrDescription:
    def test_no_body_uses_title(self):
        result = release_notes._build_pr_description('Fix a bug', '')
        assert result == 'Fix a bug.'

    def test_body_with_good_first_paragraph(self):
        body = 'This change fixes the camera rotation issue when using high DPI displays.'
        result = release_notes._build_pr_description('Fix camera rotation', body)
        assert 'camera rotation' in result.lower()
        assert 'high DPI' in result

    def test_body_skips_template_headers(self):
        body = '## What does this PR do?\n\nFixes the editor crash on startup.\n\n## How was this tested?\nManually.'
        result = release_notes._build_pr_description('Fix editor crash', body)
        assert 'editor crash' in result.lower()

    def test_body_skips_checklists(self):
        body = '- [x] Tests pass\n- [ ] Docs updated\n\nThis improves build performance by 20%.'
        result = release_notes._build_pr_description('Improve build', body)
        assert 'build performance' in result.lower()

    def test_body_too_short_uses_title(self):
        body = 'Fix.'
        result = release_notes._build_pr_description('Fix rendering bug in Atom', body)
        assert result == 'Fix rendering bug in Atom.'

    def test_body_too_long_uses_title(self):
        body = 'A' * 500
        result = release_notes._build_pr_description('Long PR', body)
        assert result == 'Long PR.'

    def test_empty_body_and_title(self):
        result = release_notes._build_pr_description('', '')
        assert result == ''

    def test_bullet_list_body_uses_title(self):
        body = '- Fixed widget A\n- Updated component B\n- Removed legacy C'
        result = release_notes._build_pr_description('Editor improvements', body)
        assert result == 'Editor improvements.'

    def test_image_in_body_skipped(self):
        body = '![screenshot](http://example.com/img.png)\n\nThis fixes the layout.'
        result = release_notes._build_pr_description('Fix layout', body)
        assert 'layout' in result.lower()
        assert '![' not in result

    def test_unrelated_body_combines_with_title(self):
        body = 'The previous implementation had a race condition in the event loop.'
        result = release_notes._build_pr_description('Fix crash on startup', body)
        assert 'crash on startup' in result.lower()
        assert 'race condition' in result.lower()

    def test_related_body_replaces_title(self):
        body = 'Fix the crash on startup caused by a null pointer in the initialization code.'
        result = release_notes._build_pr_description('Fix crash on startup', body)
        assert 'null pointer' in result.lower()


class TestExtractFirstParagraph:
    def test_simple_paragraph(self):
        body = 'This is the first paragraph.\n\nThis is the second.'
        assert release_notes._extract_first_paragraph(body) == 'This is the first paragraph.'

    def test_skips_markdown_headers(self):
        body = '## Summary\n\nActual content here.'
        assert release_notes._extract_first_paragraph(body) == 'Actual content here.'

    def test_skips_html_comments(self):
        body = '<!-- comment -->\nReal content.'
        assert release_notes._extract_first_paragraph(body) == 'Real content.'

    def test_multiline_paragraph(self):
        body = 'Line one of the paragraph.\nLine two continues.\n\nNext paragraph.'
        result = release_notes._extract_first_paragraph(body)
        assert 'Line one' in result
        assert 'Line two' in result

    def test_all_noise(self):
        body = '## What\n- [x] Done\n---\n'
        assert release_notes._extract_first_paragraph(body) == ''

    def test_bullet_list_returns_empty(self):
        body = '- Item one\n- Item two\n- Item three'
        assert release_notes._extract_first_paragraph(body) == ''

    def test_skips_images(self):
        body = '![alt text](http://img.png)\n<img src="foo.png">\n\nReal content here.'
        assert release_notes._extract_first_paragraph(body) == 'Real content here.'


class TestRos2Categorization:
    def test_ros2_files_categorized_as_simulation(self):
        files = ['Gems/ROS2/Code/Source/SomeFile.cpp']
        assert release_notes._categorize_by_files(files) == 'sig/simulation'

    def test_ros2_title_keyword(self):
        assert release_notes._categorize_by_title('ROS2 sensor fix') == 'sig/simulation'

    def test_ros2_controllers_files(self):
        files = ['Gems/ROS2Controllers/Code/Source/Gripper.cpp']
        assert release_notes._categorize_by_files(files) == 'sig/simulation'


class TestStripAnsi:
    def test_strips_escape_codes(self):
        dirty = 'Hello\x1b[6D\x1b[K world\x1b[?25h'
        assert release_notes._strip_ansi(dirty) == 'Hello world'

    def test_clean_passthrough(self):
        assert release_notes._strip_ansi('No escapes here.') == 'No escapes here.'

    def test_empty_string(self):
        assert release_notes._strip_ansi('') == ''


class TestGenerateSummary:
    def test_success(self):
        with (
            mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'),
            mock.patch('release_notes.subprocess.run') as mock_run,
        ):
            mock_run.return_value = mock.Mock(
                returncode=0,
                stdout='This release is great.',
                stderr='',
            )
            result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result == 'This release is great.'

    def test_command_not_found(self):
        with mock.patch('release_notes.shutil.which', return_value=None):
            result = release_notes.generate_summary([], '1.0', 'nonexistent')
        assert result is None

    def test_command_failure(self):
        with (
            mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'),
            mock.patch('release_notes.subprocess.run') as mock_run,
        ):
            mock_run.return_value = mock.Mock(returncode=1, stdout='', stderr='error')
            result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None

    def test_timeout(self):
        with (
            mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'),
            mock.patch('release_notes.subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 120)),
        ):
            result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None

    def test_empty_output(self):
        with (
            mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'),
            mock.patch('release_notes.subprocess.run') as mock_run,
        ):
            mock_run.return_value = mock.Mock(returncode=0, stdout='', stderr='')
            result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None


class TestRenderMarkdownWithSummary:
    def _make_pr(self, number, sig, title='Fix something'):
        return {
            'number': number, 'repo': 'o3de/o3de', 'title': title,
            'sig_category': sig, 'categorization_source': 'label',
            'description': release_notes._sanitize_pr_title_for_markdown(title),
            'flags': [],
        }

    def test_with_summary(self):
        prs = [self._make_pr(1, 'sig/build')]
        result = release_notes.render_markdown(prs, '1.0', summary='Great release.')
        assert 'Great release.' in result
        assert 'TODO' not in result

    def test_without_summary(self):
        prs = [self._make_pr(1, 'sig/build')]
        result = release_notes.render_markdown(prs, '1.0')
        assert 'TODO' in result


class TestSafeStderrRedaction:
    def test_redacts_gh_personal_token(self):
        msg = 'fatal: bad credential ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        result = release_notes._safe_stderr(msg)
        assert 'ghp_' not in result
        assert '<redacted-token>' in result

    def test_redacts_gh_oauth_token(self):
        msg = 'auth failed: gho_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
        result = release_notes._safe_stderr(msg)
        assert 'gho_' not in result
        assert '<redacted-token>' in result

    def test_passthrough_for_normal_errors(self):
        result = release_notes._safe_stderr('git log: bad ref foo')
        assert 'bad ref foo' in result

    def test_truncates_to_max_length(self):
        msg = 'a' * 1000
        result = release_notes._safe_stderr(msg)
        assert len(result) <= release_notes.MAX_STDERR_LOG_LEN


class TestPrBodySizeCap:
    def test_huge_body_does_not_explode(self):
        # 1MB body,should be capped before regex processing.
        body = 'a' * (1024 * 1024)
        result = release_notes._build_pr_description('Fix bug', body)
        assert isinstance(result, str)
        # Falls back to title because the giant body has no paragraph
        # structure to extract.
        assert 'Fix bug' in result


class TestMergeWithExistingDropWarning:
    def test_warns_when_dropping_pr_without_overrides(self, tmp_path, caplog):
        existing = {
            'metadata': {'schema_version': release_notes.SCHEMA_VERSION},
            'pull_requests': [{
                'number': 99,
                'repo': 'o3de/o3de',
                'sig_category': 'sig/core',
                'manual_override_sig': None,
                'manual_override_description': None,
            }],
        }
        json_path = tmp_path / 'existing.json'
        json_path.write_text(json.dumps(existing))

        # PR 99 is no longer in `new`; without override it should be dropped
        # AND logged as a warning.
        new = [{'number': 1, 'repo': 'o3de/o3de'}]
        with caplog.at_level('WARNING', logger='o3de.release_notes'):
            result = release_notes.merge_with_existing(new, json_path)
        numbers = [p['number'] for p in result]
        assert 99 not in numbers
        assert any('Dropped' in rec.message for rec in caplog.records)


class TestSummaryTimeoutValidation:
    def test_rejects_too_low(self):
        with mock.patch('release_notes.shutil.which', return_value='/x/y'):
            result = release_notes.generate_summary([], '1.0', 'x', timeout=0)
        assert result is None

    def test_rejects_too_high(self):
        with mock.patch('release_notes.shutil.which', return_value='/x/y'):
            result = release_notes.generate_summary([], '1.0', 'x', timeout=99999)
        assert result is None

    def test_accepts_valid(self):
        with (
            mock.patch('release_notes.shutil.which', return_value='/x/y'),
            mock.patch('release_notes.subprocess.run') as mock_run,
        ):
            mock_run.return_value = mock.Mock(returncode=0, stdout='ok', stderr='')
            result = release_notes.generate_summary([], '1.0', 'x', timeout=60)
        assert result == 'ok'

    def test_passes_timeout_to_subprocess(self):
        with (
            mock.patch('release_notes.shutil.which', return_value='/x/y'),
            mock.patch('release_notes.subprocess.run') as mock_run,
        ):
            mock_run.return_value = mock.Mock(returncode=0, stdout='ok', stderr='')
            release_notes.generate_summary([], '1.0', 'x', timeout=42)
            kwargs = mock_run.call_args.kwargs
            assert kwargs['timeout'] == 42


class TestDryRun:
    def test_dry_run_does_not_call_gh_or_write(self, tmp_path):
        # Set up a fake git repo so the .git existence check passes.
        repo_dir = tmp_path / 'repo'
        repo_dir.mkdir()
        (repo_dir / '.git').mkdir()
        out_json = tmp_path / 'out.json'

        args = mock.Mock(
            from_ref='a',
            to_ref='b',
            repos=['o3de/o3de'],
            repo_path=None,
            repo_from_ref=None,
            repo_to_ref=None,
            exclude_json=None,
            default_repo_path=str(repo_dir),
            output_json=str(out_json),
            dry_run=True,
        )
        with (
            mock.patch('release_notes._check_gh_available') as mock_check,
            mock.patch('release_notes.subprocess.run') as mock_run,
        ):
            # git log returns one PR.
            mock_run.return_value = mock.Mock(
                returncode=0,
                stdout='Fix bug (#42)\n',
                stderr='',
            )
            rc = release_notes._run_fetch(args)
        assert rc == 0
        # gh availability never checked in dry-run.
        mock_check.assert_not_called()
        # Output file never written.
        assert not out_json.exists()


class TestCleanSummary:
    def test_strips_preamble(self):
        text = "Here's the release summary:\nActual content here."
        assert release_notes._clean_summary(text) == 'Actual content here.'

    def test_strips_postamble(self):
        text = "Actual content.\nThis summary covers the key changes."
        assert release_notes._clean_summary(text) == 'Actual content.'

    def test_strips_dividers(self):
        text = "---\nContent\n---"
        assert release_notes._clean_summary(text) == 'Content'

    def test_strips_empty_lines(self):
        text = "\n\n\nContent\n\n\n"
        assert release_notes._clean_summary(text) == 'Content'

    def test_combined_cleanup(self):
        text = "---\n\nHere is the summary:\nParagraph one.\n\nParagraph two.\n---\nI followed your instructions."
        result = release_notes._clean_summary(text)
        assert result == 'Paragraph one.\n\nParagraph two.'

    def test_empty_input(self):
        assert release_notes._clean_summary('') == ''

    def test_only_preamble(self):
        text = "Here is a summary of the release:"
        assert release_notes._clean_summary(text) == ''

    def test_content_preserved(self):
        text = "The 26.05.0 release brings major improvements."
        assert release_notes._clean_summary(text) == text


class TestRunGhCommandJsonError:
    def test_non_json_output_raises_runtime_error(self):
        mock_result = mock.Mock(returncode=0, stdout='not json', stderr='')
        with mock.patch('release_notes.subprocess.run', return_value=mock_result), \
             pytest.raises(RuntimeError, match='non-JSON'):
            release_notes._run_gh_command(['gh', 'api', 'test'])

    def test_rate_limit_error(self):
        mock_result = mock.Mock(returncode=1, stdout='', stderr='rate limit exceeded')
        with mock.patch('release_notes.subprocess.run', return_value=mock_result), \
             pytest.raises(RuntimeError, match='exit code 1'):
            release_notes._run_gh_command(['gh', 'api', 'test'])


class TestCategorizeByFilesTiebreaker:
    def test_tied_sigs_use_canonical_order(self):
        files = [
            'Code/Framework/AzCore/test.cpp',
            'Gems/Atom/RPI/Code/shader.cpp',
        ]
        result = release_notes._categorize_by_files(files)
        assert result is not None
        idx = release_notes.SIG_CANONICAL_ORDER.index(result)
        alt_sigs = set()
        for fpath in files:
            for sig, patterns in release_notes.SIG_FILE_PATH_PATTERNS.items():
                for pattern in patterns:
                    if fpath.startswith(pattern):
                        alt_sigs.add(sig)
        for alt in alt_sigs:
            alt_idx = release_notes.SIG_CANONICAL_ORDER.index(alt)
            assert idx <= alt_idx


class TestNormalizePrDataTruncation:
    def test_missing_number_defaults_to_zero(self):
        raw = {'title': 'Test', 'files': {'nodes': []}}
        result = release_notes._normalize_pr_data(raw, 'o3de/o3de')
        assert result['number'] == 0

    def test_100_files_logs_warning(self):
        nodes = [{'path': f'file{i}.cpp'} for i in range(100)]
        raw = {'number': 42, 'files': {'nodes': nodes}}
        with mock.patch('release_notes.logger') as mock_logger:
            release_notes._normalize_pr_data(raw, 'o3de/o3de')
            mock_logger.warning.assert_called_once()
            # The bound is interpolated from FILES_PAGE_SIZE, not hardcoded.
            args = mock_logger.warning.call_args[0]
            assert '%d+ changed files' in args[0]
            assert release_notes.FILES_PAGE_SIZE in args


class TestSchemaVersion:
    def test_schema_version_is_6(self):
        # 5 -> 6 when metadata.reused_from_cache was added. Schema 5 files still
        # load (load_existing_json accepts SCHEMA_VERSION and SCHEMA_VERSION - 1).
        assert release_notes.SCHEMA_VERSION == 6

    def test_metadata_records_tool_version(self):
        assert release_notes.__version__.endswith('-beta')

    def test_version_is_consistent_across_the_project(self):
        # The version lives in four places that must be bumped together:
        # release_notes.__version__, generate_sbom.PROJECT_VERSION,
        # pyproject.toml, and the README's JSON example. Hardcoding the literal
        # here only forced an edit per bump without checking the thing that can
        # actually go wrong, which is the four drifting apart.
        import generate_sbom

        root = pathlib.Path(__file__).resolve().parent.parent
        pyproject = root / 'pyproject.toml'
        match = re.search(r'^version = "([^"]+)"', pyproject.read_text(encoding='utf-8'),
                          re.M)
        assert match is not None, 'pyproject.toml has no version line'

        readme = (root / 'README.md').read_text(encoding='utf-8')
        readme_versions = set(re.findall(r'"tool_version":\s*"([^"]+)"', readme))

        assert release_notes.__version__ == generate_sbom.PROJECT_VERSION
        assert match.group(1) == release_notes.__version__
        assert readme_versions == {release_notes.__version__}


class TestParsePointReleaseTag:
    def test_major_zero(self):
        assert release_notes.parse_point_release_tag('2510.0') == (2510, 0)

    def test_point_release(self):
        assert release_notes.parse_point_release_tag('2510.2') == (2510, 2)

    def test_future_year(self):
        assert release_notes.parse_point_release_tag('2605.1') == (2605, 1)

    def test_empty_returns_none(self):
        assert release_notes.parse_point_release_tag('') is None

    def test_none_input_returns_none(self):
        assert release_notes.parse_point_release_tag(None) is None

    def test_branch_name_returns_none(self):
        assert release_notes.parse_point_release_tag('origin/main') is None

    def test_semver_with_three_parts_returns_none(self):
        # 26.05.0 is the release_version string, not a git tag; we use 2605.0 as
        # the tag in the o3de repos.
        assert release_notes.parse_point_release_tag('26.05.0') is None

    def test_text_returns_none(self):
        assert release_notes.parse_point_release_tag('development') is None

    def test_whitespace_stripped(self):
        assert release_notes.parse_point_release_tag('  2510.1  ') == (2510, 1)


class TestFindSiblingPointReleaseTags:
    def test_returns_sorted_siblings(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout='2510.2\n2510.0\n2510.1\n',
                stderr='',
            )
            result = release_notes.find_sibling_point_release_tags(tmp_path, '2510.1')
            assert result == ['2510.0', '2510.1', '2510.2']

    def test_non_point_release_ref_returns_empty(self, tmp_path):
        # No git calls expected,function returns early.
        with mock.patch('release_notes.subprocess.run') as mock_run:
            result = release_notes.find_sibling_point_release_tags(tmp_path, 'development')
            assert result == []
            mock_run.assert_not_called()

    def test_git_failure_returns_empty(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=128, stdout='', stderr='boom')
            assert release_notes.find_sibling_point_release_tags(tmp_path, '2510.0') == []

    def test_filters_non_matching_tags(self, tmp_path):
        # git tag -l '2510.*' can return tags like '2510.0-beta' that don't
        # parse as point releases; those should be dropped.
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(
                returncode=0,
                stdout='2510.0\n2510.0-beta\n2510.foo\n2510.1\n',
                stderr='',
            )
            result = release_notes.find_sibling_point_release_tags(tmp_path, '2510.0')
            assert result == ['2510.0', '2510.1']


class TestExtractMergeBase:
    def test_returns_sha_and_date(self, tmp_path):
        def fake_run(cmd, **kwargs):
            if cmd[1] == 'merge-base':
                return mock.MagicMock(returncode=0, stdout='abc123def456\n', stderr='')
            if cmd[1] == 'show':
                return mock.MagicMock(returncode=0, stdout='2025-07-31T18:42:11+00:00\n', stderr='')
            raise AssertionError(f'unexpected cmd: {cmd}')

        with mock.patch('release_notes.subprocess.run', side_effect=fake_run):
            result = release_notes.extract_merge_base(tmp_path, '2510.2', 'origin/stabilization/26050')
            assert result == ('abc123def456', '2025-07-31T18:42:11+00:00')

    def test_merge_base_failure_returns_none(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=128, stdout='', stderr='no merge base')
            assert release_notes.extract_merge_base(tmp_path, '2510.0', 'main') is None

    def test_show_failure_still_returns_sha(self, tmp_path):
        def fake_run(cmd, **kwargs):
            if cmd[1] == 'merge-base':
                return mock.MagicMock(returncode=0, stdout='abc123\n', stderr='')
            return mock.MagicMock(returncode=1, stdout='', stderr='')

        with mock.patch('release_notes.subprocess.run', side_effect=fake_run):
            result = release_notes.extract_merge_base(tmp_path, '2510.2', 'main')
            assert result == ('abc123', '')

    def test_invalid_ref_raises(self, tmp_path):
        with pytest.raises(ValueError):
            release_notes.extract_merge_base(tmp_path, '; rm -rf /', 'main')


class TestExtractPointreleaseContainers:
    def _make_git_log_output(self, *commits):
        sep = '@@CONTAINER_BOUNDARY@@\n'
        out = ''
        for sha, subject, body in commits:
            out += f'{sha}\n{subject}\n{body}\n{sep}'
        return out

    def test_finds_container_with_bundled_prs(self, tmp_path):
        out = self._make_git_log_output(
            ('abc123', 'Cherry pick fixes for point release from dev (#19506)',
             'Bundled fixes:\n* Fix VS detection (#19450)\n* Add seed list (#19418)\n'),
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=out, stderr='')
            containers = release_notes.extract_pointrelease_containers(
                tmp_path, '2510.0', '2510.2',
            )
        assert len(containers) == 1
        c = containers[0]
        assert c['container_pr'] == 19506
        assert c['title'].startswith('Cherry pick fixes')
        assert c['bundled_prs'] == [19418, 19450]

    def test_skips_non_container_commits(self, tmp_path):
        out = self._make_git_log_output(
            ('aaa', 'Update version in engine.json for 25.10.2 (#19511)', ''),
            ('bbb', 'Cherrypick fixes from dev to pointrelease 25101 (#19392)',
             'Cherry-picked PRs:\n- (#19300)\n- (#19301)\n'),
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=out, stderr='')
            containers = release_notes.extract_pointrelease_containers(
                tmp_path, '2510.0', '2510.1',
            )
        # #19511 (Update version) is not a container; #19392 IS.
        assert len(containers) == 1
        assert containers[0]['container_pr'] == 19392
        assert containers[0]['bundled_prs'] == [19300, 19301]

    def test_excludes_self_reference_from_bundled(self, tmp_path):
        # The container PR's own number (e.g. (#19506)) sometimes also appears
        # in the body. It must not be listed as a bundled PR.
        out = self._make_git_log_output(
            ('abc', 'Cherry pick from dev (#19506)',
             'Cherry-picks consolidated in (#19506):\n* (#19450)\n'),
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout=out, stderr='')
            containers = release_notes.extract_pointrelease_containers(
                tmp_path, '2510.0', '2510.2',
            )
        assert containers[0]['container_pr'] == 19506
        assert 19506 not in containers[0]['bundled_prs']
        assert containers[0]['bundled_prs'] == [19450]

    def test_empty_log_returns_empty(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout='', stderr='')
            assert release_notes.extract_pointrelease_containers(
                tmp_path, '2510.0', '2510.0',
            ) == []

    def test_git_failure_returns_empty(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=128, stdout='', stderr='bad ref')
            assert release_notes.extract_pointrelease_containers(
                tmp_path, '2510.0', '2510.2',
            ) == []


class TestWritePointreleaseAudit:
    def test_sidecar_format(self, tmp_path):
        audit_data = {
            'from_ref': '2510.2',
            'to_ref': 'origin/stabilization/26050',
            'predecessor_tag': '2510.0',
            'per_repo': {
                'o3de/o3de': {
                    'containers': [
                        {
                            'container_pr': 19506,
                            'container_sha': 'abc',
                            'title': 'Cherry pick fixes for point release from dev (#19506)',
                            'bundled_prs': [19418, 19450],
                        },
                    ],
                    'present_pr_numbers': {19418, 19450},
                    'predecessor_tag': '2510.0',
                },
                'o3de/o3de-extras': {
                    'containers': [],
                    'present_pr_numbers': set(),
                    'predecessor_tag': '2510.0',
                },
            },
        }
        out_path = tmp_path / 'audit.md'
        release_notes.write_pointrelease_audit(audit_data, out_path)
        content = out_path.read_text()
        assert 'Point-release audit for origin/stabilization/26050' in content
        assert '`2510.0`' in content and '`2510.2`' in content
        assert '#19506' in content
        assert '✓ #19418' in content
        assert '✓ #19450' in content
        assert '_No cherry-pick containers found in this repo._' in content
        assert '1 container(s) checked' in content
        assert '2 bundled PR reference(s) parsed' in content
        assert '2 rendered' in content

    def test_missing_bundled_pr_flagged(self, tmp_path):
        audit_data = {
            'from_ref': '2510.2',
            'to_ref': 'main',
            'predecessor_tag': '2510.0',
            'per_repo': {
                'o3de/o3de': {
                    'containers': [
                        {
                            'container_pr': 19506,
                            'container_sha': 'abc',
                            'title': 'Cherry pick fixes (#19506)',
                            'bundled_prs': [19418, 19999],  # 19999 is missing
                        },
                    ],
                    'present_pr_numbers': {19418},
                    'predecessor_tag': '2510.0',
                },
            },
        }
        out_path = tmp_path / 'audit.md'
        release_notes.write_pointrelease_audit(audit_data, out_path)
        content = out_path.read_text()
        assert '✓ #19418' in content
        assert '✗ #19999' in content
        assert '1 rendered' in content


class TestIsReleaseMachinery:
    def test_update_version_title(self):
        pr = {'title': 'Update version in engine.json for 25.10.2', 'files': ['engine.json']}
        assert release_notes.is_release_machinery(pr) is True

    def test_update_sbom(self):
        pr = {'title': 'Update SBOM', 'files': ['sbom.cdx.json']}
        assert release_notes.is_release_machinery(pr) is True

    def test_update_gpg_key(self):
        pr = {'title': 'Update Linux GPG key for 2025', 'files': ['cmake/install/foo.cmake']}
        assert release_notes.is_release_machinery(pr) is True

    def test_cherrypick_container_title(self):
        pr = {
            'title': 'Cherrypick fixes from dev to pointrelease 25101',
            'files': ['Code/Tools/ProjectManager/Source/ProjectUtils.cpp'],
        }
        assert release_notes.is_release_machinery(pr) is True

    def test_merge_pointrelease_into_main(self):
        pr = {
            'title': 'Merge pull request #19518 from nick-l-o3de/merging_pointrelease_25102_to_main',
            'files': ['engine.json'],
        }
        assert release_notes.is_release_machinery(pr) is True

    def test_add_point_release_branch_to_ar(self):
        pr = {
            'title': 'Add point-release branch to AR merge triggers',
            'files': ['.github/workflows/ar.yml'],
        }
        assert release_notes.is_release_machinery(pr) is True

    def test_workflows_only_files_not_machinery(self):
        # Workflow-only PRs are deliberately NOT classified as machinery by
        # the file-only heuristic,they often contain real CI improvements
        # (e.g. "Add check for adequate free space in linux AR workspace")
        # that curators want to keep. We trust title patterns instead.
        pr = {
            'title': 'Add check for adequate free space in linux AR workspace',
            'files': ['.github/workflows/linux-build.yml'],
        }
        assert release_notes.is_release_machinery(pr) is False

    def test_funding_yml_only_is_machinery(self):
        # TSC-owned repository governance. The notes are organised by SIG, so
        # there is no correct heading for it, and it is not an engine change.
        pr = {
            'title': 'Add FUNDING.yml file to add a Sponsor button on Github',
            'files': ['.github/FUNDING.yml'],
        }
        assert release_notes.is_release_machinery(pr) is True

    def test_funding_yml_alongside_code_is_not_machinery(self):
        # The file rule requires EVERY file to match, so a PR that also touches
        # engine code stays a product change.
        pr = {
            'title': 'Add sponsor button and fix a crash',
            'files': ['.github/FUNDING.yml', 'Code/Framework/AzCore/Thing.cpp'],
        }
        assert release_notes.is_release_machinery(pr) is False

    @pytest.mark.parametrize('path', [
        '.github/ISSUE_TEMPLATE/bug.md',
        '.github/PULL_REQUEST_TEMPLATE.md',
        '.github/CODEOWNERS',
    ])
    def test_other_dotgithub_files_are_not_machinery(self, path):
        # The pattern is the exact file, not the directory: other .github
        # content is real work by real SIGs.
        assert release_notes.is_release_machinery({'title': 'Update', 'files': [path]}) is False

    def test_engine_json_only_is_machinery(self):
        # engine.json-only PRs are version bumps / template updates by definition.
        pr = {
            'title': 'Bump engine.json',
            'files': ['engine.json'],
        }
        assert release_notes.is_release_machinery(pr) is True

    def test_templates_engine_json_only_is_machinery(self):
        pr = {
            'title': 'Refresh templates',
            'files': ['Templates/Minimal/engine.json', 'Templates/Standard/engine.json'],
        }
        assert release_notes.is_release_machinery(pr) is True

    def test_sbom_only_is_machinery(self):
        pr = {
            'title': 'Refresh SBOM',
            'files': ['sbom.cdx.json'],
        }
        assert release_notes.is_release_machinery(pr) is True

    def test_real_product_pr_is_not_machinery(self):
        pr = {
            'title': 'Add Unlit material type to Atom Gem',
            'files': [
                'Gems/Atom/Feature/Common/Code/Source/UnlitMaterial.cpp',
                'Gems/Atom/Feature/Common/Code/Source/UnlitMaterial.h',
            ],
        }
        assert release_notes.is_release_machinery(pr) is False

    def test_mixed_files_is_not_machinery(self):
        # Has engine.json AND product code → not machinery.
        pr = {
            'title': 'Add new material type',
            'files': ['engine.json', 'Gems/Atom/Material.cpp'],
        }
        assert release_notes.is_release_machinery(pr) is False

    def test_empty_files_and_neutral_title_is_not_machinery(self):
        # File-only path requires at least one file. With no files we don't
        # have evidence to classify it as machinery; fall through to False.
        pr = {'title': 'Refactor some helpers', 'files': []}
        assert release_notes.is_release_machinery(pr) is False

    def test_missing_files_key_is_not_machinery(self):
        pr = {'title': 'Refactor some helpers'}
        assert release_notes.is_release_machinery(pr) is False


class TestRenderMarkdownExcludesMachinery:
    def _pr(self, num, title, sig='sig/core', machinery=False, repo='o3de/o3de'):
        return {
            'number': num,
            'repo': repo,
            'title': title,
            'description': title + '.',
            'url': f'https://github.com/{repo}/pull/{num}',
            'sig_category': sig,
            'flags': [],
            'release_machinery': machinery,
        }

    def test_machinery_excluded_by_default(self):
        prs = [
            self._pr(100, 'Add Unlit material type'),
            self._pr(101, 'Update version in engine.json', machinery=True),
        ]
        md = release_notes.render_markdown(prs, '26.05.0')
        assert 'Add Unlit material type' in md
        assert 'Update version in engine.json' not in md

    def test_include_release_machinery_flag(self):
        prs = [
            self._pr(100, 'Add Unlit material type'),
            self._pr(101, 'Update version in engine.json', machinery=True),
        ]
        md = release_notes.render_markdown(prs, '26.05.0', include_release_machinery=True)
        assert 'Update version in engine.json' in md

    def test_cherry_pick_flag_still_excludes(self):
        # release_machinery is additive,the existing flag-based exclusion
        # (cherry-pick / stabilization-sync) still applies independently.
        pr = self._pr(100, 'Cherry pick fix from stabilization', machinery=False)
        pr['flags'] = ['cherry-pick']
        md = release_notes.render_markdown([pr], '26.05.0')
        assert 'Cherry pick' not in md


class TestBuildSummaryPromptExcludesMachinery:
    def test_machinery_excluded_from_prompt(self):
        prs = [
            {'title': 'Add Unlit material type', 'sig_category': 'sig/graphics-audio',
             'flags': [], 'release_machinery': False},
            {'title': 'Update version in engine.json', 'sig_category': 'sig/build',
             'flags': [], 'release_machinery': True},
        ]
        prompt = release_notes._build_summary_prompt(prs, '26.05.0')
        assert 'Add Unlit material type' in prompt
        assert 'Update version in engine.json' not in prompt

    def test_include_release_machinery_in_prompt(self):
        prs = [
            {'title': 'Update version in engine.json', 'sig_category': 'sig/build',
             'flags': [], 'release_machinery': True},
        ]
        prompt = release_notes._build_summary_prompt(
            prs, '26.05.0', include_release_machinery=True,
        )
        assert 'Update version in engine.json' in prompt


class TestEmitPointReleaseAwarenessLog:
    def test_logs_when_from_ref_is_point_release_with_matching_merge_base(self, tmp_path, caplog):
        # Sibling tags include 2510.0; merge-base of both 2510.0 and 2510.2
        # against to-ref resolves to the same SHA → the equivalence log fires.
        import logging
        merge_base_sha = 'abc123def0' * 4

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ['git', 'tag']:
                return mock.MagicMock(returncode=0, stdout='2510.0\n2510.1\n2510.2\n', stderr='')
            if cmd[1] == 'merge-base':
                return mock.MagicMock(returncode=0, stdout=f'{merge_base_sha}\n', stderr='')
            if cmd[1] == 'show':
                return mock.MagicMock(returncode=0, stdout='2025-07-31T18:42:11+00:00\n', stderr='')
            raise AssertionError(f'unexpected cmd: {cmd}')

        with mock.patch('release_notes.subprocess.run', side_effect=fake_run), \
             caplog.at_level(logging.INFO, logger='o3de.release_notes'):
            release_notes._emit_point_release_awareness_log(
                from_ref='2510.2',
                to_ref='origin/stabilization/26050',
                repo_path_map={'o3de/o3de': tmp_path},
                repos=['o3de/o3de'],
            )
        assert any('Point releases on 2510 line' in r.message for r in caplog.records)

    def test_silent_for_non_point_release_ref(self, tmp_path, caplog):
        import logging
        with mock.patch('release_notes.subprocess.run') as mock_run, \
             caplog.at_level(logging.INFO, logger='o3de.release_notes'):
            release_notes._emit_point_release_awareness_log(
                from_ref='development',
                to_ref='main',
                repo_path_map={'o3de/o3de': tmp_path},
                repos=['o3de/o3de'],
            )
            mock_run.assert_not_called()
        assert not any('Point releases on' in r.message for r in caplog.records)

    def test_silent_for_zero_point_release(self, tmp_path, caplog):
        # 2510.0 IS a point-release tag pattern but with patch=0,nothing
        # earlier to compare against, so no log.
        import logging
        with mock.patch('release_notes.subprocess.run') as mock_run, \
             caplog.at_level(logging.INFO, logger='o3de.release_notes'):
            release_notes._emit_point_release_awareness_log(
                from_ref='2510.0',
                to_ref='main',
                repo_path_map={'o3de/o3de': tmp_path},
                repos=['o3de/o3de'],
            )
            mock_run.assert_not_called()
        assert not any('Point releases on' in r.message for r in caplog.records)


class TestRenderCoverageReconciliation:
    @staticmethod
    def _pr(number, sig='sig/build', flags=None, machinery=False):
        return {
            'number': number, 'repo': 'o3de/o3de', 'url': '',
            'title': f'Change {number}', 'description': f'Change {number}.',
            'sig_category': sig, 'flags': flags or [], 'release_machinery': machinery,
        }

    def test_counts_sum_to_total(self):
        prs = [
            self._pr(1),
            self._pr(2, flags=['cherry-pick']),
            self._pr(3, machinery=True),
            self._pr(4, sig='uncategorized'),
            self._pr(5),
        ]
        counts = release_notes.summarize_render_coverage(prs)
        excluded = sum(v for k, v in counts.items() if k.startswith('excluded_'))
        assert counts['total'] == 5
        assert counts['rendered'] == 2
        assert counts['rendered'] + excluded == counts['total']

    def test_reason_breakdown(self):
        prs = [
            self._pr(1, flags=['cherry-pick']),
            self._pr(2, machinery=True),
            self._pr(3, sig='uncategorized'),
        ]
        counts = release_notes.summarize_render_coverage(prs)
        assert counts['excluded_cherry-pick'] == 1
        assert counts['excluded_release_machinery'] == 1
        assert counts['excluded_uncategorized'] == 1
        assert counts['rendered'] == 0

    def test_opt_in_flags_move_prs_into_rendered(self):
        prs = [self._pr(1, machinery=True), self._pr(2, sig='uncategorized')]
        counts = release_notes.summarize_render_coverage(
            prs, include_uncategorized=True, include_release_machinery=True,
        )
        assert counts['rendered'] == 2

    def test_matches_render_markdown_bullet_count(self):
        prs = [
            self._pr(1),
            self._pr(2, flags=['cherry-pick']),
            self._pr(3, machinery=True),
            self._pr(4, sig='uncategorized'),
            self._pr(5, sig='sig/core'),
        ]
        md = release_notes.render_markdown(prs, '26.10.0')
        counts = release_notes.summarize_render_coverage(prs)
        assert md.count('\n- ') == counts['rendered']

    def test_legacy_sync_flag_counted_as_rendered(self):
        counts = release_notes.summarize_render_coverage(
            [self._pr(1, flags=['stabilization-sync'])]
        )
        assert counts['rendered'] == 1

    def test_warns_when_prs_dropped(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger='o3de.release_notes'):
            release_notes.log_render_coverage(
                release_notes.summarize_render_coverage([self._pr(1, flags=['cherry-pick'])])
            )
        assert any(r.levelno == logging.WARNING for r in caplog.records)
        assert any('Reconciliation' in r.message for r in caplog.records)

    def test_no_warning_when_nothing_dropped(self, caplog):
        import logging
        with caplog.at_level(logging.INFO, logger='o3de.release_notes'):
            release_notes.log_render_coverage(
                release_notes.summarize_render_coverage([self._pr(1)])
            )
        assert not any(r.levelno == logging.WARNING for r in caplog.records)


class TestMarkdownEscaping:
    def test_single_escape_in_combined_description(self):
        # Regression: the combined title+body path escaped twice, turning \[ into
        # \\[ which renders as a literal backslash plus an UNESCAPED bracket.
        title = 'Fix crash in [Atom] `render` pipeline'
        body = ('Completely unrelated wording about widget doohickey thingamabob '
                'whatsit gizmo contraption apparatus.')
        result = release_notes._build_pr_description(title, body)
        assert '\\\\' not in result
        assert '\\[Atom\\]' in result

    @staticmethod
    def _has_live_tag(text):
        """True if any '<' that opens a tag is left unescaped."""
        return re.search(r'(?<!\\)<[a-zA-Z/!?]', text) is not None

    def test_html_tag_opener_escaped_in_title(self):
        result = release_notes._sanitize_pr_title_for_markdown(
            'Add <img src=x onerror=alert(1)> support'
        )
        assert not self._has_live_tag(result)
        assert '\\<img' in result

    def test_script_tag_escaped(self):
        result = release_notes._sanitize_pr_title_for_markdown('Fix <script>alert(1)</script>')
        assert not self._has_live_tag(result)
        assert '\\<script' in result
        assert '\\</script' in result

    def test_arrow_not_escaped(self):
        # Real 26.05.0 titles: escaping every '<' would mangle these.
        result = release_notes._sanitize_pr_title_for_markdown(
            'Meshlets: fix 64->32 narrowing when building IndexBufferView size'
        )
        assert '64->32' in result
        assert '\\' not in result

    def test_less_than_with_space_not_escaped(self):
        result = release_notes._sanitize_pr_title_for_markdown('Guard when count < 32 items')
        assert 'count < 32' in result

    def test_html_escaped_in_body_derived_description(self):
        body = ('This change repairs the <img src=x onerror=alert(1)> widget doohickey '
                'gizmo contraption apparatus thingy.')
        result = release_notes._build_pr_description('Repair widget', body)
        assert not self._has_live_tag(result)

    def test_existing_escapes_unchanged(self):
        assert release_notes._sanitize_pr_title_for_markdown('Fix bug (#19709)') == 'Fix bug.'
        assert release_notes._sanitize_pr_title_for_markdown(
            '[Editor] Fix paths'
        ) == '\\[Editor\\] Fix paths.'

    def test_summary_html_neutralised(self):
        cleaned = release_notes._clean_summary('The release adds <script>alert(1)</script> support.')
        assert not self._has_live_tag(cleaned)
        assert '\\<script' in cleaned

    def test_summary_markdown_emphasis_preserved(self):
        cleaned = release_notes._clean_summary('This adds **Open Particle System** support.')
        assert '**Open Particle System**' in cleaned


class TestSubprocessTimeoutHandling:
    def test_gh_command_timeout_becomes_runtime_error(self):
        with mock.patch('release_notes.subprocess.run',
                        side_effect=subprocess.TimeoutExpired('gh', 30)), \
             pytest.raises(RuntimeError, match='timed out'):
            release_notes._run_gh_command(['gh', 'api', 'graphql'])

    def test_gh_missing_binary_becomes_runtime_error(self):
        with mock.patch('release_notes.subprocess.run', side_effect=OSError('no gh')), \
             pytest.raises(RuntimeError, match='failed to run'):
            release_notes._run_gh_command(['gh', 'api', 'graphql'])

    def test_batch_fetch_survives_timeout(self):
        # A timeout mid-run must not abort the whole fetch with a traceback.
        # time.sleep is patched: a timeout is transient, so the batch now backs
        # off and retries, and an unpatched sleep would add 6s to the suite.
        with mock.patch('release_notes.subprocess.run',
                        side_effect=subprocess.TimeoutExpired('gh', 30)), \
             mock.patch('release_notes.time.sleep'):
            result = release_notes.fetch_pr_metadata_batch('o3de/o3de', [1, 2, 3])
        assert result == []

    def test_gh_auth_check_timeout_returns_false(self):
        with mock.patch('release_notes.shutil.which', return_value='/usr/bin/gh'), \
             mock.patch('release_notes.subprocess.run',
                        side_effect=subprocess.TimeoutExpired('gh', 10)):
            assert release_notes._check_gh_available() is False


class TestDescriptionLengthPolicy:
    def test_overlong_paragraph_falls_back_to_title(self):
        # Regression: _extract_first_paragraph used to truncate to exactly 300
        # chars, so the ">300 -> use the title" guard never fired and 37 of the
        # 256 descriptions in the 26.05.0 corpus ended mid-sentence, several on
        # a severed URL.
        title = 'Decouple AssImp from Scene API'
        body = 'We would like to use a different library for scene asset import. ' * 8
        result = release_notes._build_pr_description(title, body)
        assert result == 'Decouple AssImp from Scene API.'
        assert not result.endswith('...')

    def test_extract_first_paragraph_does_not_truncate(self):
        body = 'word ' * 200
        assert len(release_notes._extract_first_paragraph(body)) > \
            release_notes.MAX_DESCRIPTION_CHARS

    def test_in_range_paragraph_still_used(self):
        title = 'Fix the widget'
        body = ('This change repairs the widget so that it no longer drops frames when '
                'the viewport is resized during play mode.')
        assert release_notes._build_pr_description(title, body).startswith('This change repairs')

    def test_too_short_paragraph_falls_back_to_title(self):
        assert release_notes._build_pr_description('Fix the widget', 'Yes.') == 'Fix the widget.'


class TestAtomicWriteIntegrity:
    def test_preserves_existing_file_mode(self, tmp_path):
        # Regression: mkstemp() creates 0600 and os.replace() keeps that mode,
        # so every rewrite silently made the output owner-only.
        target = tmp_path / 'out.json'
        target.write_text('{}')
        target.chmod(0o644)
        release_notes.write_json_atomic({'pull_requests': []}, target)
        assert stat.S_IMODE(target.stat().st_mode) == 0o644

    def test_new_file_gets_default_mode(self, tmp_path):
        target = tmp_path / 'new.md'
        release_notes.write_markdown_atomic('# notes\n', target)
        assert stat.S_IMODE(target.stat().st_mode) == release_notes.DEFAULT_OUTPUT_MODE

    def test_content_round_trips(self, tmp_path):
        target = tmp_path / 'out.json'
        release_notes.write_json_atomic({'pull_requests': [{'number': 1}]}, target)
        assert json.loads(target.read_text())['pull_requests'][0]['number'] == 1

    def test_no_temp_files_left_behind(self, tmp_path):
        target = tmp_path / 'out.md'
        release_notes.write_markdown_atomic('body\n', target)
        assert [p.name for p in tmp_path.iterdir()] == ['out.md']

    def test_failure_cleans_up_temp_file(self, tmp_path):
        target = tmp_path / 'out.md'
        with mock.patch('release_notes.os.replace', side_effect=OSError('boom')), \
             pytest.raises(OSError):
            release_notes.write_markdown_atomic('body\n', target)
        assert list(tmp_path.iterdir()) == []


class TestSbomIntegrity:
    def test_version_matches_release_notes(self):
        assert release_notes.__version__ == generate_sbom.PROJECT_VERSION

    def test_version_matches_pyproject(self):
        text = (pathlib.Path(__file__).parent.parent / 'pyproject.toml').read_text()
        assert f'version = "{generate_sbom.PROJECT_VERSION}"' in text

    def test_stdlib_inventory_is_derived_not_hardcoded(self, tmp_path):
        (tmp_path / 'release_notes.py').write_text('import zoneinfo\nfrom decimal import Decimal\n')
        modules = generate_sbom.discover_stdlib_modules(tmp_path)
        assert 'zoneinfo' in modules
        assert 'decimal' in modules

    def test_inventory_excludes_project_and_test_modules(self, tmp_path):
        (tmp_path / 'release_notes.py').write_text(
            'import release_notes\nimport pytest\nfrom unittest import mock\n'
        )
        assert generate_sbom.discover_stdlib_modules(tmp_path) == []

    def test_inventory_covers_every_real_import(self):
        project_dir = pathlib.Path(__file__).parent.parent
        modules = generate_sbom.discover_stdlib_modules(project_dir)
        for expected in ('contextlib', 'shlex', 'typing', 'stat'):
            assert expected in modules

    def test_substantive_document_is_deterministic(self, tmp_path):
        project_dir = pathlib.Path(__file__).parent.parent
        first = generate_sbom.generate_sbom(project_dir)
        second = generate_sbom.generate_sbom(project_dir)
        assert generate_sbom._substantive(first) == generate_sbom._substantive(second)
        assert first['serialNumber'] == second['serialNumber']

    def test_serial_number_tracks_content(self, tmp_path):
        (tmp_path / 'release_notes.py').write_text('import json\n')
        first = generate_sbom.generate_sbom(tmp_path)
        (tmp_path / 'release_notes.py').write_text('import json\nimport csv\n')
        second = generate_sbom.generate_sbom(tmp_path)
        assert first['serialNumber'] != second['serialNumber']

    def test_dependency_refs_all_resolve(self):
        sbom = generate_sbom.generate_sbom(pathlib.Path(__file__).parent.parent)
        refs = {c['bom-ref'] for c in sbom['components']}
        assert set(sbom['dependencies'][0]['dependsOn']) <= refs
        assert sbom['dependencies'][0]['ref'] == sbom['metadata']['component']['bom-ref']

    def test_purl_does_not_claim_a_pypi_package(self):
        sbom = generate_sbom.generate_sbom(pathlib.Path(__file__).parent.parent)
        for component in sbom['components']:
            assert not component.get('purl', '').startswith('pkg:pypi/')

    def test_document_is_environment_independent(self, tmp_path):
        # No field may carry the running interpreter's exact version, or the
        # document differs between a CI runner and a workstation.
        import platform
        sbom = generate_sbom.generate_sbom(pathlib.Path(__file__).parent.parent)
        rendered = json.dumps(generate_sbom._substantive(sbom))
        running = platform.python_version()
        if running != generate_sbom.MIN_PYTHON_VERSION:
            assert running not in rendered

    def test_check_mode_detects_stale_sbom(self, tmp_path, monkeypatch, capsys):
        (tmp_path / 'release_notes.py').write_text('import json\n')
        (tmp_path / 'sbom.cdx.json').write_text('{"metadata": {}, "components": []}')
        monkeypatch.setattr(generate_sbom, '__file__', str(tmp_path / 'generate_sbom.py'))
        monkeypatch.setattr(sys, 'argv', ['generate_sbom.py', '--check'])
        assert generate_sbom.main() == 1

    def test_regeneration_is_a_noop_when_current(self, tmp_path, monkeypatch):
        (tmp_path / 'release_notes.py').write_text('import json\n')
        monkeypatch.setattr(generate_sbom, '__file__', str(tmp_path / 'generate_sbom.py'))
        monkeypatch.setattr(sys, 'argv', ['generate_sbom.py'])
        assert generate_sbom.main() == 0
        first = (tmp_path / 'sbom.cdx.json').read_text()
        assert generate_sbom.main() == 0
        assert (tmp_path / 'sbom.cdx.json').read_text() == first


class TestSchemaVersionProvenance:
    def test_schema_version_is_current(self):
        assert release_notes.SCHEMA_VERSION == 6

    def test_previous_schema_still_loads(self, tmp_path):
        path = tmp_path / 'old.json'
        path.write_text(json.dumps({
            'metadata': {'schema_version': release_notes.SCHEMA_VERSION - 1},
            'pull_requests': [],
        }))
        assert release_notes.load_existing_json(path) is not None

    def test_two_versions_back_is_rejected(self, tmp_path):
        path = tmp_path / 'ancient.json'
        path.write_text(json.dumps({
            'metadata': {'schema_version': release_notes.SCHEMA_VERSION - 2},
            'pull_requests': [],
        }))
        assert release_notes.load_existing_json(path) is None


class TestPerRepoRefs:
    def test_defaults_to_global_ref(self):
        mapping = release_notes.parse_repo_ref_mappings(
            None, '2605.0', ['o3de/o3de', 'o3de/o3de-extras'], '--repo-from-ref',
        )
        assert mapping == {'o3de/o3de': '2605.0', 'o3de/o3de-extras': '2605.0'}

    def test_override_for_untagged_repo(self):
        # o3de/o3de-extras has no 2605.0 tag; without an override the whole
        # multi-repo run aborts on that repo.
        mapping = release_notes.parse_repo_ref_mappings(
            ['o3de/o3de-extras=origin/stabilization/26050'],
            '2605.0', ['o3de/o3de', 'o3de/o3de-extras'], '--repo-from-ref',
        )
        assert mapping['o3de/o3de'] == '2605.0'
        assert mapping['o3de/o3de-extras'] == 'origin/stabilization/26050'

    def test_rejects_malformed_mapping(self):
        with pytest.raises(ValueError, match='--repo-from-ref'):
            release_notes.parse_repo_ref_mappings(
                ['not-a-mapping'], '2605.0', ['o3de/o3de'], '--repo-from-ref')

    def test_validates_override_ref(self):
        with pytest.raises(ValueError, match='Invalid git reference'):
            release_notes.parse_repo_ref_mappings(
                ['o3de/o3de=--exec=evil'], '2605.0', ['o3de/o3de'], '--repo-from-ref')

    def test_ref_exists_true_on_success(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout='abc\n', stderr='')
            assert release_notes.ref_exists(tmp_path, '2605.0') is True

    def test_ref_exists_false_on_missing(self, tmp_path):
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=128, stdout='', stderr='')
            assert release_notes.ref_exists(tmp_path, '2605.0') is False

    def test_ref_exists_false_on_timeout(self, tmp_path):
        with mock.patch('release_notes.subprocess.run',
                        side_effect=subprocess.TimeoutExpired('git', 15)):
            assert release_notes.ref_exists(tmp_path, '2605.0') is False

    def test_preflight_reports_missing_ref_with_remedy(self, tmp_path):
        with mock.patch('release_notes.ref_exists', return_value=False):
            problems = release_notes.verify_refs_exist(
                {'o3de/o3de-extras': tmp_path},
                {'o3de/o3de-extras': '2605.0'},
                {'o3de/o3de-extras': 'origin/development'},
                ['o3de/o3de-extras'],
            )
        assert len(problems) == 2
        assert '--repo-from-ref' in problems[0]

    def test_preflight_silent_when_refs_resolve(self, tmp_path):
        with mock.patch('release_notes.ref_exists', return_value=True):
            assert release_notes.verify_refs_exist(
                {'o3de/o3de': tmp_path},
                {'o3de/o3de': '2605.0'},
                {'o3de/o3de': 'origin/development'},
                ['o3de/o3de'],
            ) == []


class TestRepeatableMappingFlags:
    @staticmethod
    def _parse(argv):
        import argparse
        parser = argparse.ArgumentParser()
        release_notes.add_parser_args(parser)
        return parser.parse_args(argv)

    _BASE = ['fetch', '--from-ref', 'a', '--to-ref', 'b', '--output-json', 'o.json']

    def test_repeated_repo_path_flags_accumulate(self):
        # Regression: bare nargs='*' kept only the last occurrence, so the
        # README's multi-repo example silently used --default-repo-path for
        # every repo but the last one.
        args = self._parse(self._BASE + [
            '--repo-path', 'o3de/o3de=/a',
            '--repo-path', 'o3de/o3de-extras=/b',
        ])
        assert args.repo_path == ['o3de/o3de=/a', 'o3de/o3de-extras=/b']

    def test_single_flag_multiple_values_still_works(self):
        args = self._parse(self._BASE + [
            '--repo-path', 'o3de/o3de=/a', 'o3de/o3de-extras=/b',
        ])
        assert args.repo_path == ['o3de/o3de=/a', 'o3de/o3de-extras=/b']

    def test_repeated_repo_from_ref_flags_accumulate(self):
        args = self._parse(self._BASE + [
            '--repo-from-ref', 'o3de/o3de=2605.0',
            '--repo-from-ref', 'o3de/o3de-extras=2510.2',
        ])
        assert len(args.repo_from_ref) == 2

    def test_repeated_repos_flags_accumulate(self):
        args = self._parse(self._BASE + ['--repos', 'o3de/o3de', '--repos', 'o3de/o3de-extras'])
        assert args.repos == ['o3de/o3de', 'o3de/o3de-extras']

    def test_repos_defaults_applied_in_main(self, monkeypatch):
        monkeypatch.setattr(sys, 'argv', ['release_notes', *self._BASE])
        with mock.patch('release_notes._run_fetch', return_value=0) as mock_fetch:
            release_notes.main()
        assert mock_fetch.call_args[0][0].repos == release_notes.DEFAULT_REPOS

    def test_both_paths_resolve_after_fix(self, tmp_path):
        mapping = release_notes.parse_repo_path_mappings(
            ['o3de/o3de=/a', 'o3de/o3de-extras=/b'], '.', ['o3de/o3de', 'o3de/o3de-extras'],
        )
        assert str(mapping['o3de/o3de']) == '/a'
        assert str(mapping['o3de/o3de-extras']) == '/b'


class TestPriorReleaseExclusion:
    @staticmethod
    def _write_report(path, pairs, schema=4):
        path.write_text(json.dumps({
            'metadata': {'schema_version': schema},
            'pull_requests': [{'repo': r, 'number': n, 'title': f'PR {n}'} for r, n in pairs],
        }))
        return path

    def test_collects_repo_number_pairs(self, tmp_path):
        src = self._write_report(tmp_path / 'prior.json',
                                 [('o3de/o3de', 1), ('o3de/o3de-extras', 2)])
        keys, loaded = release_notes.load_prior_release_pr_keys([str(src)])
        assert keys == {('o3de/o3de', 1), ('o3de/o3de-extras', 2)}
        assert len(loaded) == 1

    def test_multiple_sources_union(self, tmp_path):
        a = self._write_report(tmp_path / 'a.json', [('o3de/o3de', 1)])
        b = self._write_report(tmp_path / 'b.json', [('o3de/o3de', 2)])
        keys, loaded = release_notes.load_prior_release_pr_keys([str(a), str(b)])
        assert keys == {('o3de/o3de', 1), ('o3de/o3de', 2)}
        assert len(loaded) == 2

    def test_old_schema_still_usable(self, tmp_path):
        # Only repo+number are read, so an older report is a valid source.
        src = self._write_report(tmp_path / 'old.json', [('o3de/o3de', 1)], schema=2)
        keys, loaded = release_notes.load_prior_release_pr_keys([str(src)])
        assert keys == {('o3de/o3de', 1)}
        assert len(loaded) == 1

    def test_missing_file_is_reported_not_silent(self, tmp_path, caplog):
        import logging
        with caplog.at_level(logging.ERROR, logger='o3de.release_notes'):
            keys, loaded = release_notes.load_prior_release_pr_keys([str(tmp_path / 'nope.json')])
        assert keys == set()
        assert loaded == []
        assert any('not found' in r.message for r in caplog.records)

    def test_malformed_json_is_reported(self, tmp_path, caplog):
        import logging
        bad = tmp_path / 'bad.json'
        bad.write_text('{not json')
        with caplog.at_level(logging.ERROR, logger='o3de.release_notes'):
            keys, loaded = release_notes.load_prior_release_pr_keys([str(bad)])
        assert loaded == []
        assert any('Could not read' in r.message for r in caplog.records)

    def test_exclusion_is_repo_scoped(self):
        # PR #5 in o3de/o3de must not exclude PR #5 in o3de/o3de-extras.
        prior = {('o3de/o3de', 5)}
        kept, dropped = release_notes._apply_prior_release_exclusion(
            [5, 6], 'o3de/o3de-extras', prior)
        assert kept == [5, 6]
        assert dropped == 0

    def test_exclusion_drops_matching_numbers(self):
        prior = {('o3de/o3de', 5), ('o3de/o3de', 7)}
        kept, dropped = release_notes._apply_prior_release_exclusion(
            [5, 6, 7, 8], 'o3de/o3de', prior)
        assert kept == [6, 8]
        assert dropped == 2

    def test_no_exclusion_set_is_a_passthrough(self):
        kept, dropped = release_notes._apply_prior_release_exclusion([1, 2], 'o3de/o3de', set())
        assert kept == [1, 2]
        assert dropped == 0

    def test_self_exclusion_is_refused(self, tmp_path):
        # Pointing --exclude-json at this run's own output would empty the
        # report on the next run.
        repo_dir = tmp_path / 'repo'
        repo_dir.mkdir()
        (repo_dir / '.git').mkdir()
        out_json = tmp_path / 'out.json'
        self._write_report(out_json, [('o3de/o3de', 1)])
        args = mock.Mock(
            from_ref='a', to_ref='b', repos=['o3de/o3de'],
            repo_path=None, repo_from_ref=None, repo_to_ref=None,
            exclude_json=[str(out_json)],
            default_repo_path=str(repo_dir), output_json=str(out_json), dry_run=True,
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout='', stderr='')
            assert release_notes._run_fetch(args) == 1

    def test_unusable_source_aborts_rather_than_silently_including(self, tmp_path):
        repo_dir = tmp_path / 'repo'
        repo_dir.mkdir()
        (repo_dir / '.git').mkdir()
        args = mock.Mock(
            from_ref='a', to_ref='b', repos=['o3de/o3de'],
            repo_path=None, repo_from_ref=None, repo_to_ref=None,
            exclude_json=[str(tmp_path / 'missing.json')],
            default_repo_path=str(repo_dir), output_json=str(tmp_path / 'o.json'),
            dry_run=True,
        )
        with mock.patch('release_notes.subprocess.run') as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout='', stderr='')
            assert release_notes._run_fetch(args) == 1

    def test_dry_run_preview_reflects_exclusion(self, tmp_path, caplog):
        import logging
        repo_dir = tmp_path / 'repo'
        repo_dir.mkdir()
        (repo_dir / '.git').mkdir()
        prior = self._write_report(tmp_path / 'prior.json', [('o3de/o3de', 42)])
        args = mock.Mock(
            from_ref='a', to_ref='b', repos=['o3de/o3de'],
            repo_path=None, repo_from_ref=None, repo_to_ref=None,
            exclude_json=[str(prior)],
            default_repo_path=str(repo_dir), output_json=str(tmp_path / 'o.json'),
            dry_run=True,
        )
        with mock.patch('release_notes.subprocess.run') as mock_run, \
             caplog.at_level(logging.INFO, logger='o3de.release_notes'):
            mock_run.return_value = mock.Mock(
                returncode=0, stdout='Fix bug (#42)\nOther fix (#43)\n', stderr='')
            assert release_notes._run_fetch(args) == 0
        messages = [r.getMessage() for r in caplog.records]
        assert any('1 PRs would be fetched' in m for m in messages)
        assert any('#43' in m for m in messages)
        assert not any('#42' in m and 'PR numbers' in m for m in messages)

    def test_repeated_exclude_json_flags_accumulate(self):
        import argparse
        parser = argparse.ArgumentParser()
        release_notes.add_parser_args(parser)
        args = parser.parse_args([
            'fetch', '--from-ref', 'a', '--to-ref', 'b', '--output-json', 'o.json',
            '--exclude-json', 'one.json', '--exclude-json', 'two.json',
        ])
        assert args.exclude_json == ['one.json', 'two.json']


class TestTokenRedactionCoverage:
    @pytest.mark.parametrize('token', [
        'ghp_abcdefghijklmnopqrstuvwxyz012345',
        'gho_abcdefghijklmnopqrstuvwxyz012345',
        'ghu_abcdefghijklmnopqrstuvwxyz012345',
        'ghs_abcdefghijklmnopqrstuvwxyz012345',
        'ghr_abcdefghijklmnopqrstuvwxyz012345',
        'github_pat_11ABCDEFG0aBcDeFgHiJk_ZYXWVUTSRQPONMLKJIHGFEDCBA1234567890abcdef',
    ])
    def test_token_shape_is_redacted(self, token):
        out = release_notes._safe_stderr(f'error: bad credentials for {token} here')
        assert token not in out
        assert '<redacted-token>' in out

    def test_ordinary_text_untouched(self):
        assert release_notes._safe_stderr('fatal: bad revision 2605.0') == \
            'fatal: bad revision 2605.0'


class TestDocumentationAccuracy:
    """Guard the claims the docs make about the code.

    Scoped deliberately to checks that only fail when something is genuinely
    wrong. Anything that would break on an ordinary, correct edit belongs in a
    human review, not here: an exact test count is asserted as a floor rather
    than an equality, and no check parses English prose. CHANGELOG.md is
    excluded throughout because it is an append-only record of past states and
    is *supposed* to contain claims that are no longer true.
    """

    ROOT = pathlib.Path(__file__).parent.parent
    DOC_NAMES = ('README.md', 'ARCHITECTURE.md', 'AGENTS.md',
                 'CONTRIBUTING.md', 'SECURITY.md', 'RELEASE_RUNBOOK.md')
    # Put this marker in a fenced block to exempt it from the --exclude-json
    # rule (e.g. an example for a first-ever release, with no prior report).
    NO_EXCLUDE_MARKER = 'doc-check: exclusion-not-applicable'

    @classmethod
    def _docs(cls):
        return {n: (cls.ROOT / n).read_text(encoding='utf-8')
                for n in cls.DOC_NAMES if (cls.ROOT / n).exists()}

    @staticmethod
    def _fenced(text, lang=''):
        return re.findall(r'```' + lang + r'\n(.*?)```', text, re.S)

    def test_all_expected_docs_exist(self):
        # If a doc is renamed or dropped, every other check here would silently
        # stop covering it.
        missing = [n for n in self.DOC_NAMES if not (self.ROOT / n).exists()]
        assert missing == []

    def test_every_cli_flag_is_documented(self):
        import argparse
        parser = argparse.ArgumentParser()
        release_notes.add_parser_args(parser)
        subparsers = [a for a in parser._actions
                      if isinstance(a, argparse._SubParsersAction)][0]
        flags = {opt
                 for sp in subparsers.choices.values()
                 for action in sp._actions
                 for opt in action.option_strings
                 if opt.startswith('--') and opt != '--help'}
        alltext = '\n'.join(self._docs().values())
        assert sorted(f for f in flags if f not in alltext) == []

    def test_readme_records_the_current_version(self):
        assert release_notes.__version__ in self._docs()['README.md']

    def test_readme_json_example_matches_schema_version(self):
        example = self._readme_json_example()
        assert example['metadata']['schema_version'] == release_notes.SCHEMA_VERSION

    def test_readme_json_example_is_valid_json(self):
        assert 'pull_requests' in self._readme_json_example()

    def test_readme_json_example_is_internally_consistent(self):
        # The documented categorization_summary must add up to the documented
        # pr_count. A reader who cannot trust the arithmetic cannot trust the
        # shape either; this is the exact defect that shipped in 0.6.0-beta.
        meta = self._readme_json_example()['metadata']
        assert sum(meta['categorization_summary'].values()) == meta['pr_count']

    def _readme_json_example(self):
        blocks = self._fenced(self._docs()['README.md'], 'json')
        assert blocks, 'README lost its JSON schema example'
        return json.loads(blocks[0])

    def test_claimed_test_count_is_a_floor_that_holds(self):
        # Asserted as >=, never ==, so adding tests cannot break the docs.
        readme = self._docs()['README.md']
        claimed = re.search(r'(\d+)\+ unit tests', readme)
        assert claimed, 'README should claim a test floor like "300+ unit tests"'
        collected = sum(1 for cls_name, cls_obj in globals().items()
                        if cls_name.startswith('Test') and isinstance(cls_obj, type)
                        for m in dir(cls_obj) if m.startswith('test_'))
        assert collected >= int(claimed.group(1))

    def test_relative_links_resolve(self):
        broken = []
        for name, text in self._docs().items():
            for link in set(re.findall(r'\]\((?!https?:|#)([^)]+)\)', text)):
                if not (self.ROOT / link.split('#')[0]).exists():
                    broken.append(f'{name} -> {link}')
        assert sorted(broken) == []

    def test_shell_examples_exclude_the_previous_release(self):
        # A fetch/generate example without --exclude-json is wrong by default
        # for a major release: the window reaches back past the prior release.
        # Opt out with NO_EXCLUDE_MARKER when an example genuinely needs it.
        offenders = []
        for name, text in self._docs().items():
            for block in self._fenced(text, 'bash'):
                if not re.search(r'release_notes\.py\s+(generate|fetch)', block):
                    continue
                if self.NO_EXCLUDE_MARKER in block or '--exclude-json' in block:
                    continue
                offenders.append(name)
        assert sorted(set(offenders)) == []

    def test_diagram_boxes_are_aligned(self):
        # Compares only contiguous runs of box-drawing lines, so one fenced
        # block may legitimately hold several diagrams of different widths.
        misaligned = []
        for name, text in self._docs().items():
            for block in self._fenced(text):
                run = []
                for line in block.splitlines() + ['']:
                    if line.startswith('│') and line.endswith('│'):
                        run.append(line)
                        continue
                    if len(run) > 1 and len({len(x) for x in run}) > 1:
                        misaligned.append(f'{name}: widths {sorted({len(x) for x in run})}')
                    run = []
        assert sorted(set(misaligned)) == []

    # Matches every way the docs state a schema version: the JSON form
    # (`"schema_version": 6`), the prose form (`schema_version: 6`), and the
    # shorthand used in narrative text and ASCII diagrams (`schema v6`,
    # `JSON v6`). The original check required the closing quote of the JSON
    # form and only compared against SCHEMA_VERSION - 1, so ARCHITECTURE.md
    # sat on `schema v5`, `JSON v4`, and `schema_version: 5` simultaneously
    # while the suite stayed green.
    SCHEMA_VERSION_MENTION = re.compile(
        r'(?:schema[_ ]version["\']?\s*[:=]\s*|schema\s+v|JSON\s+v)(\d+)',
        re.IGNORECASE,
    )

    def test_no_doc_claims_a_superseded_schema_version(self):
        offenders = []
        for name, text in self._docs().items():
            for match in self.SCHEMA_VERSION_MENTION.finditer(text):
                if int(match.group(1)) != release_notes.SCHEMA_VERSION:
                    offenders.append(f'{name}: {match.group(0)!r}')
        assert offenders == []

    def test_schema_version_mention_pattern_actually_matches_each_form(self):
        # Guards the guard. If the pattern stops recognising a form, the check
        # above degrades to passing vacuously, which is how the old one failed.
        forms = ['"schema_version": 6', 'schema_version: 6', 'schema v6',
                 'JSON v6', "'schema_version': 6"]
        for form in forms:
            found = self.SCHEMA_VERSION_MENTION.findall(form)
            assert found == ['6'], f'pattern missed {form!r}'

    def test_schema_version_check_is_not_vacuous(self):
        # Every doc that pins the schema version must be visible to the check,
        # so a doc set that mentions it nowhere cannot pass by silence.
        alltext = '\n'.join(self._docs().values())
        assert self.SCHEMA_VERSION_MENTION.search(alltext) is not None


class TestAuditChecksRenderedSet:
    """The audit must compare against what renders, not what was collected."""

    @staticmethod
    def _audit_data(present, filtered):
        return {
            'from_ref': '2510.2', 'to_ref': 'main', 'predecessor_tag': '2510.0',
            'per_repo': {'o3de/o3de': {
                'containers': [{'container_pr': 19506, 'container_sha': 'abc',
                                'title': 'Cherry pick fixes for point release from dev',
                                'bundled_prs': [19418, 19450]}],
                'present_pr_numbers': present,
                'filtered_pr_numbers': filtered,
                'predecessor_tag': '2510.0',
            }},
        }

    def test_filtered_pr_is_warned_not_ticked(self, tmp_path):
        out = tmp_path / 'audit.md'
        release_notes.write_pointrelease_audit(
            self._audit_data({19418}, {19450: 'cherry-pick'}), out)
        content = out.read_text()
        assert '✓ #19418' in content
        assert '⚠ #19450' in content
        assert '✓ #19450' not in content
        assert 'cherry-pick' in content

    def test_summary_counts_all_three_states(self, tmp_path):
        out = tmp_path / 'audit.md'
        release_notes.write_pointrelease_audit(
            self._audit_data({19418}, {19450: 'uncategorized'}), out)
        content = out.read_text()
        assert '1 rendered' in content
        assert '1 filtered out' in content
        assert '0 not found' in content
        assert 'Action required before publishing' in content

    def test_clean_audit_says_so(self, tmp_path):
        out = tmp_path / 'audit.md'
        release_notes.write_pointrelease_audit(self._audit_data({19418, 19450}, {}), out)
        assert 'All bundled fixes are present' in out.read_text()

    def test_classifier_is_the_shared_source_of_truth(self):
        prs = [
            {'repo': 'o3de/o3de', 'number': 1, 'sig_category': 'sig/build', 'flags': []},
            {'repo': 'o3de/o3de', 'number': 2, 'sig_category': 'sig/build',
             'flags': ['cherry-pick']},
            {'repo': 'o3de/o3de', 'number': 3, 'sig_category': 'uncategorized', 'flags': []},
        ]
        classified = release_notes.classify_for_report(prs)
        assert classified[('o3de/o3de', 1)] is None
        assert classified[('o3de/o3de', 2)] == 'cherry-pick'
        assert classified[('o3de/o3de', 3)] == 'uncategorized'
        # The reconciliation counter must agree with it, by construction.
        counts = release_notes.summarize_render_coverage(prs)
        assert counts['rendered'] == sum(1 for v in classified.values() if v is None)

    def test_sync_labelled_pr_is_no_longer_filtered(self):
        # The class of PR a point-release audit exists to protect: fixes synced
        # to stabilization to make the point release.
        pr = {'repo': 'o3de/o3de', 'number': 19178, 'sig_category': 'sig/build',
              'labels': ['sig/build', 'sync/to-stabilization'], 'flags': []}
        pr['flags'] = release_notes.detect_pr_flags(pr)
        assert release_notes.classify_for_report([pr])[('o3de/o3de', 19178)] is None


class TestFileListTruncation:
    def test_flag_set_when_page_cap_hit(self):
        nodes = [{'path': f'f{i}.cpp'} for i in range(release_notes.FILES_PAGE_SIZE)]
        pr = release_notes._normalize_pr_data({'number': 1, 'files': {'nodes': nodes}}, 'o3de/o3de')
        assert pr['files_truncated'] is True

    def test_flag_clear_for_ordinary_pr(self):
        nodes = [{'path': 'a.cpp'}, {'path': 'b.cpp'}]
        pr = release_notes._normalize_pr_data({'number': 1, 'files': {'nodes': nodes}}, 'o3de/o3de')
        assert pr['files_truncated'] is False

    def test_derivable_from_stored_list_for_older_json(self):
        # Schema 4 files have no files_truncated field; the answer is still
        # recoverable from the stored list, so no re-fetch is needed.
        old = {'files': [f'f{i}.cpp' for i in range(release_notes.FILES_PAGE_SIZE)]}
        assert release_notes.files_possibly_truncated(old) is True
        assert release_notes.files_possibly_truncated({'files': ['a.cpp']}) is False
        assert release_notes.files_possibly_truncated({}) is False

    def test_query_page_size_and_check_cannot_drift(self):
        # The bound in the query string is the same constant the check reads.
        query = release_notes._build_graphql_query([1])
        assert f'files(first: {release_notes.FILES_PAGE_SIZE})' in query
        assert f'labels(first: {release_notes.LABELS_PAGE_SIZE})' in query

    def test_only_file_heuristic_cases_are_called_out(self):
        # A truncated list is harmless when a label decided the SIG.
        prs = [
            {'repo': 'o3de/o3de', 'number': 1, 'files_truncated': True,
             'categorization_source': 'label'},
            {'repo': 'o3de/o3de', 'number': 2, 'files_truncated': True,
             'categorization_source': 'heuristic_files'},
        ]
        at_risk = [f"{p['repo']}#{p['number']}" for p in prs
                   if p.get('files_truncated')
                   and p.get('categorization_source') == 'heuristic_files']
        assert at_risk == ['o3de/o3de#2']


class TestBatchRetryAndClassification:
    """One bad PR number used to cost 30 API calls; a rate limit cost 30 more."""

    @staticmethod
    def _fail(stderr, returncode=1):
        return mock.Mock(returncode=returncode, stdout='', stderr=stderr)

    @staticmethod
    def _ok(numbers):
        payload = {'data': {'repository': {
            f'pr_{n}': {'number': n, 'title': f'PR {n}', 'body': '', 'url': '',
                        'author': {'login': 'x'}, 'mergedAt': '',
                        'labels': {'nodes': []}, 'files': {'nodes': []}}
            for n in numbers}}}
        return mock.Mock(returncode=0, stdout=json.dumps(payload), stderr='')

    def test_unresolvable_number_parsed_from_stderr(self):
        err = 'gh: Could not resolve to a PullRequest with the number of 18886.'
        assert release_notes._unresolvable_pr_numbers(err) == {18886}

    def test_multiple_unresolvable_numbers_parsed(self):
        err = ('Could not resolve to a PullRequest with the number of 1. '
               'Could not resolve to a PullRequest with the number of 2.')
        assert release_notes._unresolvable_pr_numbers(err) == {1, 2}

    @pytest.mark.parametrize('stderr,expected', [
        ('You have exceeded a secondary rate limit', True),
        ('API rate limit exceeded', True),
        ('502 Bad Gateway', True),
        ('connection reset by peer', True),
        ('timed out', True),
        ('Could not resolve to a PullRequest with the number of 5', False),
        ('some unknown failure', False),
    ])
    def test_transient_classification(self, stderr, expected):
        assert release_notes._is_transient_error(stderr) is expected

    def test_backoff_is_exponential_and_capped(self):
        delays = [release_notes._backoff_seconds(i) for i in range(8)]
        assert delays[0] < delays[1] < delays[2]
        assert max(delays) <= release_notes.MAX_BACKOFF_SECONDS

    def test_bad_number_is_dropped_and_batch_retried_not_split(self):
        # The whole point: one unresolvable number must cost ONE extra batch
        # call, not one call per PR in the batch.
        batch = list(range(1, 31))
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                return self._fail('gh: Could not resolve to a PullRequest with the number of 7.')
            return self._ok([n for n in batch if n != 7])

        with mock.patch('release_notes.subprocess.run', side_effect=fake_run), \
             mock.patch('release_notes.time.sleep') as sleep:
            result = release_notes.fetch_pr_metadata_batch('o3de/o3de', batch)

        assert len(calls) == 2, 'should retry the batch once, not split into 30'
        sleep.assert_not_called(), 'a permanent error must not back off'
        assert len(result) == 29
        assert 7 not in {p['number'] for p in result}

    def test_transient_error_backs_off_then_succeeds(self):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                return self._fail('You have exceeded a secondary rate limit')
            return self._ok([1, 2])

        with mock.patch('release_notes.subprocess.run', side_effect=fake_run), \
             mock.patch('release_notes.time.sleep') as sleep:
            result = release_notes.fetch_pr_metadata_batch('o3de/o3de', [1, 2])

        sleep.assert_called_once()
        assert sleep.call_args[0][0] == release_notes._backoff_seconds(0)
        assert len(result) == 2

    def test_retries_are_bounded(self):
        with mock.patch('release_notes.subprocess.run',
                        return_value=self._fail('503 Service Unavailable')) as run, \
             mock.patch('release_notes.time.sleep') as sleep:
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [1])
        assert sleep.call_count == release_notes.MAX_BATCH_ATTEMPTS - 1
        # MAX_BATCH_ATTEMPTS batch tries, then the per-PR fallback for 1 PR.
        assert run.call_count == release_notes.MAX_BATCH_ATTEMPTS + 1

    def test_unknown_error_falls_back_without_retrying(self):
        with mock.patch('release_notes.subprocess.run',
                        return_value=self._fail('something unrecognised')) as run, \
             mock.patch('release_notes.time.sleep') as sleep:
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [1, 2])
        sleep.assert_not_called()
        # one batch attempt, then one call per PR
        assert run.call_count == 3

    def test_success_never_sleeps(self):
        with mock.patch('release_notes.subprocess.run', return_value=self._ok([1])), \
             mock.patch('release_notes.time.sleep') as sleep:
            release_notes.fetch_pr_metadata_batch('o3de/o3de', [1])
        sleep.assert_not_called()

    def test_every_number_unresolvable_gives_up_cleanly(self):
        with mock.patch('release_notes.subprocess.run',
                        return_value=self._fail(
                            'Could not resolve to a PullRequest with the number of 1')), \
             mock.patch('release_notes.time.sleep'):
            assert release_notes.fetch_pr_metadata_batch('o3de/o3de', [1]) == []


class TestLogFileValidation:
    @staticmethod
    def _reset():
        for h in list(release_notes.logger.handlers):
            release_notes.logger.removeHandler(h)

    def test_valid_path_attaches_a_handler(self, tmp_path):
        self._reset()
        target = tmp_path / 'run.log'
        release_notes._configure_logging(False, str(target))
        release_notes.logger.info('hello')
        assert any(isinstance(h, logging.FileHandler)
                   for h in release_notes.logger.handlers)
        assert 'hello' in target.read_text()
        self._reset()

    def test_missing_parent_is_reported_not_raised(self, tmp_path, caplog):
        self._reset()
        bad = tmp_path / 'no_such_dir' / 'run.log'
        with caplog.at_level(logging.ERROR, logger='o3de.release_notes'):
            release_notes._configure_logging(False, str(bad))
        assert any('Invalid --log-file path' in r.getMessage() for r in caplog.records)
        assert not any(isinstance(h, logging.FileHandler)
                       for h in release_notes.logger.handlers)
        self._reset()

    def test_a_bad_log_path_never_aborts_the_run(self, tmp_path):
        # Logging is a convenience; losing it must not cost the release notes.
        self._reset()
        release_notes._configure_logging(False, str(tmp_path / 'nope' / 'x.log'))
        release_notes.logger.info('still working')
        self._reset()

    def test_no_log_file_is_a_noop(self):
        self._reset()
        release_notes._configure_logging(False, None)
        assert not any(isinstance(h, logging.FileHandler)
                       for h in release_notes.logger.handlers)


class TestReuseExisting:
    """Caching must never freeze a wrong SIG for the rest of a cycle."""

    @staticmethod
    def _pr(number, source, sig='sig/build', **extra):
        pr = {'repo': 'o3de/o3de', 'number': number, 'title': f'PR {number}',
              'body': '', 'labels': [], 'files': [], 'sig_category': sig,
              'categorization_source': source}
        pr.update(extra)
        return pr

    def test_only_label_sourced_prs_are_cacheable(self):
        existing = {'pull_requests': [
            self._pr(1, 'label'),
            self._pr(2, 'heuristic_title'),
            self._pr(3, 'heuristic_files'),
            self._pr(4, 'uncategorized', sig='uncategorized'),
        ]}
        cacheable = release_notes.select_cacheable_prs(existing)
        assert set(cacheable) == {('o3de/o3de', 1)}

    def test_uncategorized_pr_is_never_cached(self):
        # The whole point: its sig/ label may have been applied since.
        existing = {'pull_requests': [self._pr(9, 'uncategorized', sig='uncategorized')]}
        assert release_notes.select_cacheable_prs(existing) == {}

    def test_no_existing_report_means_no_cache(self):
        assert release_notes.select_cacheable_prs(None) == {}
        assert release_notes.select_cacheable_prs({'pull_requests': []}) == {}

    def test_derived_fields_are_recomputed_not_trusted(self):
        # A cached PR carrying conclusions from an older version of the tool
        # must be re-derived, or today's heuristic fixes would never reach it.
        stale = {
            'repo': 'o3de/o3de', 'number': 19178,
            'title': 'Fix Clang20 compile errors',
            'body': '', 'labels': ['sig/build', 'sync/to-stabilization'],
            'files': [],
            'sig_category': 'sig/graphics-audio',        # wrong, from an old run
            'categorization_source': 'label',
            'flags': ['stabilization-sync'],             # the retired flag
            'release_machinery': True,                   # wrong
            'description': 'stale text',
        }
        fresh = release_notes.rederive_pr_fields(dict(stale))
        assert fresh['sig_category'] == 'sig/build'
        assert fresh['flags'] == []
        assert fresh['release_machinery'] is False
        assert fresh['description'] == 'Fix Clang20 compile errors.'

    def test_rederive_preserves_raw_github_fields(self):
        pr = self._pr(5, 'label', title='Keep me', body='body text',
                      labels=['sig/build'], files=['a.cpp'])
        out = release_notes.rederive_pr_fields(dict(pr))
        assert out['title'] == 'Keep me'
        assert out['body'] == 'body text'
        assert out['labels'] == ['sig/build']
        assert out['files'] == ['a.cpp']

    def test_rederive_sets_files_truncated(self):
        pr = self._pr(6, 'label', files=[f'f{i}.cpp' for i in range(200)])
        assert release_notes.rederive_pr_fields(dict(pr))['files_truncated'] is True


class TestDuplicateCollapsing:
    """A change that merged twice must appear once, and only on real evidence."""

    @staticmethod
    def _pr(number, title='Fix the thing', sig='sig/build', repo='o3de/o3de',
            files=('a.cpp',), flags=None, machinery=False):
        return {
            'number': number, 'repo': repo, 'title': title,
            'sig_category': sig, 'categorization_source': 'label',
            'description': title, 'files': list(files),
            'flags': list(flags or []), 'release_machinery': machinery,
        }

    def test_identical_change_collapses_to_one(self):
        prs = [self._pr(10), self._pr(20)]
        assert release_notes.classify_reasons(prs) == [None, 'duplicate']

    def test_lower_number_survives(self):
        prs = [self._pr(20), self._pr(10)]
        reasons = release_notes.classify_reasons(prs)
        assert reasons[1] is None and reasons[0] == 'duplicate'

    def test_same_title_different_files_is_not_a_duplicate(self):
        # "Fix build error" recurs on unrelated work across a release window.
        prs = [self._pr(10, files=['a.cpp']), self._pr(20, files=['b.cpp'])]
        assert release_notes.classify_reasons(prs) == [None, None]

    def test_same_title_different_repo_is_not_a_duplicate(self):
        prs = [self._pr(10), self._pr(20, repo='o3de/o3de-extras')]
        assert release_notes.classify_reasons(prs) == [None, None]

    def test_missing_file_list_is_never_collapsed(self):
        # Absent evidence is not evidence of sameness.
        prs = [self._pr(10, files=[]), self._pr(20, files=[])]
        assert release_notes.classify_reasons(prs) == [None, None]

    def test_title_comparison_ignores_case_and_whitespace(self):
        prs = [self._pr(10, title='Fix  the Thing'), self._pr(20, title='fix the thing')]
        assert release_notes.classify_reasons(prs) == [None, 'duplicate']

    def test_categorized_survives_over_uncategorized(self):
        # Keeping the uncategorized member would file the change under
        # Uncategorized or drop it, losing a bullet the report already had.
        prs = [self._pr(10, sig='uncategorized'), self._pr(20, sig='sig/build')]
        reasons = release_notes.classify_reasons(prs, include_uncategorized=True)
        assert reasons[1] is None and reasons[0] == 'duplicate'

    def test_duplicate_of_an_excluded_pr_keeps_the_specific_reason(self):
        # Reporting a cherry-pick as a duplicate would send a curator looking
        # for an original that is itself not in the report.
        prs = [self._pr(10), self._pr(20, flags=['cherry-pick'])]
        assert release_notes.classify_reasons(prs) == [None, 'cherry-pick']

    def test_include_duplicates_keeps_every_copy(self):
        prs = [self._pr(10), self._pr(20)]
        assert release_notes.classify_reasons(prs, include_duplicates=True) == [None, None]

    def test_three_way_duplicate_keeps_exactly_one(self):
        prs = [self._pr(10), self._pr(20), self._pr(30)]
        assert release_notes.classify_reasons(prs).count(None) == 1

    def test_reconciliation_accounts_for_collapsed_prs(self):
        counts = release_notes.summarize_render_coverage([self._pr(10), self._pr(20)])
        assert counts['total'] == 2
        assert counts['rendered'] == 1
        assert counts['excluded_duplicate'] == 1

    def test_buckets_still_sum_to_total(self):
        prs = [self._pr(10), self._pr(20), self._pr(30, files=['z.cpp']),
               self._pr(40, flags=['cherry-pick'], files=['q.cpp'])]
        counts = release_notes.summarize_render_coverage(prs)
        excluded = sum(v for k, v in counts.items() if k.startswith('excluded_'))
        assert counts['rendered'] + excluded == counts['total']

    def test_rendered_markdown_contains_one_bullet(self):
        out = release_notes.render_markdown([self._pr(10), self._pr(20)], '1.0')
        assert out.count('Fix the thing') == 1

    def test_render_and_reconciliation_cannot_disagree(self):
        # The defect class 0.6.2-beta fixed: the audit said a PR was present
        # while the renderer had filtered it. Any filter must be visible to both.
        prs = [self._pr(10), self._pr(20), self._pr(30, files=['z.cpp'])]
        out = release_notes.render_markdown(prs, '1.0')
        counts = release_notes.summarize_render_coverage(prs)
        assert out.count('](https://github.com/o3de/o3de/pull/') == counts['rendered']

    def test_summary_prompt_lists_the_change_once(self):
        prompt = release_notes._build_summary_prompt([self._pr(10), self._pr(20)], '1.0')
        assert prompt.count('Fix the thing') == 1

    def test_collapsed_pairs_are_named_not_just_counted(self, caplog):
        prs = [self._pr(10), self._pr(20)]
        with caplog.at_level(logging.WARNING, logger='o3de.release_notes'):
            release_notes.log_duplicate_groups(prs)
        assert 'kept #10' in caplog.text
        assert '#20' in caplog.text

    def test_no_warning_when_there_are_no_duplicates(self, caplog):
        with caplog.at_level(logging.WARNING, logger='o3de.release_notes'):
            release_notes.log_duplicate_groups([self._pr(10), self._pr(20, files=['z.cpp'])])
        assert 'Duplicate title' not in caplog.text

    def test_audit_counts_a_collapsed_duplicate_as_present(self):
        # The fix reached the reader via its twin's bullet. A checklist that
        # flags present content as missing stops being read.
        prs = [self._pr(10), self._pr(20)]
        classified = release_notes.classify_for_report(prs, include_duplicates=True)
        assert classified[('o3de/o3de', 20)] is None


class TestBuildPathHeuristicCoverage:
    """cmake/ and scripts/ fall to sig/build without shadowing narrower owners."""

    @staticmethod
    def _sig(files):
        pr = {'number': 1, 'repo': 'o3de/o3de', 'title': 'Untitled change',
              'body': '', 'labels': [], 'files': files}
        return release_notes.categorize_pr(pr)

    @pytest.mark.parametrize('path', [
        'cmake/o3deConfigVersion.cmake',
        'cmake/LYPython.cmake',
        'cmake/3rdPartyPackages.cmake',
        'scripts/o3de.sh',
    ])
    def test_loose_build_files_resolve_to_build(self, path):
        # Each of these was uncategorized in the 26.10.0 draft.
        assert self._sig([path])[0] == 'sig/build'

    @pytest.mark.parametrize('path,expected', [
        ('cmake/LYTestWrappers.cmake', 'sig/testing'),
        ('scripts/ctest/run.py', 'sig/testing'),
        ('scripts/o3de/o3de.py', 'sig/core'),
        ('cmake/Platform/Linux/x.cmake', 'sig/build'),
    ])
    def test_specific_owners_still_win(self, path, expected):
        # Longest-match-wins is what makes the catch-alls safe to add.
        assert self._sig([path])[0] == expected
