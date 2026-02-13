if (NOT EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/nova-simd/vec.hpp)
    message(FATAL_ERROR "It appears you haven't cloned this project's git submodules:"
			" please run `git submodule update --init --recursive` from the root level of the repository.\n"
			"For advice on setting up submodules, and also on keeping them updated over time, please see"
			" this wiki page, and consider saving this link:"
			" https://github.com/supercollider/supercollider/wiki/git-cheat-sheet#working-with-submodules")
endif()

if(NOT SYSTEM_PORTAUDIO)
    message(STATUS "PortAudio: building static library")
    add_subdirectory(portaudio)
endif()

if(NOT SYSTEM_BOOST) # we compile boost ourselves
	message(STATUS "Using bundled boost (headers only)")
	set(BOOST_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/boost)

	# headers-only target -- compiled boost libs (thread, program_options,
	# regex, unit_test_framework) are only needed by supernova/sclang/X11
	# UGens, all of which are disabled in the nanosynth build.
	add_library(boost_headers INTERFACE)
	target_include_directories(boost_headers INTERFACE ${BOOST_INCLUDE_DIR})

	# Provide INTERFACE-only stubs so Boost::* aliases resolve if referenced
	# in guarded cmake code that never actually links.
	add_library(boost_thread_lib INTERFACE)
	target_link_libraries(boost_thread_lib INTERFACE boost_headers)
	add_library(boost_program_options_lib INTERFACE)
	target_link_libraries(boost_program_options_lib INTERFACE boost_headers)
	add_library(boost_regex_lib INTERFACE)
	target_link_libraries(boost_regex_lib INTERFACE boost_headers)
	add_library(boost_unit_test_framework_lib INTERFACE)
	target_link_libraries(boost_unit_test_framework_lib INTERFACE boost_headers)

	add_library(Boost::thread ALIAS boost_thread_lib)
	add_library(Boost::program_options ALIAS boost_program_options_lib)
	add_library(Boost::regex ALIAS boost_regex_lib)
	add_library(Boost::unit_test_framework ALIAS boost_unit_test_framework_lib)
	add_library(Boost::headers ALIAS boost_headers)

endif()

# add a custom target for boost_sync
add_library(boost_sync INTERFACE)
target_include_directories(boost_sync INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/boost_sync/include
)
# Boost::headers comes from either system or bundled boost
target_link_libraries(boost_sync INTERFACE Boost::headers)
add_library(Boost::sync ALIAS boost_sync)

# tlsf
add_library(tlsf STATIC EXCLUDE_FROM_ALL "TLSF-2.4.6/src/tlsf.c")
target_compile_definitions( tlsf PRIVATE TLSF_STATISTIC=1 )
target_include_directories( tlsf INTERFACE TLSF-2.4.6/src )
set_property(TARGET tlsf PROPERTY POSITION_INDEPENDENT_CODE TRUE)

#oscpack
add_library(oscpack STATIC EXCLUDE_FROM_ALL "oscpack_build.cpp")
target_link_libraries(oscpack PUBLIC Boost::headers)
target_include_directories(oscpack INTERFACE oscpack_1_1_0 )

if(LTO)
	set_property(TARGET oscpack tlsf
				 APPEND PROPERTY COMPILE_FLAGS "-flto -flto-report")

	set_property(TARGET oscpack tlsf
				 APPEND PROPERTY LINK_FLAGS "-flto -flto-report")
endif()

if(NOT SYSTEM_YAMLCPP)
  message(STATUS "Using bundled yaml-cpp")

  # yaml-cpp
  set(CMAKE_POLICY_VERSION_MINIMUM 3.10) # workaround for cmake 4
  aux_source_directory(${PROJECT_SOURCE_DIR}/external_libraries/yaml-cpp/src yaml_src)
  CREATE_FINAL_FILE(${CMAKE_CURRENT_BINARY_DIR}/libyamlcpp.cpp ${yaml_src})

  add_library(yaml STATIC EXCLUDE_FROM_ALL ${CMAKE_CURRENT_BINARY_DIR}/libyamlcpp.cpp)
  target_include_directories(yaml PUBLIC ${PROJECT_SOURCE_DIR}/external_libraries/yaml-cpp/include ${boost_include_dirs})
  set_property( TARGET yaml PROPERTY FOLDER 3rdparty )
  set(YAMLCPP_LIBRARY yaml)
  set(YAMLCPP_INCLUDE_DIR ${PROJECT_SOURCE_DIR}/external_libraries/yaml-cpp/include)

  if(CMAKE_COMPILER_IS_GNUCXX)
    target_compile_options(yaml PRIVATE -Wno-deprecated-declarations)
  endif()

endif()


set_property( TARGET oscpack tlsf PROPERTY FOLDER 3rdparty )


##### HID_API #######

if (HID_LIBUSB)
  set( LIBUSB ON )
  set( HIDRAW OFF )
endif()
if (HID_HIDRAW)
  set( HIDRAW ON )
  set( LIBUSB OFF )
endif()
set( EXAMPLE_TEST OFF )
set( EXAMPLE_OSC OFF )

if(SC_HIDAPI)
    add_subdirectory(hidapi)
    message(STATUS "Building with HID support")
elseif(MINGW AND (${CMAKE_CXX_COMPILER_VERSION} VERSION_LESS 5.3.0))
    message(WARNING "SC is by default built without HID-support if a MinGW/gcc-version below 5.3 is used. Please consult the Readme on how to enable it (easy).")
else()
    message(STATUS "HID support disabled")
endif()

if(WIN32)
  add_library(portmidi portmidi/pm_common/pminternal.h
                       portmidi/pm_common/pmutil.c
                       portmidi/pm_common/pmutil.h
                       portmidi/pm_common/portmidi.c
                       portmidi/pm_common/portmidi.h
                       portmidi/pm_win/pmwin.c
                       portmidi/pm_win/pmwinmm.c
                       portmidi/pm_win/pmwinmm.h
                       portmidi/porttime/porttime.c
                       portmidi/porttime/porttime.h
                       portmidi/porttime/ptwinmm.c)
  target_include_directories(portmidi PUBLIC  portmidi/pm_common portmidi/porttime)
  target_include_directories(portmidi PRIVATE portmidi/pm_win)

  target_link_libraries(portmidi PRIVATE winmm.lib)
  target_compile_definitions(portmidi INTERFACE HAVE_PORTMIDI)
endif()
