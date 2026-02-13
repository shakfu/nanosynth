#!/bin/sh
# Apply all SC patches for building libscsynth as a subdirectory.
# Run from the SC source directory. Pass the patches directory as $1.
set -e

PATCHES_DIR="$1"

# 1. Reentrant-world fixes (C++ source patches for World lifecycle)
patch -p1 -N -i "$PATCHES_DIR/sc-reentrant-world.patch" || true

# 2. Fix CMAKE_SOURCE_DIR for subdirectory builds.
#    SC's cmake uses CMAKE_SOURCE_DIR to locate sources in common/, include/,
#    etc. When SC is a subdirectory (FetchContent), CMAKE_SOURCE_DIR points to
#    the parent project. PROJECT_SOURCE_DIR is set by SC's project() call and
#    always resolves to SC's own root -- use it instead.
find . \( -name 'CMakeLists.txt' -o -name '*.cmake' \) \
    -exec sed -i.bak 's|\${CMAKE_SOURCE_DIR}|\${PROJECT_SOURCE_DIR}|g' {} +

# 3. Remove sclang/platform/editors subdirectories (not needed for libscsynth)
sed -i.bak \
    -e '/^add_subdirectory(lang)$/d' \
    -e '/^add_subdirectory(platform)$/d' \
    -e '/^add_subdirectory(editors)$/d' \
    CMakeLists.txt

# 4. Strip SC's own install() rules to prevent wheel pollution.
#    We install only what we need from our top-level CMakeLists.txt.
for f in server/scsynth/CMakeLists.txt server/plugins/CMakeLists.txt; do
    if [ -f "$f" ]; then
        sed -i.bak '/^[[:space:]]*install(/,/)/d' "$f"
    fi
done

# Cleanup sed backup files
find . -name '*.bak' -delete
