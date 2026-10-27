#!/bin/bash
# Copyright 2019 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

LIB_EXTENSION="so"

if [[ "$OSTYPE" == "darwin"* ]] ; then
    LIB_EXTENSION="dylib"
fi

# Prefer a memory-aware job count. A fresh environment does not have psutil yet.
if ! PARALLELISM=$(python3 -c 'import psutil; import multiprocessing as mp; print(int(max(1,min((psutil.virtual_memory().available/1000000000-1)/0.5, mp.cpu_count()))))' 2>/dev/null); then
  PARALLELISM=$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)
fi

# Delete pre-existing version of CMakeCache.txt to make 'python3 -m pip install' work.
rm -f third_party/gfootball_engine/CMakeCache.txt
CMAKE_ARGS=()
# setup.sh sets these so the engine links the Python and Boost from this checkout,
# not whatever CMake finds first on the machine.
if [[ -n "${PYTHON:-}" ]]; then
  PY_INCLUDE="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
  PY_LIBDIR="$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')"
  PY_VER="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  CMAKE_ARGS+=(
    -DPython_EXECUTABLE="${PYTHON}"
    -DPython3_EXECUTABLE="${PYTHON}"
    -DPython_FIND_STRATEGY=LOCATION
    -DPython_INCLUDE_DIR="${PY_INCLUDE}"
    -DPython_LIBRARY="${PY_LIBDIR}/libpython${PY_VER}.dylib"
  )
  echo "Engine Python: ${PYTHON}"
fi
if [[ -n "${PYTHON_ROOT:-}" ]]; then
  CMAKE_ARGS+=(-DPython_ROOT_DIR="${PYTHON_ROOT}" -DPython3_ROOT_DIR="${PYTHON_ROOT}")
fi
if [[ -n "${BOOST_ROOT:-}" ]]; then
  CMAKE_ARGS+=(
    -DBOOST_ROOT="${BOOST_ROOT}"
    -DBoost_NO_SYSTEM_PATHS=ON
    -DCMAKE_BUILD_RPATH="${BOOST_ROOT}/lib"
    -DCMAKE_INSTALL_RPATH="${BOOST_ROOT}/lib"
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON
  )
fi
# A failed configure must not leave this shell inside the engine directory.
(
  cd third_party/gfootball_engine
  cmake "${CMAKE_ARGS[@]}" .
  make -j "$PARALLELISM"
)
ln -sf "libgame.$LIB_EXTENSION" third_party/gfootball_engine/_gameplayfootball.so
