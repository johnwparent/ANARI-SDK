#!/usr/bin/env python3
# Copyright 2026 The Khronos Group
# SPDX-License-Identifier: Apache-2.0

"""Check the Python packages' versions against the SDK, the tag and PyPI.

Versions are ANARI_SDK_VERSION, or a post-release of it (0.17.0.post1).
"""

import argparse
import json
import pathlib
import re
import sys
import tomllib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Built and published by the workflow; 'dir' holds the pyproject.toml
PACKAGES = [
    {'name': 'anari', 'dir': '.'},
]

# Must require 'anari~=MAJOR.MINOR.0' of the current SDK, to build and to run
ANARI_DEPENDENTS = [
    'examples/empty_helium_device',
]


def sdk_version():
    cmake = (ROOT / 'CMakeLists.txt').read_text()
    return '.'.join(
        re.search(r'set\(ANARI_SDK_VERSION_%s (\d+)\)' % part, cmake).group(1)
        for part in ('MAJOR', 'MINOR', 'PATCH'))


def package_version(package):
    with open(ROOT / package['dir'] / 'pyproject.toml', 'rb') as f:
        project = tomllib.load(f)['project']
    if project['name'] != package['name']:
        sys.exit('%s/pyproject.toml names the package %r, not %r'
                 % (package['dir'], project['name'], package['name']))
    return project['version']


def anari_pins(directory):
    """(where, requirement) for each 'anari' requirement in pyproject.toml."""
    with open(ROOT / directory / 'pyproject.toml', 'rb') as f:
        pyproject = tomllib.load(f)
    found = []
    for where, requirements in (
            ('project.dependencies',
             pyproject.get('project', {}).get('dependencies', [])),
            ('build-system.requires',
             pyproject.get('build-system', {}).get('requires', []))):
        for requirement in requirements:
            if re.match(r'anari\s*([~=<>!;\[]|$)', requirement):
                found.append((where, requirement.replace(' ', '')))
    return found


def on_pypi(name, version):
    """True if PyPI has this release, yanked or not."""
    url = 'https://pypi.org/pypi/%s/%s/json' % (name, version)
    try:
        with urllib.request.urlopen(url, timeout=30):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--tag', help='the release tag being built (vX.Y.Z)')
    parser.add_argument('--require-new', action='store_true',
                        help='fail, instead of warning, if PyPI already has '
                             'a package at this version')
    parser.add_argument('--offline', action='store_true',
                        help="don't ask PyPI")
    parser.add_argument('--github-output', type=pathlib.Path,
                        help='append outputs here ($GITHUB_OUTPUT)')
    args = parser.parse_args()

    errors = []
    sdk = sdk_version()
    versions = {p['name']: package_version(p) for p in PACKAGES}
    for name, version in versions.items():
        print('%s %s (SDK %s)' % (name, version, sdk))
        if not re.fullmatch(re.escape(sdk) + r'(\.post\d+)?', version):
            errors.append('%s is %s: it must be the SDK version %s, or a '
                          'post-release of it (%s.post1, ...)'
                          % (name, version, sdk, sdk))
    if len(set(versions.values())) > 1:
        errors.append('the packages must share one version: %s' % versions)
    version = versions[PACKAGES[0]['name']]

    series = '.'.join(sdk.split('.')[:2]) + '.0'
    for directory in ANARI_DEPENDENTS:
        pins = dict(anari_pins(directory))
        for where in ('project.dependencies', 'build-system.requires'):
            if pins.get(where) != 'anari~=' + series:
                errors.append('%s/pyproject.toml: %s must require '
                              "'anari~=%s' (the SDK's release series), not %r"
                              % (directory, where, series, pins.get(where)))

    if args.tag is not None and args.tag != 'v' + version:
        errors.append('the tag %s is not v%s' % (args.tag, version))

    if not args.offline:
        for name, v in versions.items():
            try:
                published = on_pypi(name, v)
            except (urllib.error.URLError, OSError) as e:
                msg = 'could not ask PyPI about %s %s: %s' % (name, v, e)
                if args.require_new:
                    errors.append(msg)
                else:
                    print('::warning::' + msg)
                continue
            if published:
                msg = ('PyPI already has %s %s, and never accepts a version '
                       'twice: release a new version (or %s.postN for a '
                       'packaging-only respin)' % (name, v, sdk))
                if args.require_new:
                    errors.append(msg)
                else:
                    print('::warning::' + msg)

    for e in errors:
        print('::error::' + e)
    if errors:
        return 1

    if args.github_output:
        with open(args.github_output, 'a') as f:
            f.write('version=%s\n' % version)
            f.write('packages=%s\n' % json.dumps(PACKAGES, separators=(',', ':')))
            f.write('requirements=%s\n' % ' '.join(
                '%s==%s' % (name, v) for name, v in versions.items()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
