## Copyright 2024-2026 The Khronos Group
## SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.11)

if (${CMAKE_SOURCE_DIR} STREQUAL ${CMAKE_CURRENT_LIST_DIR})
  set(STANDALONE_SOURCE_TREE TRUE)
else()
  set(STANDALONE_SOURCE_TREE FALSE)
endif()

if (STANDALONE_SOURCE_TREE)
  message(STATUS "CMake version: ${CMAKE_VERSION}")
endif()

## Language setup ##

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(CMAKE_BUILD_TYPE_INIT Release)

set(CMAKE_INSTALL_RPATH "$ORIGIN")
set(CMAKE_INSTALL_MESSAGE LAZY)

## Establish project ##

project(anari_library_hecore LANGUAGES CXX)

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})

include(GNUInstallDirs)

## Dependencies ##

# Built on its own as a Python package (pip install, see pyproject.toml): use
# the ANARI SDK shipped in the 'anari' package that the build depends on, which
# is also the one the device will load into. (Inside the SDK's tree,
# cmake/Findanari.cmake provides anari instead.)
if (STANDALONE_SOURCE_TREE AND DEFINED PY_BUILD_CMAKE_VERSION AND NOT anari_DIR)
  execute_process(
    COMMAND ${PY_BUILD_CMAKE_BUILD_PYTHON_INTERPRETER} -m anari --cmake-dir
    OUTPUT_VARIABLE anari_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE ANARI_PYTHON_PACKAGE_RESULT
  )
  if (NOT ANARI_PYTHON_PACKAGE_RESULT EQUAL 0)
    message(FATAL_ERROR "the 'anari' Python package was not found: it is a "
      "build requirement in pyproject.toml")
  endif()
endif()

find_package(anari REQUIRED)


## Build device target ##

add_library(${PROJECT_NAME} SHARED
  HeCoreDevice.cpp
  HeCoreDeviceGlobalState.cpp
  HeCoreLibrary.cpp
  Object.cpp
  camera/Camera.cpp
  frame/Frame.cpp
  geometry/Geometry.cpp
  light/Light.cpp
  material/Material.cpp
  renderer/Renderer.cpp
  sampler/Sampler.cpp
  spatial_field/SpatialField.cpp
  surface/Surface.cpp
  volume/Volume.cpp
  world/Group.cpp
  world/Instance.cpp
  world/World.cpp
)

target_link_libraries(${PROJECT_NAME} PRIVATE anari::helium)

include(GenerateExportHeader)
generate_export_header(${PROJECT_NAME} EXPORT_MACRO_NAME "HECORE_EXPORT")

target_include_directories(${PROJECT_NAME}
PRIVATE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_LIST_DIR}>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>
)

## Code generation ##

anari_generate_queries(
  DEVICE_TARGET ${PROJECT_NAME}
  CPP_NAMESPACE hecore
  JSON_DEFINITIONS_FILE ${CMAKE_CURRENT_SOURCE_DIR}/HeCoreDefinitions.json
)

## Python package ##

# The device library and a module that loads it (code_gen's
# device_trampoline.py.in), installed as the 'hecore' Python package by
# pyproject.toml (install_components): 'import hecore; hecore.newDevice()'
set(DEVICE_LIBRARY_NAME hecore)
configure_file(${ANARI_CODE_GEN_ROOT}/device_trampoline.py.in
  ${CMAKE_CURRENT_BINARY_DIR}/__init__.py)

install(
  FILES ${CMAKE_CURRENT_BINARY_DIR}/__init__.py
  EXCLUDE_FROM_ALL
  COMPONENT hecore_module
  DESTINATION hecore
)
install(TARGETS ${PROJECT_NAME}
  EXCLUDE_FROM_ALL
  COMPONENT hecore_module
  LIBRARY DESTINATION hecore
  RUNTIME DESTINATION hecore
)
