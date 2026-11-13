# Copyright 2026 The Khronos Group
# SPDX-License-Identifier: Apache-2.0

"""Print where the ANARI SDK shipped in the 'anari' package is installed.

  cmake -Danari_DIR="$(python -m anari --cmake-dir)" ...
"""

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='python -m anari',
        description='Locations of the ANARI SDK shipped in the anari package.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--version', action='store_true',
                       help="the package's version")
    group.add_argument('--sdk-version', action='store_true',
                       help='the ANARI SDK version it ships')
    group.add_argument('--prefix', action='store_true',
                       help='the SDK install prefix')
    group.add_argument('--cmake-dir', action='store_true',
                       help='the directory holding anariConfig.cmake (anari_DIR)')
    group.add_argument('--include-dir', action='store_true',
                       help='the directory holding anari/anari.h')
    group.add_argument('--library-dir', action='store_true',
                       help='the directory holding libanari and the sample devices')
    args = parser.parse_args(argv)

    # Imported here so --help works without loading the extension
    import anari

    if args.version:
        print(anari.__version__)
        return 0
    if args.sdk_version:
        print(anari.sdk_version)
        return 0

    locate = {
        'prefix': anari.sdk_dir,
        'cmake_dir': anari.cmake_dir,
        'include_dir': anari.include_dir,
        'library_dir': anari.library_dir,
    }
    path = next(f for k, f in locate.items() if getattr(args, k))()
    if path is None:
        print('anari: no SDK found in ' + str(anari.__file__), file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
