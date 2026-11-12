# The HeCore empty device

This directory contains an empty, minimal device using libhelium that is
intended to be copied/renamed as a starting point for new devices. Various notes
can be found as code comments for why various items exist.

It's worth knowing that because helide is also based on libhelium, it can show
how such a device is filled out with actual implementation. Of course all
rendering implementation choices made by helide are not universal and ought to
be reconsidered by the reader.

## Building

With an installed ANARI SDK (`find_package(anari)`):

```
cmake -S . -B build -Danari_DIR=<prefix>/lib/cmake/anari-<version>
cmake --build build
```

or against the SDK in the `anari` Python package:
`-Danari_DIR="$(python -m anari --cmake-dir)"`.

## Python package

`pyproject.toml` packages the device as the `hecore` Python package, built
against the SDK in the `anari` package (a build requirement and dependency):

```
pip install .
python -c "import hecore; device = hecore.newDevice()"
```
