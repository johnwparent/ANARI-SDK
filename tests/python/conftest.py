# Copyright 2026 The Khronos Group
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for the 'anari' wheel validation suite.

The suite tests an *installed* anari wheel. Run it from a directory outside
the ANARI-SDK checkout so 'import anari' can only resolve to site-packages.
"""

import os
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent

WIDTH = 64
HEIGHT = 48


def render_tutorial_scene(device):
    """Build and render the scene of examples/python/anari_tutorial_device.py
    (a two-triangle mesh, a camera, a light and a renderer) and return the
    mapped color channel as an ndarray."""
    import anari
    import numpy as np

    device.commitParameters()

    vertex = np.array([
        -1.0, -1.0, 3.0,
        -1.0, 1.0, 3.0,
        1.0, -1.0, 3.0,
        0.1, 0.1, 0.3,
    ], dtype=np.float32)
    color = np.array([
        0.9, 0.5, 0.5, 1.0,
        0.8, 0.8, 0.8, 1.0,
        0.8, 0.8, 0.8, 1.0,
        0.5, 0.9, 0.5, 1.0,
    ], dtype=np.float32)
    index = np.array([0, 1, 2, 1, 2, 3], dtype=np.uint32)

    camera = device.newCamera('perspective')
    camera.setParameter('aspect', anari.FLOAT32, WIDTH / HEIGHT)
    camera.setParameter('position', anari.FLOAT32_VEC3, [0.0, 0.0, 0.0])
    camera.setParameter('direction', anari.FLOAT32_VEC3, [0.1, 0.0, 1.0])
    camera.setParameter('up', anari.FLOAT32_VEC3, [0.0, 1.0, 0.0])
    camera.commitParameters()

    mesh = device.newGeometry('triangle')
    mesh.setParameterArray1D('vertex.position', anari.FLOAT32_VEC3, vertex)
    mesh.setParameterArray1D('vertex.color', anari.FLOAT32_VEC4, color)
    mesh.setParameterArray1D('primitive.index', anari.UINT32_VEC3, index)
    mesh.commitParameters()

    material = device.newMaterial('matte')
    material.setParameter('color', anari.STRING, 'color')
    material.commitParameters()

    surface = device.newSurface()
    surface.setParameter('geometry', anari.GEOMETRY, mesh)
    surface.setParameter('material', anari.MATERIAL, material)
    surface.commitParameters()

    light = device.newLight('directional')
    light.setParameter('direction', anari.FLOAT32_VEC3, [0, 0, 1])
    light.commitParameters()

    world = device.newWorld()
    world.setParameterArray1D('surface', anari.SURFACE, [surface])
    world.setParameterArray1D('light', anari.LIGHT, [light])
    world.commitParameters()

    renderer = device.newRenderer('default')
    renderer.setParameter('background', anari.FLOAT32_VEC4, [1, 1, 1, 1])
    renderer.commitParameters()

    frame = device.newFrame()
    frame.setParameter('size', anari.UINT32_VEC2, [WIDTH, HEIGHT])
    frame.setParameter('channel.color', anari.DATA_TYPE, anari.FLOAT32_VEC4)
    frame.setParameter('renderer', anari.RENDERER, renderer)
    frame.setParameter('camera', anari.CAMERA, camera)
    frame.setParameter('world', anari.WORLD, world)
    frame.commitParameters()

    frame.renderFrame()
    assert frame.frameReady(anari.WAIT)
    return frame.channelAsNdarray('channel.color')


@pytest.fixture
def render_scene():
    return render_tutorial_scene


@pytest.fixture(scope='session')
def empty_device_source():
    """Source of examples/empty_helium_device: $ANARI_EMPTY_DEVICE_SOURCE, or
    its place relative to this directory in an ANARI-SDK tree (or a sparse
    copy of tests/python and examples/empty_helium_device)."""
    env = os.environ.get('ANARI_EMPTY_DEVICE_SOURCE')
    path = pathlib.Path(env) if env else \
        HERE.parent.parent / 'examples' / 'empty_helium_device'
    if not (path / 'CMakeLists.txt').is_file():
        message = 'examples/empty_helium_device not found at ' + str(path)
        if os.environ.get('ANARI_WHEEL_REQUIRE_VENDOR_BUILD'):
            pytest.fail(message)
        pytest.skip(message)
    return path
