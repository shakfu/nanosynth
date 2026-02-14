cmake_minimum_required(VERSION 3.28...3.31)
project(${SKBUILD_PROJECT_NAME} VERSION ${SKBUILD_PROJECT_VERSION} LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
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
option(NANOSYNTH_EMBED_SCSYNTH "Build _scsynth extension with embedded libscsynth" ON)

if(NANOSYNTH_EMBED_SCSYNTH)
    nanobind_add_module(_scsynth src/nanosynth/_scsynth.cpp)

    # --- Vendored libsndfile (static, tailored -- no external codec deps) ---
    set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
    set(BUILD_PROGRAMS    OFF CACHE BOOL "" FORCE)
    set(BUILD_EXAMPLES    OFF CACHE BOOL "" FORCE)
    set(BUILD_TESTING     OFF CACHE BOOL "" FORCE)
    set(ENABLE_EXTERNAL_LIBS OFF CACHE BOOL "" FORCE)  # no ogg/vorbis/FLAC
    set(ENABLE_MPEG       OFF CACHE BOOL "" FORCE)     # no mpg123/lame
    set(INSTALL_MANPAGES  OFF CACHE BOOL "" FORCE)
    set(INSTALL_PKGCONFIG_MODULE OFF CACHE BOOL "" FORCE)

    add_subdirectory(thirdparty/libsndfile EXCLUDE_FROM_ALL)

    # Point SC's FindSndfile at our vendored build so it doesn't find
    # a system dylib. SC does target_link_libraries(libscsynth ${SNDFILE_LIBRARIES})
    # so passing the CMake target name works -- CMake resolves it at build time.
    set(SNDFILE_LIBRARY "sndfile" CACHE STRING "" FORCE)
    set(SNDFILE_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/libsndfile/include"
        CACHE PATH "" FORCE)

    # --- Vendored SuperCollider (static libscsynth) ---
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
    set(SYSTEM_YAMLCPP   ON  CACHE BOOL "" FORCE)   # skip bundled yaml-cpp (sclang only)

    # Prevent SC's macOS POST_BUILD commands from copying plugins/scsynth
    # into a SuperCollider.app bundle inside the wheel staging area.
    set(scappauxresourcesdir "" CACHE STRING "" FORCE)
    set(scappbindir          "" CACHE STRING "" FORCE)

    # Audio API: CoreAudio on macOS, vendored PortAudio on Linux/Windows
    if(NOT APPLE)
        set(AUDIOAPI         "portaudio" CACHE STRING "" FORCE)
        set(SYSTEM_PORTAUDIO OFF CACHE BOOL "" FORCE)  # build vendored portaudio
    endif()

    # Windows: pthreads doesn't exist; SC plugins link ${PTHREADS_LIBRARY}
    if(WIN32)
        set(PTHREADS_LIBRARY "" CACHE STRING "" FORCE)
    endif()

    # Disable SC's ccache integration on Windows: Strawberry Perl's
    # ccache is incompatible with modern MSVC and crashes cl.exe.
    if(WIN32)
        set(USE_CCACHE OFF CACHE BOOL "" FORCE)
    endif()

    add_subdirectory(thirdparty/supercollider EXCLUDE_FROM_ALL)

    target_include_directories(_scsynth PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/supercollider/include/server
        ${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/supercollider/include/common
        ${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/supercollider/include/plugin_interface
        ${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/supercollider/common
    )

    # Link against CMake targets from vendored deps
    target_link_libraries(_scsynth PRIVATE libscsynth tlsf sndfile)

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
