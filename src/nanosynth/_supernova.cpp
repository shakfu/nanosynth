// nanobind wrapper for supernova -- embeds SuperCollider's parallel DSP engine
// in-process, exposing nova_server lifecycle via direct C++ calls.
//
// Mirrors _scsynth.cpp but wraps supernova's C++ class hierarchy instead of
// scsynth's C API (World_New, World_SendPacket, etc.).

// SC function attribute macros (PURE, HOT, etc.) -- must be included before
// supernova headers because Windows SDK defines PURE as "= 0" which breaks
// supernova's utils.hpp where PURE is used as __attribute__((pure)).
// On MSVC, function_attributes.h defines PURE as empty before windef.h can
// define it as "= 0".  NOMINMAX, WIN32_LEAN_AND_MEAN, _WIN32_WINNT, and
// _ENABLE_ATOMIC_ALIGNMENT_FIX are set via target_compile_definitions in
// CMakeLists.txt to match SC's global MSVC definitions.
#include "function_attributes.h"

#ifdef _MSC_VER
// Include Windows headers explicitly in the correct order before
// nanobind/Python.h and Boost.Asio.  This ensures:
// 1. SAL annotations (IN, OUT) are defined for winsock2.h
// 2. winsock2.h is included before winsock.h (WIN32_LEAN_AND_MEAN alone
//    is not sufficient on SDK 10.0.26100.0)
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
// Restore PURE -- windows.h pulls in windef.h which defines PURE as "= 0"
#undef PURE
#define PURE /*PURE*/
#endif

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/optional.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#ifdef __APPLE__
#include <unistd.h>

static void _sn_force_exit_on_teardown() {
    _exit(0);
}
#endif

// SC headers (PrintFunc type declaration)
#include "SC_WorldOptions.h"

// supernova does not define SetPrintFunc (that's scsynth's API).
// We provide our own implementation here.
static PrintFunc g_nanosynth_print_func = nullptr;

extern "C" void SetPrintFunc(PrintFunc func) {
    g_nanosynth_print_func = func;
}

// Supernova headers
#include "server/server.hpp"
#include "server/server_args.hpp"
#include "sc/sc_ugen_factory.hpp"
#include "server/memory_pool.hpp"

using nova::rt_pool;
using nova::sc_factory;

namespace nb = nanobind;

// Forward declarations from supernova
namespace nova {
void parse_hardware_topology(void);
}

// ---------------------------------------------------------------------------
// Print function redirection
// ---------------------------------------------------------------------------

static nb::object g_sn_print_func;
static std::mutex g_sn_print_mutex;

static int supernova_print_func(const char* fmt, va_list ap) {
    char stack_buf[4096];
    va_list ap_copy;
    va_copy(ap_copy, ap);
    int n = vsnprintf(stack_buf, sizeof(stack_buf), fmt, ap);
    char* buf = stack_buf;
    std::vector<char> heap_buf;
    if (n >= static_cast<int>(sizeof(stack_buf))) {
        heap_buf.resize(static_cast<size_t>(n) + 1);
        vsnprintf(heap_buf.data(), heap_buf.size(), fmt, ap_copy);
        buf = heap_buf.data();
    }
    va_end(ap_copy);
    std::lock_guard<std::mutex> lock(g_sn_print_mutex);
    if (g_sn_print_func.ptr() != nullptr && !g_sn_print_func.is_none()) {
        nb::gil_scoped_acquire gil;
        try {
            g_sn_print_func(buf);
        } catch (...) {
            // Swallow Python exceptions to avoid crashing supernova internals
        }
    }
    return n;
}

// ---------------------------------------------------------------------------
// Reply function redirection
// ---------------------------------------------------------------------------

static nb::object g_sn_reply_func;
static std::mutex g_sn_reply_mutex;

// Custom endpoint that forwards replies to a Python callback
class python_endpoint : public nova::detail::nova_endpoint {
public:
    void send(const char* data, size_t length) override {
        std::lock_guard<std::mutex> lock(g_sn_reply_mutex);
        if (g_sn_reply_func.ptr() != nullptr && !g_sn_reply_func.is_none()) {
            nb::gil_scoped_acquire gil;
            try {
                nb::bytes py_data(data, length);
                g_sn_reply_func(py_data);
            } catch (...) {
                // Swallow Python exceptions to avoid crashing supernova reply path
            }
        }
    }
};

static void py_sn_set_print_func(nb::object func) {
    std::lock_guard<std::mutex> lock(g_sn_print_mutex);
    if (func.is_none()) {
        g_sn_print_func = nb::none();
    } else {
        g_sn_print_func = func;
    }
    SetPrintFunc(supernova_print_func);
}

static void py_sn_set_reply_func(nb::object func) {
    std::lock_guard<std::mutex> lock(g_sn_reply_mutex);
    if (func.is_none()) {
        g_sn_reply_func = nb::none();
    } else {
        g_sn_reply_func = func;
    }
}

// ---------------------------------------------------------------------------
// Server handle
// ---------------------------------------------------------------------------

struct SupernovaHandle {
    nova::nova_server* server;
};

static nova::nova_server* extract_server(nb::capsule& cap) {
    if (!cap.data()) {
        throw std::runtime_error("Supernova handle is null (already cleaned up?)");
    }
    return static_cast<SupernovaHandle*>(cap.data())->server;
}

// ---------------------------------------------------------------------------
// Plugin loading (adapted from supernova main.cpp)
// ---------------------------------------------------------------------------

static void load_plugins(const std::string& plugin_path, nova::sc_ugen_factory* factory) {
    factory->load_plugin_folder(plugin_path);
}

// Cross-engine guard. scsynth and supernova each statically embed the full
// SuperCollider server core and share process-global singletons (the dlopen'd
// UGen plugin registry, the global FFT init, etc.). Creating one kind after
// the other has run in the same process crashes -- in either order, and even
// after a clean quit. The two extension modules share no symbols, so they
// coordinate through an environment variable. Throws (surfaced to Python as
// ServerCannotBoot) instead of letting the process segfault.
static void nanosynth_claim_engine(const char* kind) {
    const char* active = std::getenv("NANOSYNTH_ACTIVE_ENGINE");
    if (active && active[0] != '\0' && std::string(active) != kind) {
        throw std::runtime_error(
            std::string("cannot create a ") + kind + " engine: a " + active +
            " engine has already been created in this process. scsynth and "
            "supernova embed the full SuperCollider core and share "
            "process-global state, so only one kind can run per process (even "
            "sequentially). Use a separate process for the other engine.");
    }
#ifdef _WIN32
    _putenv_s("NANOSYNTH_ACTIVE_ENGINE", kind);
#else
    setenv("NANOSYNTH_ACTIVE_ENGINE", kind, 1);
#endif
}

// ---------------------------------------------------------------------------
// Boot: construct nova_server with programmatic arguments
// ---------------------------------------------------------------------------

static nb::capsule py_supernova_new(
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
    uint32_t realtime_memory_size,
    uint32_t preferred_sample_rate,
    int32_t preferred_hardware_buffer_size,
    uint16_t load_graph_defs,
    bool memory_locking,
    int16_t verbosity,
    std::optional<std::string> ugen_plugins_path,
    std::optional<std::string> password,
    std::optional<std::string> in_device_name,
    std::optional<std::string> out_device_name,
    int shared_memory_id,
    uint16_t threads,
    float safety_clip_threshold
) {
    nanosynth_claim_engine("supernova");
    // Parse hardware topology for thread pinning
    nova::parse_hardware_topology();

    // Initialize server_arguments singleton via embedded path (no boost::program_options)
    nova::server_arguments& args = nova::server_arguments::initialize_embedded();

    // Populate fields directly
    args.udp_port = 0;  // No UDP socket -- packets injected via handle_packet_async
    args.tcp_port = 0;  // No TCP socket
    args.socket_address_str = "127.0.0.1";
    args.socket_address = boost::asio::ip::make_address("127.0.0.1");
    args.control_busses = num_control_bus_channels;
    args.audio_busses = num_audio_bus_channels;
    args.blocksize = block_size;
    args.samplerate = preferred_sample_rate;
    args.hardware_buffer_size = preferred_hardware_buffer_size;
    args.buffers = num_buffers;
    args.max_nodes = max_nodes;
    args.max_synthdefs = max_graph_defs;
    args.use_system_clock = 1;
    args.rt_pool_size = realtime_memory_size;
    args.wires = max_wire_bufs;
    args.rng_count = num_rgens;
    args.load_synthdefs = load_graph_defs;
    args.verbosity = verbosity;
    args.dump_version = false;
    args.memory_locking = memory_locking;
    args.threads = threads ? threads : static_cast<uint16_t>(std::thread::hardware_concurrency());
    args.thread_pinning = false;
    args.input_channels = static_cast<uint16_t>(num_input_bus_channels);
    args.output_channels = static_cast<uint16_t>(num_output_bus_channels);
    args.non_rt = false;

    if (password.has_value()) {
        args.server_password = *password;
    }

    // Hardware device names
    if (in_device_name.has_value() && out_device_name.has_value()) {
        args.hw_name = {*in_device_name, *out_device_name};
    } else if (in_device_name.has_value()) {
        args.hw_name = {*in_device_name};
    } else if (out_device_name.has_value()) {
        args.hw_name = {*out_device_name};
    }

    // UGen plugin path
    if (ugen_plugins_path.has_value()) {
        args.ugen_paths = {*ugen_plugins_path};
    }

#ifdef __APPLE__
    args.safety_clip_threshold = safety_clip_threshold;
#else
    (void)safety_clip_threshold;
#endif

    // Initialize RT memory pool
    rt_pool.init(args.rt_pool_size * 1024, args.memory_locking);

    // Install print function
    SetPrintFunc(supernova_print_func);

    // Clean up any leftover shared memory from a previous crash
    // Use shared_memory_id as the port for shared memory
    int shm_port = shared_memory_id ? shared_memory_id : 57210;  // default supernova port
    // Temporarily set udp_port so args.port() returns the right value for shared memory
    args.udp_port = static_cast<uint32_t>(shm_port);
    server_shared_memory_creator::cleanup(args.port());

    nova::nova_server* server;
    {
        nb::gil_scoped_release release;
        server = new nova::nova_server(args);
    }

    // Reset udp_port to 0 after construction (shared memory is already set up)
    args.udp_port = 0;

    // Load UGen plugins
    if (ugen_plugins_path.has_value()) {
        load_plugins(*ugen_plugins_path, sc_factory.get());
    }

    // Start audio backend (PortAudio path)
#ifdef PORTAUDIO_BACKEND
    {
        std::string input_device, output_device;
        if (!args.hw_name.empty()) {
            if (args.hw_name.size() == 1) {
                input_device = output_device = args.hw_name[0];
            } else {
                input_device = args.hw_name[0];
                output_device = args.hw_name[1];
            }
        }
        if (args.input_channels == 0)
            input_device.clear();
        if (args.output_channels == 0)
            output_device.clear();

        bool success;
        {
            nb::gil_scoped_release release;
#ifdef __APPLE__
            success = server->open_stream(input_device, args.input_channels,
                                          output_device, args.output_channels,
                                          args.samplerate, args.blocksize,
                                          args.hardware_buffer_size,
                                          args.safety_clip_threshold);
#else
            success = server->open_stream(input_device, args.input_channels,
                                          output_device, args.output_channels,
                                          args.samplerate, args.blocksize,
                                          args.hardware_buffer_size, 0);
#endif
        }
        if (!success) {
            delete server;
            throw std::runtime_error("Supernova: could not open audio devices");
        }

        unsigned int real_sr = server->get_samplerate();
        if (args.samplerate != real_sr) {
            nova::server_arguments::set_samplerate(static_cast<uint32_t>(real_sr));
            sc_factory->reset_sampling_rate(real_sr);
        }

        server->report_latency();
    }
#endif

    {
        nb::gil_scoped_release release;
        server->prepare_backend();
        server->activate_audio();
    }

#ifdef __APPLE__
    static bool exit_guard_registered = false;
    if (!exit_guard_registered) {
        std::atexit(_sn_force_exit_on_teardown);
        exit_guard_registered = true;
    }
#endif

    auto* handle = new SupernovaHandle{server};
    return nb::capsule(handle, "SupernovaHandle", [](void* p) noexcept {
        auto* h = static_cast<SupernovaHandle*>(p);
        delete h;
    });
}

// ---------------------------------------------------------------------------
// Run (blocking event loop)
// ---------------------------------------------------------------------------

static void py_supernova_run(nb::capsule& cap) {
    auto* server = extract_server(cap);
    {
        nb::gil_scoped_release release;
        server->run();  // blocks until terminate() is called
    }
}

// ---------------------------------------------------------------------------
// Send packet (inject OSC data into supernova)
// ---------------------------------------------------------------------------

static bool py_supernova_send_packet(nb::capsule& cap, nb::bytes data) {
    auto* server = extract_server(cap);
    auto endpoint = std::make_shared<python_endpoint>();
    // Copy data for safety (same pattern as _scsynth.cpp)
    std::vector<char> buf(data.c_str(), data.c_str() + data.size());
    {
        nb::gil_scoped_release release;
        server->handle_packet_async(buf.data(), buf.size(), endpoint);
    }
    return true;
}

// ---------------------------------------------------------------------------
// Terminate (signal the event loop to stop)
// ---------------------------------------------------------------------------

static void py_supernova_terminate(nb::capsule& cap) {
    auto* server = extract_server(cap);
    {
        nb::gil_scoped_release release;
        server->prepare_to_terminate();
        server->terminate();
    }
}

// ---------------------------------------------------------------------------
// Cleanup (explicit resource release)
// ---------------------------------------------------------------------------

static void py_supernova_cleanup(nb::capsule& cap) {
    auto* server = extract_server(cap);
    if (server) {
        {
            nb::gil_scoped_release release;
            server->deactivate_audio();
            server->close_stream();
        }
        delete server;
        static_cast<SupernovaHandle*>(cap.data())->server = nullptr;
        nova::instance = nullptr;
    }
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

NB_MODULE(_supernova, m) {
    m.doc() = "Embedded SuperCollider supernova engine (parallel DSP)";

    m.def("set_print_func", &py_sn_set_print_func,
          nb::arg("func").none(),
          "Set the print function for supernova output. Pass None to clear.");

    m.def("set_reply_func", &py_sn_set_reply_func,
          nb::arg("func").none(),
          "Set the reply callback for OSC responses. Pass None to clear.");

    m.def("supernova_new", &py_supernova_new,
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
          nb::arg("realtime_memory_size") = 8192u,
          nb::arg("preferred_sample_rate") = 0u,
          nb::arg("preferred_hardware_buffer_size") = static_cast<int32_t>(0),
          nb::arg("load_graph_defs") = static_cast<uint16_t>(1),
          nb::arg("memory_locking") = false,
          nb::arg("verbosity") = static_cast<int16_t>(0),
          nb::arg("ugen_plugins_path") = nb::none(),
          nb::arg("password") = nb::none(),
          nb::arg("in_device_name") = nb::none(),
          nb::arg("out_device_name") = nb::none(),
          nb::arg("shared_memory_id") = 0,
          nb::arg("threads") = static_cast<uint16_t>(0),
          nb::arg("safety_clip_threshold") = 1.26f,
          "Create a new supernova engine. Returns an opaque handle.");

    m.def("supernova_run", &py_supernova_run,
          nb::arg("handle"),
          "Run the supernova event loop (blocks until terminate is called).");

    m.def("supernova_send_packet", &py_supernova_send_packet,
          nb::arg("handle"), nb::arg("data"),
          "Send an OSC packet directly to supernova. Returns True on success.");

    m.def("supernova_terminate", &py_supernova_terminate,
          nb::arg("handle"),
          "Signal supernova to terminate (unblocks supernova_run).");

    m.def("supernova_cleanup", &py_supernova_cleanup,
          nb::arg("handle"),
          "Clean up supernova resources (deactivate audio, delete server).");
}
