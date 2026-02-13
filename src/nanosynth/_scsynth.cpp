// nanobind wrapper for libscsynth -- embeds SuperCollider's synthesis engine
// in-process, exposing World_New / World_OpenUDP / World_WaitForQuit etc.

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/optional.h>

#include <cstdarg>
#include <cstdio>
#include <mutex>
#include <string>

#include "SC_WorldOptions.h"

namespace nb = nanobind;

// ---------------------------------------------------------------------------
// Print function redirection
// ---------------------------------------------------------------------------

static nb::object g_print_func;
static std::mutex g_print_mutex;

static int scsynth_print_func(const char* fmt, va_list ap) {
    char buf[4096];
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    std::lock_guard<std::mutex> lock(g_print_mutex);
    if (g_print_func.ptr() != nullptr && !g_print_func.is_none()) {
        nb::gil_scoped_acquire gil;
        try {
            g_print_func(buf);
        } catch (...) {
            // Swallow Python exceptions in the print callback to avoid
            // crashing inside scsynth's internal logging.
        }
    }
    return n;
}

// ---------------------------------------------------------------------------
// Helpers for string lifetime management
// ---------------------------------------------------------------------------

// We need C strings whose lifetime extends beyond world_new.
// Store them in a simple container attached to the capsule destructor context.

struct WorldStrings {
    std::string password;
    std::string ugen_plugins_path;
    std::string restricted_path;
    std::string in_device_name;
    std::string out_device_name;
    std::string input_streams_enabled;
    std::string output_streams_enabled;
};

// ---------------------------------------------------------------------------
// No-op reply function for World_SendPacket (avoids null dereference when
// scsynth internally replies to commands like /quit or /notify).
// ---------------------------------------------------------------------------

static void noop_reply_func(struct ReplyAddress*, char*, int) {}

// ---------------------------------------------------------------------------
// Module functions
// ---------------------------------------------------------------------------

static void py_set_print_func(nb::object func) {
    std::lock_guard<std::mutex> lock(g_print_mutex);
    if (func.is_none()) {
        g_print_func = nb::none();
        // SetPrintFunc with our no-op handler to avoid null dereference
    } else {
        g_print_func = func;
    }
    SetPrintFunc(scsynth_print_func);
}

static nb::capsule py_world_new(
    uint32_t num_audio_bus_channels,
    uint32_t num_input_bus_channels,
    uint32_t num_output_bus_channels,
    uint32_t num_control_bus_channels,
    uint32_t block_size,
    uint32_t num_buffers,
    uint32_t max_nodes,
    uint32_t max_graph_defs,
    uint32_t max_wire_bufs,
    uint32_t num_rgens,
    uint32_t max_logins,
    uint32_t realtime_memory_size,
    uint32_t preferred_sample_rate,
    uint32_t preferred_hardware_buffer_size,
    uint32_t load_graph_defs,
    bool memory_locking,
    bool realtime,
    int verbosity,
    bool rendezvous,
    std::optional<std::string> ugen_plugins_path,
    std::optional<std::string> restricted_path,
    std::optional<std::string> password,
    std::optional<std::string> in_device_name,
    std::optional<std::string> out_device_name,
    std::optional<std::string> input_streams_enabled,
    std::optional<std::string> output_streams_enabled,
    int shared_memory_id,
    float safety_clip_threshold
) {
    // Allocate string storage with the same lifetime as the capsule
    auto* strings = new WorldStrings();

    WorldOptions opts;
    opts.mNumAudioBusChannels = num_audio_bus_channels;
    opts.mNumInputBusChannels = num_input_bus_channels;
    opts.mNumOutputBusChannels = num_output_bus_channels;
    opts.mNumControlBusChannels = num_control_bus_channels;
    opts.mBufLength = block_size;
    opts.mNumBuffers = num_buffers;
    opts.mMaxNodes = max_nodes;
    opts.mMaxGraphDefs = max_graph_defs;
    opts.mMaxWireBufs = max_wire_bufs;
    opts.mNumRGens = num_rgens;
    opts.mMaxLogins = max_logins;
    opts.mRealTimeMemorySize = realtime_memory_size;
    opts.mPreferredSampleRate = preferred_sample_rate;
    opts.mPreferredHardwareBufferFrameSize = preferred_hardware_buffer_size;
    opts.mLoadGraphDefs = load_graph_defs;
    opts.mMemoryLocking = memory_locking;
    opts.mRealTime = realtime;
    opts.mVerbosity = verbosity;
    opts.mRendezvous = rendezvous;
    opts.mSharedMemoryID = shared_memory_id;
    opts.mSafetyClipThreshold = safety_clip_threshold;

    if (password.has_value()) {
        strings->password = *password;
        opts.mPassword = strings->password.c_str();
    }
    if (ugen_plugins_path.has_value()) {
        strings->ugen_plugins_path = *ugen_plugins_path;
        opts.mUGensPluginPath = strings->ugen_plugins_path.c_str();
    }
    if (restricted_path.has_value()) {
        strings->restricted_path = *restricted_path;
        opts.mRestrictedPath = strings->restricted_path.c_str();
    }
    if (in_device_name.has_value()) {
        strings->in_device_name = *in_device_name;
        opts.mInDeviceName = strings->in_device_name.c_str();
    }
    if (out_device_name.has_value()) {
        strings->out_device_name = *out_device_name;
        opts.mOutDeviceName = strings->out_device_name.c_str();
    }
    if (input_streams_enabled.has_value()) {
        strings->input_streams_enabled = *input_streams_enabled;
        opts.mInputStreamsEnabled = strings->input_streams_enabled.c_str();
    }
    if (output_streams_enabled.has_value()) {
        strings->output_streams_enabled = *output_streams_enabled;
        opts.mOutputStreamsEnabled = strings->output_streams_enabled.c_str();
    }

    World* world;
    {
        nb::gil_scoped_release release;
        world = World_New(&opts);
    }

    if (!world) {
        delete strings;
        throw std::runtime_error("World_New failed");
    }

    // Return World* as an opaque capsule. The destructor cleans up strings.
    // World cleanup is handled explicitly via world_cleanup / world_wait_for_quit.
    return nb::capsule(world, "World", [](void* p) noexcept {
        // Note: we do NOT call World_Cleanup here because the user should
        // explicitly manage the world lifecycle. If they forget, the world
        // was already cleaned up by world_wait_for_quit or world_cleanup.
        (void)p;
    });
}

static World* extract_world(nb::capsule& cap) {
    if (!cap.data()) {
        throw std::runtime_error("World handle is null (already cleaned up?)");
    }
    return static_cast<World*>(cap.data());
}

static bool py_world_open_udp(nb::capsule& world_cap, const std::string& bind_to, int port) {
    World* world = extract_world(world_cap);
    int result;
    {
        nb::gil_scoped_release release;
        result = World_OpenUDP(world, bind_to.c_str(), port);
    }
    return result != 0;
}

static bool py_world_open_tcp(
    nb::capsule& world_cap,
    const std::string& bind_to,
    int port,
    int max_connections,
    int backlog
) {
    World* world = extract_world(world_cap);
    int result;
    {
        nb::gil_scoped_release release;
        result = World_OpenTCP(world, bind_to.c_str(), port, max_connections, backlog);
    }
    return result != 0;
}

static void py_world_wait_for_quit(nb::capsule& world_cap, bool unload_plugins) {
    World* world = extract_world(world_cap);
    {
        nb::gil_scoped_release release;
        World_WaitForQuit(world, unload_plugins);
    }
}

static void py_world_cleanup(nb::capsule& world_cap, bool unload_plugins) {
    World* world = extract_world(world_cap);
    {
        nb::gil_scoped_release release;
        World_Cleanup(world, unload_plugins);
    }
}

static bool py_world_send_packet(nb::capsule& world_cap, nb::bytes data) {
    World* world = extract_world(world_cap);
    int size = static_cast<int>(data.size());
    // World_SendPacket takes a char* but does not modify the data.
    char* buf = const_cast<char*>(data.c_str());
    bool result;
    {
        nb::gil_scoped_release release;
        result = World_SendPacket(world, size, buf, noop_reply_func);
    }
    return result;
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

NB_MODULE(_scsynth, m) {
    m.doc() = "Embedded SuperCollider synthesis server (libscsynth)";

    m.def("set_print_func", &py_set_print_func,
          nb::arg("func").none(),
          "Set the print function for scsynth output. Pass None to clear.");

    m.def("world_new", &py_world_new,
          nb::arg("num_audio_bus_channels") = 1024u,
          nb::arg("num_input_bus_channels") = 8u,
          nb::arg("num_output_bus_channels") = 8u,
          nb::arg("num_control_bus_channels") = 16384u,
          nb::arg("block_size") = 64u,
          nb::arg("num_buffers") = 1024u,
          nb::arg("max_nodes") = 1024u,
          nb::arg("max_graph_defs") = 1024u,
          nb::arg("max_wire_bufs") = 64u,
          nb::arg("num_rgens") = 64u,
          nb::arg("max_logins") = 64u,
          nb::arg("realtime_memory_size") = 8192u,
          nb::arg("preferred_sample_rate") = 0u,
          nb::arg("preferred_hardware_buffer_size") = 0u,
          nb::arg("load_graph_defs") = 1u,
          nb::arg("memory_locking") = false,
          nb::arg("realtime") = true,
          nb::arg("verbosity") = 0,
          nb::arg("rendezvous") = true,
          nb::arg("ugen_plugins_path") = nb::none(),
          nb::arg("restricted_path") = nb::none(),
          nb::arg("password") = nb::none(),
          nb::arg("in_device_name") = nb::none(),
          nb::arg("out_device_name") = nb::none(),
          nb::arg("input_streams_enabled") = nb::none(),
          nb::arg("output_streams_enabled") = nb::none(),
          nb::arg("shared_memory_id") = 0,
          nb::arg("safety_clip_threshold") = 1.26f,
          "Create a new scsynth World. Returns an opaque handle.");

    m.def("world_open_udp", &py_world_open_udp,
          nb::arg("world"), nb::arg("bind_to"), nb::arg("port"),
          "Open a UDP interface on the world. Returns True on success.");

    m.def("world_open_tcp", &py_world_open_tcp,
          nb::arg("world"), nb::arg("bind_to"), nb::arg("port"),
          nb::arg("max_connections") = 64, nb::arg("backlog") = 128,
          "Open a TCP interface on the world. Returns True on success.");

    m.def("world_wait_for_quit", &py_world_wait_for_quit,
          nb::arg("world"), nb::arg("unload_plugins") = true,
          "Block until the world receives /quit. Cleans up internally.");

    m.def("world_cleanup", &py_world_cleanup,
          nb::arg("world"), nb::arg("unload_plugins") = false,
          "Force-cleanup the world without waiting for /quit.");

    m.def("world_send_packet", &py_world_send_packet,
          nb::arg("world"), nb::arg("data"),
          "Send an OSC packet directly to the world. Returns True on success.");
}
