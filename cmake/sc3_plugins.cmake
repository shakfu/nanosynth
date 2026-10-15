# sc3-plugins (thirdparty/sc3-plugins) as EXCLUDE_FROM_ALL MODULE targets.
#
# Replaces sc3-plugins' own CMake, which changes global flags; see
# docs/dev/sc3-plugins-build.md. Sets SC3_SCSYNTH_PLUGIN_TARGETS and, when
# supernova is embedded, SC3_SUPERNOVA_PLUGIN_TARGETS.

set(_sc3 "${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/sc3-plugins/source")
set(_stk "${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/sc3-plugins/external_libraries/stk")
set(_sc  "${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/supercollider")

set(SC3_SCSYNTH_PLUGIN_TARGETS "")
set(SC3_SUPERNOVA_PLUGIN_TARGETS "")

# Settings shared by the scsynth and supernova variant of one plugin.
function(_sc3_configure target)
    # Core plugins: no prefix; .scx on macOS/Windows, .so on Linux (SC_PLUGIN_EXT).
    set_target_properties(${target} PROPERTIES PREFIX "")
    if(APPLE OR WIN32)
        set_target_properties(${target} PROPERTIES SUFFIX ".scx")
    endif()
    set_target_properties(${target} PROPERTIES
        C_VISIBILITY_PRESET hidden CXX_VISIBILITY_PRESET hidden)
    target_include_directories(${target} PRIVATE
        ${_sc}/include/plugin_interface
        ${_sc}/include/common
        ${_sc}/common
        ${_sc}/server/plugins
        ${_sc}/external_libraries/nova-simd
    )
    target_compile_definitions(${target} PRIVATE NOVA_SIMD)
    if(WIN32)
        # Give MSVC the M_PI and min/max behaviour POSIX builds already have.
        target_compile_definitions(${target} PRIVATE NOMINMAX _USE_MATH_DEFINES)
    endif()
endfunction()

# sc3_plugin(<name> SOURCES ... [LIBS ...] [INCLUDES ...] [DEFINES ...])
# Relative SOURCES are under thirdparty/sc3-plugins/source.
function(sc3_plugin name)
    cmake_parse_arguments(P "" "" "SOURCES;LIBS;INCLUDES;DEFINES" ${ARGN})
    set(srcs "")
    foreach(src ${P_SOURCES})
        if(NOT IS_ABSOLUTE "${src}")
            set(src "${_sc3}/${src}")
        endif()
        list(APPEND srcs "${src}")
    endforeach()
    set(P_SOURCES ${srcs})
    add_library(${name} MODULE EXCLUDE_FROM_ALL ${P_SOURCES})
    _sc3_configure(${name})
    target_include_directories(${name} PRIVATE ${P_INCLUDES})
    target_compile_definitions(${name} PRIVATE ${P_DEFINES})
    target_link_libraries(${name} PRIVATE ${P_LIBS})
    list(APPEND SC3_SCSYNTH_PLUGIN_TARGETS ${name})
    set(SC3_SCSYNTH_PLUGIN_TARGETS ${SC3_SCSYNTH_PLUGIN_TARGETS} PARENT_SCOPE)

    if(NANOSYNTH_EMBED_SUPERNOVA)
        set(sn ${name}_supernova)
        add_library(${sn} MODULE EXCLUDE_FROM_ALL ${P_SOURCES})
        _sc3_configure(${sn})
        target_include_directories(${sn} PRIVATE ${P_INCLUDES}
            ${_sc}/external_libraries/nova-tt
            ${_sc}/external_libraries/boost
        )
        target_compile_definitions(${sn} PRIVATE ${P_DEFINES} SUPERNOVA)
        target_link_libraries(${sn} PRIVATE ${P_LIBS})
        if(MSVC)
            # Boost headers must not auto-link boost libraries (as for _supernova).
            target_compile_definitions(${sn} PRIVATE BOOST_ALL_NO_LIB)
            target_compile_options(${sn} PRIVATE /Zc:__cplusplus)
        endif()
        if(WIN32)
            target_link_libraries(${sn} PRIVATE ws2_32)
        endif()
        list(APPEND SC3_SUPERNOVA_PLUGIN_TARGETS ${sn})
        set(SC3_SUPERNOVA_PLUGIN_TARGETS ${SC3_SUPERNOVA_PLUGIN_TARGETS} PARENT_SCOPE)
    endif()
endfunction()

# --- One plugin per .cpp file (upstream PLUGIN_DIRS, without HOAUGens)
foreach(dir
        AntiAliasingOscillators ATK BatUGens BBCut2UGens BerlachUGens BhobUGens
        BlackrainUGens ConcatUGens DistortionUGens DWGUGens GlitchUGens JoshUGens
        LoopBufUGens MCLDUGens MdaUGens Neuromodules NHUGens QuantityUGens
        RFWUGens RMEQSuiteUGens SCMIRUGens SkUGens SLUGens SummerUGens
        TagSystemUGens VBAPUGens VOSIMUGens)
    file(GLOB _srcs "${_sc3}/${dir}/*.cpp")
    foreach(src ${_srcs})
        get_filename_component(_name ${src} NAME_WE)
        sc3_plugin(${_name} SOURCES ${src})
    endforeach()
endforeach()

# --- Plugins with several sources or extra settings (upstream PLUGIN_DIRS_EXTRA)
file(GLOB _srcs "${_sc3}/AuditoryModeling/*.cpp")
sc3_plugin(AuditoryModeling SOURCES ${_srcs})

sc3_plugin(BetablockerUGens SOURCES
    BetablockerUGens/BetablockerUGens.cpp
    BetablockerUGens/betablocker/machine.cpp
    BetablockerUGens/betablocker/thread.cpp)

sc3_plugin(NoiseRing SOURCES ChaosUGens/NoiseRing.cpp)
sc3_plugin(PredPrey SOURCES ChaosUGens/PredPrey.cpp)

sc3_plugin(RMS SOURCES DEINDUGens/RMS.cpp)
sc3_plugin(DiodeRingMod SOURCES DEINDUGens/DiodeRingMod.cpp)
sc3_plugin(complexRes SOURCES DEINDUGens/complexRes.cpp)
sc3_plugin(JPverb SOURCES DEINDUGens/JPverbRaw.cpp
    INCLUDES ${_sc3}/DEINDUGens/include
    DEFINES [[SC_FAUST_PREFIX=""]] mydsp=JPVERB NDEBUG)
sc3_plugin(Greyhole SOURCES DEINDUGens/GreyholeRaw.cpp
    INCLUDES ${_sc3}/DEINDUGens/include
    DEFINES [[SC_FAUST_PREFIX=""]] mydsp=GREYHOLE NDEBUG)

sc3_plugin(MembraneUGens SOURCES
    MembraneUGens/Membrane_shape.c MembraneUGens/Membrane.cpp)

sc3_plugin(OteyPianoUGens SOURCES
    OteyPianoUGens/OteyPiano.cpp OteyPianoUGens/dwgs.cpp
    OteyPianoUGens/filter.cpp OteyPianoUGens/hammer.cpp OteyPianoUGens/reverb.cpp)

# PitchDetection needs an FFT: Accelerate on macOS. Elsewhere it needs FFTW3f,
# which is not vendored, so it is left out.
if(APPLE)
    file(GLOB _srcs "${_sc3}/PitchDetection/*.cpp")
    sc3_plugin(PitchDetection SOURCES ${_srcs}
        DEFINES SC_FFT_VDSP LIBS "-framework Accelerate")
endif()

# NCAnalysisUGens uses Accelerate on macOS only for vector helpers.
file(GLOB _srcs "${_sc3}/NCAnalysisUGens/*.cpp")
if(APPLE)
    sc3_plugin(NCAnalysisUGens SOURCES ${_srcs} LIBS "-framework Accelerate")
else()
    sc3_plugin(NCAnalysisUGens SOURCES ${_srcs})
endif()

sc3_plugin(AY_UGen SOURCES AYUGens/AY_UGen.cpp AYUGens/AY_libayemu/src/ay8912.c
    INCLUDES ${_sc3}/AYUGens/AY_libayemu/include)

file(GLOB _srcs "${_sc3}/TJUGens/*.cpp")
sc3_plugin(TJUGens SOURCES ${_srcs})

# --- STK: StkUGens and StkInst each compile their own copy of the STK sources.
file(GLOB _stk_srcs "${_stk}/src/*.cpp")
foreach(unneeded Rt Inet Socket Tcp UdpSocket Thread Mutex)
    list(FILTER _stk_srcs EXCLUDE REGEX "/src/${unneeded}[^/]*\\.cpp$")
endforeach()
set(_stk_includes ${_stk} ${_stk}/include ${_stk}/src/include)
sc3_plugin(StkUGens SOURCES StkUGens/StkAll.cpp ${_stk_srcs}
    INCLUDES ${_stk_includes})
list(FILTER _stk_srcs EXCLUDE REGEX "/src/Messager\\.cpp$")
sc3_plugin(StkInst SOURCES StkInst/StkInst.cpp ${_stk_srcs}
    INCLUDES ${_stk_includes}
    DEFINES __LITTLE_ENDIAN__ _STK_DEBUG_)
