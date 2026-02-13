cmake_minimum_required(VERSION 3.28...3.31)
project(${SKBUILD_PROJECT_NAME} VERSION ${SKBUILD_PROJECT_VERSION} LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

# --- _osc: OSC encode/decode ---
nanobind_add_module(_osc src/nanosynth/_osc.cpp)
if(MSVC)
    target_compile_options(_osc PRIVATE /W4)
else()
    target_compile_options(_osc PRIVATE -Wall -Wextra)
endif()
install(TARGETS _osc DESTINATION nanosynth)

# --- Option to embed libscsynth as a nanobind extension ---
option(NANOSYNTH_EMBED_SCSYNTH "Build _scsynth extension with embedded libscsynth" OFF)

if(NANOSYNTH_EMBED_SCSYNTH)
    set(SC_SOURCE_DIR "" CACHE PATH "Path to pre-built SuperCollider source directory (legacy)")
    set(SC_BUILD_DIR "" CACHE PATH "Path to pre-built SuperCollider build directory (legacy)")

    nanobind_add_module(_scsynth src/nanosynth/_scsynth.cpp)

    if(SC_SOURCE_DIR AND SC_BUILD_DIR)
        # ---- Mode B: Pre-built SC tree (legacy) ----
        message(STATUS "Using pre-built SuperCollider: ${SC_SOURCE_DIR}")
        target_include_directories(_scsynth PRIVATE
            ${SC_SOURCE_DIR}/include/server
            ${SC_SOURCE_DIR}/include/common
            ${SC_SOURCE_DIR}/include/plugin_interface
            ${SC_SOURCE_DIR}/common
        )
        target_link_libraries(_scsynth PRIVATE
            ${SC_BUILD_DIR}/server/scsynth/libscsynth.a
            ${SC_BUILD_DIR}/external_libraries/libtlsf.a
        )
    else()
        # ---- Mode A: FetchContent (default) ----
        message(STATUS "Fetching SuperCollider via FetchContent ...")
        include(FetchContent)

        # Override SC options before FetchContent_MakeAvailable (add_subdirectory)
        set(SC_QT            OFF CACHE BOOL "" FORCE)
        set(SC_IDE           OFF CACHE BOOL "" FORCE)
        set(SUPERNOVA        OFF CACHE BOOL "" FORCE)
        set(NO_X11           ON  CACHE BOOL "" FORCE)
        set(ENABLE_TESTSUITE OFF CACHE BOOL "" FORCE)
        set(SC_HIDAPI        OFF CACHE BOOL "" FORCE)
        set(SC_ABLETON_LINK  OFF CACHE BOOL "" FORCE)
        set(INSTALL_HELP     OFF CACHE BOOL "" FORCE)
        set(SC_BUILD_SCLANG  OFF CACHE BOOL "" FORCE)
        set(SC_BUILD_EDITORS OFF CACHE BOOL "" FORCE)
        set(LIBSCSYNTH       OFF CACHE BOOL "" FORCE)   # static libscsynth

        FetchContent_Declare(supercollider
            GIT_REPOSITORY https://github.com/supercollider/supercollider.git
            GIT_TAG        Version-3.14.1
            GIT_SHALLOW    ON
            GIT_SUBMODULES external_libraries/nova-simd external_libraries/nova-tt
            PATCH_COMMAND  sh "${CMAKE_CURRENT_SOURCE_DIR}/patches/apply_sc_patches.sh" "${CMAKE_CURRENT_SOURCE_DIR}/patches"
            EXCLUDE_FROM_ALL
        )
        FetchContent_MakeAvailable(supercollider)

        target_include_directories(_scsynth PRIVATE
            ${supercollider_SOURCE_DIR}/include/server
            ${supercollider_SOURCE_DIR}/include/common
            ${supercollider_SOURCE_DIR}/include/plugin_interface
            ${supercollider_SOURCE_DIR}/common
        )

        # Link against real CMake targets from SC
        target_link_libraries(_scsynth PRIVATE libscsynth tlsf)

        # --- UGen plugins ---
        set(SCSYNTH_PLUGIN_TARGETS
            BinaryOpUGens ChaosUGens DelayUGens DemandUGens DynNoiseUGens
            FilterUGens GendynUGens GrainUGens IOUGens LFUGens
            MulAddUGens NoiseUGens OscUGens PanUGens PhysicalModelingUGens
            ReverbUGens TestUGens TriggerUGens UnaryOpUGens UnpackFFTUGens
            FFT_UGens PV_ThirdParty ML_UGens DiskIO_UGens
        )
        # Ensure plugins are built alongside _scsynth (needed with EXCLUDE_FROM_ALL)
        add_dependencies(_scsynth ${SCSYNTH_PLUGIN_TARGETS})

        # Install plugin shared libraries into the wheel
        foreach(plugin_target ${SCSYNTH_PLUGIN_TARGETS})
            install(TARGETS ${plugin_target}
                LIBRARY DESTINATION nanosynth/plugins
                RUNTIME DESTINATION nanosynth/plugins
            )
        endforeach()

        # Copy plugins to source tree so editable installs can find them.
        # scikit-build-core editable mode only extracts Python extensions
        # to site-packages, not data files like .scx plugins.
        # We attach to _scsynth POST_BUILD since it depends on all plugins.
        add_custom_command(TARGET _scsynth POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E make_directory
                "${CMAKE_CURRENT_SOURCE_DIR}/src/nanosynth/plugins"
        )
        foreach(plugin_target ${SCSYNTH_PLUGIN_TARGETS})
            add_custom_command(TARGET _scsynth POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy
                    "$<TARGET_FILE:${plugin_target}>"
                    "${CMAKE_CURRENT_SOURCE_DIR}/src/nanosynth/plugins/"
            )
        endforeach()
    endif()

    # ---- Common to both modes ----

    # libsndfile (dynamic)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(SNDFILE REQUIRED IMPORTED_TARGET sndfile)
    target_link_libraries(_scsynth PRIVATE PkgConfig::SNDFILE)

    # macOS system frameworks required by libscsynth
    if(APPLE)
        target_link_libraries(_scsynth PRIVATE
            "-framework CoreAudio"
            "-framework Accelerate"
            "-framework CoreServices"
            "-framework Foundation"
            "-framework AppKit"
        )
    endif()

    # Linux: pthread and rt
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        target_link_libraries(_scsynth PRIVATE pthread rt)
    endif()

    if(MSVC)
        target_compile_options(_scsynth PRIVATE /W4)
    else()
        target_compile_options(_scsynth PRIVATE -Wall -Wextra)
    endif()

    install(TARGETS _scsynth DESTINATION nanosynth)
endif()
