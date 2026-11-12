# Copyright 2026 The Khronos Group
# SPDX-License-Identifier: Apache-2.0

"""Validation of an installed 'anari' wheel: the bindings, the frontend, the
sample devices, the shipped device SDK and the wheel's dependencies."""

import importlib
import importlib.metadata
import os
import pathlib
import re
import shutil
import subprocess
import sys
import sysconfig
import warnings

import pytest

import anari

PACKAGE_DIR = pathlib.Path(anari.__file__).resolve().parent

if sys.platform == 'win32':
    SHLIB_SUFFIXES = ('.dll', '.pyd')
elif sys.platform == 'darwin':
    SHLIB_SUFFIXES = ('.dylib', '.so')
else:
    SHLIB_SUFFIXES = ('.so',)


def _shared_libraries(root):
    return sorted(p for p in root.rglob('*')
                  if p.is_file() and (p.suffix in SHLIB_SUFFIXES
                                      or re.search(r'\.so(\.\d+)+$', p.name)))


def _load(name):
    library = anari.loadLibrary(name, anari.error_status_handle)
    assert library is not None, name
    return library


def _device_library(name, directory):
    if sys.platform == 'win32':
        return directory / ('anari_library_%s.dll' % name)
    ext = '.dylib' if sys.platform == 'darwin' else '.so'
    return directory / ('libanari_library_%s%s' % (name, ext))


# Installation ################################################################

def test_imported_from_site_packages():
    """The suite must test the installed wheel, not a source checkout."""
    purelib = pathlib.Path(sysconfig.get_paths()['purelib']).resolve()
    platlib = pathlib.Path(sysconfig.get_paths()['platlib']).resolve()
    assert PACKAGE_DIR.parent in (purelib, platlib), PACKAGE_DIR


def test_version_matches_metadata():
    assert anari.__version__ == importlib.metadata.version('anari')
    # The package's version is the SDK's, or a post-release of it
    assert re.fullmatch(re.escape(anari.sdk_version) + r'(\.post\d+)?',
                        anari.__version__), (anari.__version__, anari.sdk_version)


def test_nothing_grafted_by_wheel_repair():
    """The wheel is self-contained: auditwheel (anari.libs/) and delocate
    (anari/.dylibs/) had nothing outside the wheel to copy in."""
    assert not (PACKAGE_DIR.parent / 'anari.libs').exists()
    assert not (PACKAGE_DIR / '.dylibs').exists()


def test_shipped_sdk_layout():
    sdk = anari.sdk_dir()
    assert sdk is not None and sdk.is_dir()
    assert (anari.cmake_dir() / 'anariConfig.cmake').is_file()
    assert (anari.include_dir() / 'anari' / 'anari.h').is_file()
    assert (anari.include_dir() / 'anari' / 'backend' / 'helium'
            / 'BaseDevice.h').is_file()
    assert (sdk / 'share' / 'anari' / 'code_gen'
            / 'generate_queries.py').is_file()
    for name in ('sink', 'debug'):
        assert _device_library(name, anari.library_dir()).is_file(), name


@pytest.mark.parametrize('option,expected', [
    ('--prefix', lambda: anari.sdk_dir()),
    ('--cmake-dir', lambda: anari.cmake_dir()),
    ('--include-dir', lambda: anari.include_dir()),
    ('--library-dir', lambda: anari.library_dir()),
    ('--version', lambda: anari.__version__),
    ('--sdk-version', lambda: anari.sdk_version),
])
def test_command_line(option, expected):
    out = subprocess.run([sys.executable, '-m', 'anari', option],
                         check=True, capture_output=True, text=True).stdout
    assert out.strip() == str(expected())


# Dependencies ################################################################

# Libraries a wheel may link from the system, beyond its own: the manylinux
# (PEP 600) and musllinux (PEP 656) base libraries, macOS's system libraries
# and Windows' system DLLs. Python itself is never linked on Linux or macOS.
LINUX_SYSTEM_LIBS = re.compile(
    r'^(libc\.so\.6|libm\.so\.6|libdl\.so\.2|libpthread\.so\.0|librt\.so\.1'
    r'|libstdc\+\+\.so\.6|libgcc_s\.so\.1|ld-linux.*\.so\.\d'
    r'|libc\.musl-.*\.so\.1|ld-musl-.*\.so\.1)$')
WINDOWS_SYSTEM_DLLS = re.compile(
    r'^(kernel32|user32|advapi32|shell32|ole32|ws2_32|bcrypt|ntdll'
    r'|api-ms-win-.*|ucrtbase|python3\d*)\.dll$', re.IGNORECASE)


def _needed(path):
    if sys.platform == 'linux':
        from elftools.elf.elffile import ELFFile
        from elftools.elf.dynamic import DynamicSection
        with open(path, 'rb') as f:
            elf = ELFFile(f)
            for section in elf.iter_sections():
                if isinstance(section, DynamicSection):
                    return [t.needed for t in section.iter_tags()
                            if t.entry.d_tag == 'DT_NEEDED']
        return []
    if sys.platform == 'darwin':
        out = subprocess.run(['otool', '-L', str(path)], check=True,
                             capture_output=True, text=True).stdout
        # First line is the file name; for a dylib the next is its own id
        deps = [l.split(' (')[0].strip() for l in out.splitlines()[1:]]
        return [d for d in deps if not d.endswith('/' + path.name)]
    import pefile
    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    return [e.dll.decode() for e in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])]


def test_dependencies_are_in_wheel_or_system():
    libs = _shared_libraries(PACKAGE_DIR)
    shipped = {p.name.lower() for p in libs}
    assert libs
    problems = []
    for lib in libs:
        for dep in _needed(lib):
            name = dep.rsplit('/', 1)[-1]
            if sys.platform == 'darwin':
                ok = (dep.startswith(('/usr/lib/', '/System/Library/'))
                      or (dep.startswith(('@rpath/', '@loader_path/'))
                          and name.lower() in shipped))
            elif sys.platform == 'win32':
                ok = (name.lower() in shipped
                      or WINDOWS_SYSTEM_DLLS.match(name) is not None)
            else:
                ok = (name.lower() in shipped
                      or LINUX_SYSTEM_LIBS.match(name) is not None)
            if not ok:
                problems.append('%s -> %s' % (lib.relative_to(PACKAGE_DIR), dep))
    assert not problems, 'dependencies outside the wheel:\n' + '\n'.join(problems)


LOAD_ALL_SCRIPT = """
import ctypes, os, sys
package_dir, library_dir, libraries = sys.argv[1], sys.argv[2], sys.argv[3:]
if sys.platform == 'win32':
    # Imports are always bound at load on Windows; search the directories of
    # the bundled MSVC runtime (next to the extension) and of anari.dll
    handles = [os.add_dll_directory(package_dir),
               os.add_dll_directory(library_dir)]
    mode = 0
else:
    mode = os.RTLD_NOW | os.RTLD_LOCAL
for library in libraries:
    ctypes.CDLL(library, mode=mode)
"""


def _assert_loads_with_all_symbols_bound(libraries):
    """Load the libraries with every symbol bound, in a separate process:
    libraries left loaded here would let the later tests pass even where the
    frontend couldn't find or load them itself."""
    result = subprocess.run(
        [sys.executable, '-c', LOAD_ALL_SCRIPT, str(PACKAGE_DIR),
         str(anari.library_dir())] + [str(p) for p in libraries],
        capture_output=True, text=True)
    assert result.returncode == 0, (result.returncode, result.stderr)


def test_every_shared_library_loads_with_all_symbols_bound():
    """RTLD_NOW resolves every symbol at load, so a missing symbol or library
    fails here instead of on first use (the frontend loads with RTLD_LAZY)."""
    libraries = _shared_libraries(PACKAGE_DIR)
    assert libraries
    _assert_loads_with_all_symbols_bound(libraries)


def _macos_wheel_tag():
    """(minimum macOS version, architecture) from the installed wheel's tag,
    e.g. macosx_11_0_arm64 -> ((11, 0), 'arm64')."""
    wheel = importlib.metadata.distribution('anari').read_text('WHEEL')
    tags = re.findall(r'^Tag: .*-macosx_(\d+)_(\d+)_(\w+)$', wheel, re.M)
    assert tags, wheel
    major, minor, arch = tags[0]
    return (int(major), int(minor)), arch


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS wheels only')
def test_macos_binaries_match_the_wheel_tag():
    """Every Mach-O binary, the static SDK libraries too, is built for the
    wheel's architecture only and needs no newer macOS than its tag says
    (MACOSX_DEPLOYMENT_TARGET, ARCHFLAGS)."""
    minimum, arch = _macos_wheel_tag()
    binaries = [p for p in PACKAGE_DIR.rglob('*') if p.is_file()
                and p.suffix in ('.so', '.dylib', '.a')]
    assert binaries
    problems = []
    for path in binaries:
        archs = subprocess.run(['lipo', '-archs', str(path)], check=True,
                               capture_output=True, text=True).stdout.split()
        if archs != [arch]:
            problems.append('%s: built for %s' % (path.name, archs))
        commands = subprocess.run(['otool', '-l', str(path)], check=True,
                                  capture_output=True, text=True).stdout
        for version in re.findall(r'\bminos (\d+)\.(\d+)', commands):
            if tuple(map(int, version)) > minimum:
                problems.append('%s: needs macOS %s.%s' % ((path.name,) + version))
    assert not problems, '\n'.join(sorted(set(problems)))


# Bindings and frontend #######################################################

def test_bindings_enums():
    assert anari.FLOAT32_VEC3 == anari.lib.ANARI_FLOAT32_VEC3
    assert anari.WAIT == anari.lib.ANARI_WAIT


def test_missing_library_is_reported_not_raised():
    assert anari.loadLibrary('no_such_anari_library',
                             anari.error_status_handle) is None


def test_environment_library(monkeypatch):
    monkeypatch.setenv('ANARI_LIBRARY', 'sink')
    library = _load('environment')
    assert 'default' in library.getDeviceSubtypes()


# Python frees objects in any order, at exit too, and freeing a Library unloads
# its device library (anariUnloadLibrary): the bindings keep a device's
# Library alive while anything made from it is, including through another
# object's parameters (a debug device's wrappedDevice). In a subprocess, as
# the crash this guards against happens at interpreter exit.
OBJECT_LIFETIME_SCRIPTS = {
    'objects outlive their device and library': """
import sys, anari
library = anari.loadLibrary(sys.argv[1], anari.error_status_handle)
device = library.newDevice('default')
camera = device.newCamera('perspective')
world = device.newWorld()
del library, device
""",
    'a device held only as a parameter': """
import anari
sink = anari.loadLibrary('sink', anari.error_status_handle).newDevice('default')
debug = anari.loadLibrary('debug', anari.error_status_handle).newDevice('default')
debug.setParameter('wrappedDevice', anari.DEVICE, sink)
debug.commitParameters()
camera = debug.newCamera('perspective')
del sink
""",
}


@pytest.mark.parametrize('name', ['sink', 'debug'])
@pytest.mark.parametrize('script', sorted(OBJECT_LIFETIME_SCRIPTS))
def test_objects_keep_their_library_loaded(script, name):
    env = dict(os.environ, ANARI_DEBUG_WRAPPED_LIBRARY='sink')
    result = subprocess.run(
        [sys.executable, '-c', OBJECT_LIFETIME_SCRIPTS[script], name],
        capture_output=True, text=True, env=env)
    assert result.returncode == 0, (result.returncode, result.stderr)


# Sample devices ##############################################################

def test_sink_introspection():
    library = _load('sink')
    assert library.getDeviceSubtypes()
    device = library.newDevice('default')
    assert device.getObjectSubtypes(anari.GEOMETRY)


def test_scene_on_sink(render_scene):
    from conftest import HEIGHT, WIDTH
    device = _load('sink').newDevice('default')
    pixels = render_scene(device)
    assert pixels.shape == (HEIGHT, WIDTH, 4)


def test_scene_on_debug_wrapping_sink(render_scene):
    from conftest import HEIGHT, WIDTH
    sink = _load('sink').newDevice('default')
    debug = _load('debug').newDevice('default')
    debug.setParameter('wrappedDevice', anari.DEVICE, sink)
    pixels = render_scene(debug)
    assert pixels.shape == (HEIGHT, WIDTH, 4)


def test_scene_on_debug_wrapping_from_environment(monkeypatch, render_scene):
    """The debug device loads ANARI_DEBUG_WRAPPED_LIBRARY through the shipped
    shared libanari, which finds sink next to it."""
    from conftest import HEIGHT, WIDTH
    monkeypatch.setenv('ANARI_DEBUG_WRAPPED_LIBRARY', 'sink')
    debug = _load('debug').newDevice('default')
    pixels = render_scene(debug)
    assert pixels.shape == (HEIGHT, WIDTH, 4)


# Vendor device built against the wheel #######################################

def _cmake():
    """The environment's own cmake (the 'cmake' package of requirements.txt)
    first, then one on PATH."""
    cmake = shutil.which('cmake', path=sysconfig.get_path('scripts')) \
        or shutil.which('cmake')
    if cmake is None:
        if os.environ.get('ANARI_WHEEL_REQUIRE_VENDOR_BUILD'):
            pytest.fail('cmake not found')
        pytest.skip('cmake not found')
    return cmake


@pytest.fixture(scope='session')
def vendor_device(tmp_path_factory, empty_device_source):
    """Build examples/empty_helium_device ('hecore') with nothing but the
    wheel: its headers, static helium/anari_backend, CMake package and
    code_gen (anari_generate_queries())."""
    cmake = _cmake()
    build = tmp_path_factory.mktemp('hecore')
    subprocess.run([
        cmake, '-S', str(empty_device_source), '-B', str(build),
        '-DCMAKE_BUILD_TYPE=Release',
        '-Danari_DIR=' + str(anari.cmake_dir()),
        '-DPython3_EXECUTABLE=' + sys.executable,
    ], check=True)
    subprocess.run([cmake, '--build', str(build), '--config', 'Release',
                    '--parallel'], check=True)
    found = [p for p in build.rglob('*')
             if p.name == _device_library('hecore', p.parent).name]
    assert found, 'no hecore library built in ' + str(build)
    return found[0]


def test_vendor_device_builds_and_renders(vendor_device, render_scene):
    from conftest import HEIGHT, WIDTH
    _assert_loads_with_all_symbols_bound([vendor_device])
    library = _load('hecore,' + str(vendor_device.parent) + os.sep)
    pixels = render_scene(library.newDevice('default'))
    assert pixels.shape[:2] == (HEIGHT, WIDTH)


# Vendor device packaged for Python ###########################################

@pytest.fixture(scope='session')
def device_package(tmp_path_factory, empty_device_source):
    """pip install examples/empty_helium_device as the 'hecore' Python package
    (its pyproject.toml): built by py-build-cmake against the installed 'anari'
    package, its build requirement and dependency, with nothing downloaded."""
    cmake = _cmake()
    source = tmp_path_factory.mktemp('hecore_package') / 'hecore'
    shutil.copytree(empty_device_source, source)
    env = dict(os.environ)
    env['PATH'] = os.path.dirname(cmake) + os.pathsep + env.get('PATH', '')
    # --no-build-isolation: build with this environment's py-build-cmake and
    # anari; --no-index: the 'anari' dependency must be the installed one
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    '--no-build-isolation', '--no-index', str(source)],
                   check=True, env=env)
    yield
    # Best effort: on Windows the loaded anari_library_hecore.dll can't be
    # deleted, which mustn't turn a passing session into a teardown error
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'uninstall', '-y', 'hecore'],
        capture_output=True, text=True)
    if result.returncode != 0:
        warnings.warn('could not uninstall hecore: ' + result.stderr)


def test_device_package_installs_and_renders(device_package, render_scene):
    from conftest import HEIGHT, WIDTH
    importlib.invalidate_caches()  # installed after this process started
    import hecore
    location = pathlib.Path(hecore.__file__).resolve().parent
    assert location.parent == PACKAGE_DIR.parent  # next to anari
    assert any(re.match(r'anari\b', r)
               for r in importlib.metadata.requires('hecore'))
    assert hecore.library is not None
    pixels = render_scene(hecore.newDevice())
    assert pixels.shape[:2] == (HEIGHT, WIDTH)
