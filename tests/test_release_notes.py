#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 OR MIT
# Copyright 2026 Nick Schuetz

import json
import pathlib
import subprocess
from unittest import mock

import pytest

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

    def test_sync_label(self):
        pr = {'title': 'Some fix', 'labels': ['sync/to-development']}
        assert 'stabilization-sync' in release_notes.detect_pr_flags(pr)

    def test_normal_pr(self):
        pr = {'title': 'Fix a bug in rendering', 'labels': []}
        assert release_notes.detect_pr_flags(pr) == []


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
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
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
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=1, stdout='', stderr='error')
                result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None

    def test_timeout(self):
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 120)):
                result = release_notes.generate_summary([], '1.0', 'ollama run qwen2.5:32b')
        assert result is None

    def test_empty_output(self):
        with mock.patch('release_notes.shutil.which', return_value='/usr/local/bin/ollama'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
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
        with mock.patch('release_notes.shutil.which', return_value='/x/y'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
                mock_run.return_value = mock.Mock(returncode=0, stdout='ok', stderr='')
                result = release_notes.generate_summary([], '1.0', 'x', timeout=60)
        assert result == 'ok'

    def test_passes_timeout_to_subprocess(self):
        with mock.patch('release_notes.shutil.which', return_value='/x/y'):
            with mock.patch('release_notes.subprocess.run') as mock_run:
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
            default_repo_path=str(repo_dir),
            output_json=str(out_json),
            dry_run=True,
        )
        with mock.patch('release_notes._check_gh_available') as mock_check:
            with mock.patch('release_notes.subprocess.run') as mock_run:
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
            assert '100+' in mock_logger.warning.call_args[0][0]


class TestSchemaVersion:
    def test_schema_version_is_3(self):
        # Bumped from 2 -> 3 when release_machinery flag and merge-base metadata
        # were added. Existing JSON at schema 2 is still readable
        # (load_existing_json accepts SCHEMA_VERSION and SCHEMA_VERSION - 1).
        assert release_notes.SCHEMA_VERSION == 3


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
        assert '2 accounted for' in content

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
        assert '1 accounted for' in content


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
