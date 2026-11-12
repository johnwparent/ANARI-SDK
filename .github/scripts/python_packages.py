#!/usr/bin/env python3
# Copyright 2026 The Khronos Group
# SPDX-License-Identifier: Apache-2.0

"""The Python packages built from this repository, and the checks on their
versions that .github/workflows/python_wheels.yml runs before building.

Every package is versioned in lockstep with the SDK (ANARI_SDK_VERSION in
CMakeLists.txt): a device package's wheel links helium from one SDK release,
so 'anari[all]' pins its device packages with '=='. A packaging-only respin
of a release is a PEP 440 post-release of the SDK version (0.17.0.post1), as
PyPI never accepts a version (or a file name) twice.

  python .github/scripts/python_packages.py [--tag vX.Y.Z] [--require-new]
                                            [--offline] [--github-output FILE]
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

# Each package is a pyproject.toml directory, relative to the repository root.
# To add a device package (e.g. {'name': 'helide', 'dir': 'src/devices/helide'}),
# list it here, give it a Trusted Publisher on PyPI, and only then add it to
# anari's [project.optional-dependencies] (see python_bindings.md).
PACKAGES = [
    {'name': 'anari', 'dir': '.'},
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


def on_pypi(name, version):
    """True if PyPI has this release (even yanked), False if not."""
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
