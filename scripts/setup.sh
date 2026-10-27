#!/bin/bash
# Build BranchPlay on this Mac and leave it ready to open.
# Apple Silicon only. Run from anywhere: scripts/setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "BranchPlay setup is for Apple Silicon Macs." >&2
  exit 1
fi
if ! command -v clang >/dev/null 2>&1 || ! command -v swiftc >/dev/null 2>&1; then
  echo "Xcode or the Command Line Tools are required (clang and swiftc)." >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh" >&2
  exit 1
fi
export PATH="$(brew --prefix)/bin:$PATH"

# Install only when the tool is missing. brew install upgrades a formula
# that is already present, and that upgrade is not required to build.
brew_install_missing() {
  echo "==> Homebrew: $1"
  brew install "$1"
}

PREFIX="$ROOT/.deps/prefix"
SRC="$ROOT/.deps/src"
mkdir -p "$PREFIX/bin" "$PREFIX/include/SDL2" "$PREFIX/lib" "$SRC"
JOBS="$(sysctl -n hw.ncpu)"

find_python() {
  local candidate
  for candidate in \
    "${PYTHON_FOR_BRANCHPLAY:-}" \
    /opt/homebrew/opt/python@3.11/bin/python3.11 \
    /usr/local/opt/python@3.11/bin/python3.11 \
    "$(command -v python3.11 || true)"
  do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! SYS_PY="$(find_python)"; then
  brew_install_missing python@3.11
  hash -r
  if ! SYS_PY="$(find_python)"; then
    echo "Python 3.11 is still missing after: brew install python@3.11" >&2
    exit 1
  fi
fi

download() {
  local url="$1" dest="$2"
  if [[ ! -f "$dest" ]]; then
    echo "==> $(basename "$dest")"
    curl -L --fail --retry 3 -o "$dest" "$url"
  fi
}

if [[ ! -x "$PREFIX/bin/cmake" ]]; then
  echo "==> CMake"
  download \
    https://github.com/Kitware/CMake/releases/download/v3.31.8/cmake-3.31.8-macos-universal.tar.gz \
    "$SRC/cmake-3.31.8-macos-universal.tar.gz"
  tar -xzf "$SRC/cmake-3.31.8-macos-universal.tar.gz" -C "$SRC"
  ln -sfn "$SRC/cmake-3.31.8-macos-universal/CMake.app/Contents/bin/cmake" "$PREFIX/bin/cmake"
fi
CMAKE="$PREFIX/bin/cmake"

# The engine looks for SDL2, SDL2_image, SDL2_ttf, and SDL2_gfx.
# A Homebrew SDL2 is used when it is already installed. The other three
# are built into this checkout so setup does not have to write to Homebrew.
SDL2_PREFIX=""
for candidate in /opt/homebrew /usr/local; do
  if [[ -f "$candidate/lib/libSDL2.dylib" || -f "$candidate/lib/libSDL2.0.dylib" ]]; then
    SDL2_PREFIX="$candidate"
    break
  fi
done
if [[ -z "$SDL2_PREFIX" ]]; then
  brew_install_missing sdl2-compat
  for candidate in /opt/homebrew /usr/local "$(brew --prefix)"; do
    if [[ -f "$candidate/lib/libSDL2.dylib" || -f "$candidate/lib/libSDL2.0.dylib" ]]; then
      SDL2_PREFIX="$candidate"
      break
    fi
  done
fi
if [[ -z "$SDL2_PREFIX" ]]; then
  echo "SDL2 is still missing after: brew install sdl2-compat" >&2
  exit 1
fi

if [[ ! -f "$PREFIX/lib/libSDL2_image.dylib" ]]; then
  echo "==> SDL2_image"
  download \
    https://github.com/libsdl-org/SDL_image/releases/download/release-2.8.8/SDL2_image-2.8.8.tar.gz \
    "$SRC/SDL2_image-2.8.8.tar.gz"
  rm -rf "$SRC/SDL2_image-2.8.8" "$SRC/SDL2_image-build"
  tar -xzf "$SRC/SDL2_image-2.8.8.tar.gz" -C "$SRC"
  "$CMAKE" -S "$SRC/SDL2_image-2.8.8" -B "$SRC/SDL2_image-build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_PREFIX_PATH="$SDL2_PREFIX" \
    -DSDL2_DIR="$SDL2_PREFIX/lib/cmake/SDL2" \
    -DBUILD_SHARED_LIBS=ON \
    -DSDL2IMAGE_VENDORED=OFF \
    -DSDL2IMAGE_BACKEND_STB=ON \
    -DSDL2IMAGE_SAMPLES=OFF \
    -DSDL2IMAGE_TESTS=OFF \
    -DSDL2IMAGE_AVIF=OFF \
    -DSDL2IMAGE_JXL=OFF \
    -DSDL2IMAGE_TIF=OFF \
    -DSDL2IMAGE_WEBP=OFF \
    -DSDL2IMAGE_DEPS_SHARED=OFF
  "$CMAKE" --build "$SRC/SDL2_image-build" -j "$JOBS"
  "$CMAKE" --install "$SRC/SDL2_image-build"
fi

if [[ ! -f "$PREFIX/lib/libSDL2_ttf.dylib" ]]; then
  echo "==> SDL2_ttf"
  download \
    https://github.com/libsdl-org/SDL_ttf/releases/download/release-2.24.0/SDL2_ttf-2.24.0.tar.gz \
    "$SRC/SDL2_ttf-2.24.0.tar.gz"
  rm -rf "$SRC/SDL2_ttf-2.24.0" "$SRC/SDL2_ttf-build"
  tar -xzf "$SRC/SDL2_ttf-2.24.0.tar.gz" -C "$SRC"
  "$CMAKE" -S "$SRC/SDL2_ttf-2.24.0" -B "$SRC/SDL2_ttf-build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_PREFIX_PATH="$SDL2_PREFIX" \
    -DSDL2_DIR="$SDL2_PREFIX/lib/cmake/SDL2" \
    -DBUILD_SHARED_LIBS=ON \
    -DSDL2TTF_VENDORED=ON \
    -DSDL2TTF_HARFBUZZ=OFF \
    -DSDL2TTF_SAMPLES=OFF
  "$CMAKE" --build "$SRC/SDL2_ttf-build" -j "$JOBS"
  "$CMAKE" --install "$SRC/SDL2_ttf-build"
fi

if [[ ! -f "$PREFIX/lib/libSDL2_gfx.dylib" ]]; then
  echo "==> SDL2_gfx"
  download \
    https://sourceforge.net/projects/sdl2gfx/files/SDL2_gfx-1.0.4.tar.gz/download \
    "$SRC/SDL2_gfx-1.0.4.tar.gz"
  rm -rf "$SRC/SDL2_gfx-1.0.4"
  tar -xzf "$SRC/SDL2_gfx-1.0.4.tar.gz" -C "$SRC"
  # The GitHub tag unpacks as SDL2_gfx-1.0.4.
  clang -dynamiclib -fPIC -O2 \
    -I"$SDL2_PREFIX/include/SDL2" \
    -install_name "$PREFIX/lib/libSDL2_gfx.dylib" \
    -o "$PREFIX/lib/libSDL2_gfx.dylib" \
    "$SRC/SDL2_gfx-1.0.4/SDL2_framerate.c" \
    "$SRC/SDL2_gfx-1.0.4/SDL2_gfxPrimitives.c" \
    "$SRC/SDL2_gfx-1.0.4/SDL2_imageFilter.c" \
    "$SRC/SDL2_gfx-1.0.4/SDL2_rotozoom.c" \
    -L"$SDL2_PREFIX/lib" -lSDL2
  cp "$SRC/SDL2_gfx-1.0.4"/SDL2_gfxPrimitives.h \
     "$SRC/SDL2_gfx-1.0.4"/SDL2_framerate.h \
     "$SRC/SDL2_gfx-1.0.4"/SDL2_imageFilter.h \
     "$SRC/SDL2_gfx-1.0.4"/SDL2_rotozoom.h \
     "$PREFIX/include/SDL2/"
fi

if [[ ! -f "$PREFIX/lib/libboost_python311.dylib" ]]; then
  echo "==> Boost"
  download \
    https://archives.boost.io/release/1.86.0/source/boost_1_86_0.tar.gz \
    "$SRC/boost_1_86_0.tar.gz"
  rm -rf "$SRC/boost_1_86_0"
  tar -xzf "$SRC/boost_1_86_0.tar.gz" -C "$SRC"
  PY_INC="$("$SYS_PY" -c 'import sysconfig; print(sysconfig.get_path("include"))')"
  PY_LIB="$("$SYS_PY" -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')"
  cat > "$SRC/boost_1_86_0/user-config.jam" << EOF
using python : 3.11 : $SYS_PY : $PY_INC : $PY_LIB ;
EOF
  (
    cd "$SRC/boost_1_86_0"
    ./bootstrap.sh --prefix="$PREFIX" \
      --with-libraries=filesystem,system,thread,python \
      --with-python="$SYS_PY"
    ./b2 -j "$JOBS" \
      --user-config="$SRC/boost_1_86_0/user-config.jam" \
      --prefix="$PREFIX" \
      toolset=clang \
      cxxstd=14 \
      link=shared \
      runtime-link=shared \
      visibility=global \
      install
  )
fi

echo "==> Python environment"
VENV="$ROOT/GRF/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$SYS_PY" -m venv "$VENV"
fi
PY="$VENV/bin/python"
"$PY" -m pip install --upgrade pip
# gym 0.21's metadata uses specifiers current packaging rejects.
"$PY" -m pip install "setuptools==65.5.0" "wheel==0.38.4" "packaging==21.3"
"$PY" -m pip install --no-build-isolation -r "$ROOT/GRF/requirements.txt"
"$PY" -m pip install -r "$ROOT/viewer/requirements.txt"

echo "==> Game engine"
export PATH="$PREFIX/bin:$PATH"
export PYTHON="$SYS_PY"
export PYTHON_ROOT="$(cd "$(dirname "$SYS_PY")/.." && pwd)"
export BOOST_ROOT="$PREFIX"
export CMAKE_PREFIX_PATH="$PREFIX:$SDL2_PREFIX"
export SDL2DIR="$SDL2_PREFIX"
# Link and load from this checkout. Homebrew's lib directory is not added:
# ImageIO then picks up Homebrew image libraries and the window dies.
export DYLD_LIBRARY_PATH="$PREFIX/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
# Keep CMake off any other Python, such as a conda install earlier on PATH.
export CMAKE_IGNORE_PATH="${CMAKE_IGNORE_PATH:-}"
if [[ -d "$HOME/miniconda3" ]]; then
  export CMAKE_IGNORE_PATH="$HOME/miniconda3${CMAKE_IGNORE_PATH:+:$CMAKE_IGNORE_PATH}"
fi
if [[ -d "$HOME/anaconda3" ]]; then
  export CMAKE_IGNORE_PATH="$HOME/anaconda3${CMAKE_IGNORE_PATH:+:$CMAKE_IGNORE_PATH}"
fi
(
  cd "$ROOT/GRF"
  PYTHON="$SYS_PY" PYTHON_ROOT="$PYTHON_ROOT" BOOST_ROOT="$PREFIX" \
    "$PY" -m pip install . --no-deps --no-build-isolation
)

echo "==> Match controls"
if [[ ! -x "$ROOT/viewer/overlay" || "$ROOT/viewer/overlay.swift" -nt "$ROOT/viewer/overlay" ]]; then
  swiftc -O -o "$ROOT/viewer/overlay" "$ROOT/viewer/overlay.swift" \
    -framework Cocoa -framework QuartzCore -framework WebKit
fi

echo "==> Phi-4 mini"
if ! command -v ollama >/dev/null 2>&1; then
  brew_install_missing ollama
  hash -r
  export PATH="$(brew --prefix ollama)/bin:$PATH"
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is still missing after: brew install ollama" >&2
  exit 1
fi
if ! curl -sf -o /dev/null http://127.0.0.1:11434/api/tags; then
  ollama serve >/tmp/branchplay-ollama.log 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if curl -sf -o /dev/null http://127.0.0.1:11434/api/tags; then
      break
    fi
    sleep 1
  done
fi
if ! curl -sf -o /dev/null http://127.0.0.1:11434/api/tags; then
  echo "Ollama is not answering on 127.0.0.1:11434. Start it, then run: ollama pull phi4-mini" >&2
  exit 1
fi
ollama pull phi4-mini

echo "SETUP_OK"
echo "Open BranchPlay.app, or run:"
echo "  DYLD_LIBRARY_PATH=\"$PREFIX/lib\" \"$PY\" -u viewer/watch.py"
