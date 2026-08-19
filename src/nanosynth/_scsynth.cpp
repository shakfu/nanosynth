// nanobind wrapper for libscsynth -- embeds SuperCollider's synthesis engine
// in-process, exposing World_New / World_OpenUDP / World_WaitForQuit etc.

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/optional.h>
#include <nanobind/ndarray.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

#ifdef __APPLE__
#include <unistd.h>

// Registered via atexit to dodge CoreAudio static-destructor crashes on macOS
// by hard-exiting before those destructors run. Caveat: _exit(0) forces exit
// code 0, so a genuine non-zero exit or a crash during shutdown is masked from
// CI/test harnesses. Deliberate trade-off (a clean exit beats a spurious crash
// report); scoped to macOS only.
static void _force_exit_on_teardown() {
    _exit(0);
}
#endif

#include "SC_WorldOptions.h"
#include "SC_World.h"   // World struct, SndBuf, World_GetBuf

namespace nb = nanobind;

// ---------------------------------------------------------------------------
// Print function redirection
// ---------------------------------------------------------------------------

static nb::object g_print_func;
static std::mutex g_print_mutex;

static int scsynth_print_func(const char* fmt, va_list ap) {
    // First try a stack buffer; fall back to dynamic allocation for long messages
    // (e.g. verbose plugin loading can exceed 4096 bytes).
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
    // Do not touch Python once the interpreter is finalizing/gone (UB); return
    // the formatted length without dispatching.
    if (!Py_IsInitialized()) {
        return n;
    }
    // Lock order is GIL-then-mutex everywhere in this file. The Python-side
    // entry points (set_print_func, set_reply_func, world_send_packet) are
    // entered with the GIL already held and then take these mutexes, so
    // taking the mutex first here and blocking on the GIL afterwards would
    // invert the order and deadlock the whole process.
    nb::gil_scoped_acquire gil;
    nb::object callback;
    {
        std::lock_guard<std::mutex> lock(g_print_mutex);
        callback = g_print_func;  // refcount bump is safe: GIL is held
    }
    // Called outside the lock so a slow handler cannot stall an unrelated
    // send_packet, which takes the same mutex.
    if (callback.ptr() != nullptr && !callback.is_none()) {
        try {
            callback(buf);
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

struct WorldHandle {
    World* world;
    WorldStrings* strings;
    // Set once the World has been explicitly torn down (world_cleanup or
    // world_wait_for_quit). Until then scsynth still holds raw const char*
    // into `strings`, so they must not be freed. See the capsule destructor.
    bool cleaned = false;
};

// ---------------------------------------------------------------------------
// No-op reply function for World_SendPacket (avoids null dereference when
// scsynth internally replies to commands like /quit or /notify).
// ---------------------------------------------------------------------------

static void noop_reply_func(struct ReplyAddress*, char*, int) {}

// ---------------------------------------------------------------------------
// Reply function redirection
// ---------------------------------------------------------------------------

static nb::object g_reply_func;
static std::mutex g_reply_mutex;

static void python_reply_func(struct ReplyAddress*, char* buf, int size) {
    // Do not acquire the GIL on a finalizing/gone interpreter (UB). Narrow
    // shutdown-ordering guard.
    if (!Py_IsInitialized()) {
        return;
    }
    // GIL before mutex -- see the note in scsynth_print_func. This runs on
    // scsynth's reply thread while a Python thread may be inside
    // world_send_packet holding the GIL and waiting for g_reply_mutex.
    nb::gil_scoped_acquire gil;
    nb::object callback;
    {
        std::lock_guard<std::mutex> lock(g_reply_mutex);
        callback = g_reply_func;  // refcount bump is safe: GIL is held
    }
    if (callback.ptr() == nullptr || callback.is_none()) {
        return;
    }
    // Dispatched outside the lock: holding it across the Python handler would
    // block every send_packet for the handler's duration.
    try {
        // Copy the reply data into a Python bytes object
        nb::bytes data(buf, static_cast<size_t>(size));
        callback(data);
    } catch (...) {
        // Swallow Python exceptions to avoid crashing scsynth's
        // internal reply path.
    }
}

static void py_set_reply_func(nb::object func) {
    std::lock_guard<std::mutex> lock(g_reply_mutex);
    if (func.is_none()) {
        g_reply_func = nb::none();
    } else {
        g_reply_func = func;
    }
}

// ---------------------------------------------------------------------------
// Module functions
// ---------------------------------------------------------------------------

static void py_set_print_func(nb::object func) {
    {
        std::lock_guard<std::mutex> lock(g_print_mutex);
        if (func.is_none()) {
            g_print_func = nb::none();
            // SetPrintFunc with our no-op handler to avoid null dereference
        } else {
            g_print_func = func;
        }
    }
    // Outside the lock: if this ever logged, scsynth_print_func would re-enter
    // the same non-recursive mutex.
    SetPrintFunc(scsynth_print_func);
}

// Cross-engine guard. scsynth and supernova each statically embed the full
// SuperCollider server core and share process-global singletons (the dlopen'd
// UGen plugin registry, the global FFT init, etc.). Creating one kind after
// the other has run in the same process crashes -- in either order, and even
// after a clean quit. The two extension modules share no symbols, so they
// coordinate through an environment variable. Throws (surfaced to Python as
// ServerCannotBoot) instead of letting the process segfault.
//
// Caveat (M15): the env var is process-global and inherited across fork() /
// multiprocessing, so a forked child sees the parent's claim and would be
// wrongly blocked from booting its own engine kind; and getenv-then-setenv is
// not atomic against a concurrent claim on another thread. This is accepted:
// the two extension modules share no symbols, so a process-local static cannot
// coordinate across them, and an env var is the available cross-module channel.
// Boot from the main thread of each process; do not rely on the guard surviving
// a fork.
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

// Release the claim so a failed World_New does not leave the process claimed
// for scsynth for its lifetime (wrongly rejecting a later supernova boot even
// though no engine is running). See the RAII guard in py_world_new (M14).
static void nanosynth_release_engine() {
#ifdef _WIN32
    _putenv_s("NANOSYNTH_ACTIVE_ENGINE", "");
#else
    unsetenv("NANOSYNTH_ACTIVE_ENGINE");
#endif
}

// Releases the engine claim on stack unwind unless explicitly committed (M14).
namespace {
struct EngineClaimGuard {
    bool committed = false;
    ~EngineClaimGuard() {
        if (!committed)
            nanosynth_release_engine();
    }
};
}  // namespace

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
    nanosynth_claim_engine("scsynth");
    // Release the claim automatically if World_New (or anything below) throws (M14).
    EngineClaimGuard claim_guard;
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

#ifdef __APPLE__
    // Register a C-level atexit handler that calls _exit(0) to prevent
    // CoreAudio static destructor crashes on macOS. Registered after
    // World_New so it runs before CoreAudio's destructors in the
    // reverse-order atexit chain. Python atexit handlers still run
    // normally (they execute during Py_FinalizeEx, before C atexit).
    static bool exit_guard_registered = false;
    if (!exit_guard_registered) {
        std::atexit(_force_exit_on_teardown);
        exit_guard_registered = true;
    }
#endif

    // World is fully constructed: keep the engine claim (do not release it).
    claim_guard.committed = true;
    // Pack World* and WorldStrings* into a single handle so the capsule
    // destructor (a plain function pointer) can clean up both.
    auto* handle = new WorldHandle{world, strings};
    return nb::capsule(handle, "WorldHandle", [](void* p) noexcept {
        auto* h = static_cast<WorldHandle*>(p);
        // We do NOT call World_Cleanup here: the user manages the world
        // lifecycle explicitly (world_wait_for_quit / world_cleanup), and
        // tearing the world down from a GC-triggered destructor could race a
        // still-running engine thread.
        //
        // Only free the option strings if the world was explicitly cleaned. If
        // it was not (the handle is being GC'd while a World may still be live,
        // e.g. an abandoned boot with an open port), scsynth still holds raw
        // const char* into `strings` -- mPassword/mRestrictedPath are read on
        // every incoming packet and file/buffer command -- so freeing them here
        // would be a use-after-free on the engine's network/command thread.
        // Deliberately leak in that abnormal case: a one-time bounded leak is
        // strictly safer than a UAF. See REVIEW.md H3.
        if (h->cleaned) {
            delete h->strings;
        }
        delete h;
    });
}

static World* extract_world(nb::capsule& cap) {
    if (!cap.data()) {
        throw std::runtime_error("World handle is null (already cleaned up?)");
    }
    return static_cast<WorldHandle*>(cap.data())->world;
}

// --- Direct in-process buffer access -------------------------------------
//
// scsynth runs in-process, so we can read/write a buffer's float storage
// directly with a memcpy instead of round-tripping sample data through OSC
// (/b_getn, /b_setn) with their datagram-size limits. The buffer must already
// be allocated (e.g. via /b_alloc + sync()).
//
// SAFETY CONTRACT: these read buf->data/frames/channels and then memcpy, with
// no lock against the engine's command thread. A get/set racing a *reading or
// writing synth* on a stable buffer only risks a torn/glitched sample block.
// But a get/set racing a command that FREES or REALLOCATES the same buffer
// (/b_free, /b_alloc, /b_read, /b_close) is a use-after-free / out-of-bounds
// access, not a benign glitch -- the shape is read at one instant and data at
// another. Callers MUST ensure no such buffer command for `buf_id` is in flight
// during the transfer (e.g. perform it between sync() points with no pending
// buffer commands). scsynth exposes no per-buffer lock to enforce this here.
// See REVIEW.md H2.

static SndBuf* get_sndbuf(World* world, uint32_t buf_id) {
    if (buf_id >= world->mNumSndBufs) {
        throw std::runtime_error("buffer index out of range");
    }
    return World_GetBuf(world, buf_id);
}

static nb::tuple py_world_buffer_info(nb::capsule& world_cap, uint32_t buf_id) {
    World* world = extract_world(world_cap);
    SndBuf* buf = get_sndbuf(world, buf_id);
    return nb::make_tuple(buf->frames, buf->channels, buf->samplerate);
}

static nb::ndarray<nb::numpy, float, nb::ndim<2>>
py_world_buffer_get(nb::capsule& world_cap, uint32_t buf_id) {
    World* world = extract_world(world_cap);
    SndBuf* buf = get_sndbuf(world, buf_id);
    if (buf->data == nullptr || buf->frames <= 0 || buf->channels <= 0) {
        throw std::runtime_error("buffer is not allocated");
    }
    size_t frames = static_cast<size_t>(buf->frames);
    size_t channels = static_cast<size_t>(buf->channels);
    size_t n = frames * channels;
    // Own a copy so the returned array stays valid even if the buffer is later
    // freed or reallocated by the engine.
    float* copy = new float[n];
    std::memcpy(copy, buf->data, n * sizeof(float));
    nb::capsule owner(copy, [](void* p) noexcept { delete[] static_cast<float*>(p); });
    return nb::ndarray<nb::numpy, float, nb::ndim<2>>(copy, {frames, channels}, owner);
}

static void py_world_buffer_set(
    nb::capsule& world_cap, uint32_t buf_id,
    nb::ndarray<const float, nb::ndim<2>, nb::c_contig> data) {
    World* world = extract_world(world_cap);
    SndBuf* buf = get_sndbuf(world, buf_id);
    if (buf->data == nullptr) {
        throw std::runtime_error("buffer is not allocated");
    }
    if (static_cast<int>(data.shape(0)) != buf->frames ||
        static_cast<int>(data.shape(1)) != buf->channels) {
        throw std::runtime_error(
            "array shape does not match buffer (frames, channels)");
    }
    size_t n = static_cast<size_t>(buf->frames) * static_cast<size_t>(buf->channels);
    std::memcpy(buf->data, data.data(), n * sizeof(float));
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
    // World is now torn down; its raw pointers into WorldStrings are dead, so
    // the capsule destructor may safely free them.
    static_cast<WorldHandle*>(world_cap.data())->cleaned = true;
}

static void py_world_cleanup(nb::capsule& world_cap, bool unload_plugins) {
    World* world = extract_world(world_cap);
    {
        nb::gil_scoped_release release;
        World_Cleanup(world, unload_plugins);
    }
    static_cast<WorldHandle*>(world_cap.data())->cleaned = true;
}

static bool py_world_send_packet(nb::capsule& world_cap, nb::bytes data) {
    World* world = extract_world(world_cap);
    int size = static_cast<int>(data.size());
    // Defensive copy: World_SendPacket takes char* but should not modify the
    // data. Copying into a mutable buffer avoids undefined behavior from
    // const_cast on the immutable Python bytes object.
    std::vector<char> buf(data.c_str(), data.c_str() + size);
    // Use the Python reply callback if one is registered, otherwise noop.
    ReplyFunc reply_fn;
    {
        std::lock_guard<std::mutex> lock(g_reply_mutex);
        reply_fn = (g_reply_func.ptr() != nullptr && !g_reply_func.is_none())
                   ? python_reply_func
                   : noop_reply_func;
    }
    bool result;
    {
        nb::gil_scoped_release release;
        result = World_SendPacket(world, size, buf.data(), reply_fn);
    }
    return result;
}

// ---------------------------------------------------------------------------
// NRT (Non-Real-Time) rendering
// ---------------------------------------------------------------------------

static void py_world_nrt_render(
    const std::string& cmd_filename,
    const std::string& output_filename,
    uint32_t sample_rate,
    std::optional<std::string> input_filename,
    std::optional<std::string> header_format,
    std::optional<std::string> sample_format,
    uint32_t num_output_bus_channels,
    uint32_t num_input_bus_channels,
    uint32_t block_size,
    uint32_t num_buffers,
    uint32_t max_nodes,
    uint32_t max_graph_defs,
    uint32_t realtime_memory_size,
    uint32_t preferred_hardware_buffer_size,
    int verbosity,
    std::optional<std::string> ugen_plugins_path,
    uint32_t num_audio_bus_channels,
    uint32_t num_control_bus_channels,
    uint32_t max_wire_bufs,
    uint32_t num_rgens
) {
    nanosynth_claim_engine("scsynth");
    // Allocate string storage that outlives World_New
    auto* strings = new WorldStrings();

    WorldOptions opts;
    opts.mRealTime = false;
    opts.mPreferredSampleRate = sample_rate;
    opts.mNumOutputBusChannels = num_output_bus_channels;
    opts.mNumInputBusChannels = num_input_bus_channels;
    opts.mBufLength = block_size;
    opts.mNumBuffers = num_buffers;
    opts.mMaxNodes = max_nodes;
    opts.mMaxGraphDefs = max_graph_defs;
    opts.mRealTimeMemorySize = realtime_memory_size;
    opts.mPreferredHardwareBufferFrameSize = preferred_hardware_buffer_size;
    opts.mVerbosity = verbosity;
    opts.mNumAudioBusChannels = num_audio_bus_channels;
    opts.mNumControlBusChannels = num_control_bus_channels;
    opts.mMaxWireBufs = max_wire_bufs;
    opts.mNumRGens = num_rgens;
    opts.mLoadGraphDefs = 0;
    opts.mRendezvous = false;

    // NRT-specific file paths -- store in WorldStrings for lifetime
    // cmd_filename and output_filename are required; use a temporary
    // std::string member to keep the c_str() alive.
    strings->password = cmd_filename;  // repurpose unused field
    opts.mNonRealTimeCmdFilename = strings->password.c_str();

    strings->restricted_path = output_filename;  // repurpose unused field
    opts.mNonRealTimeOutputFilename = strings->restricted_path.c_str();

    if (input_filename.has_value()) {
        strings->in_device_name = *input_filename;
        opts.mNonRealTimeInputFilename = strings->in_device_name.c_str();
    }
    if (header_format.has_value()) {
        strings->out_device_name = *header_format;
        opts.mNonRealTimeOutputHeaderFormat = strings->out_device_name.c_str();
    }
    if (sample_format.has_value()) {
        strings->input_streams_enabled = *sample_format;
        opts.mNonRealTimeOutputSampleFormat = strings->input_streams_enabled.c_str();
    }
    if (ugen_plugins_path.has_value()) {
        strings->ugen_plugins_path = *ugen_plugins_path;
        opts.mUGensPluginPath = strings->ugen_plugins_path.c_str();
    }

    World* world;
    {
        nb::gil_scoped_release release;
        world = World_New(&opts);
    }

    if (!world) {
        delete strings;
        throw std::runtime_error("World_New failed for NRT rendering");
    }

    try {
        nb::gil_scoped_release release;
        // World_NonRealTimeSynthesis calls World_Cleanup internally
        World_NonRealTimeSynthesis(world, &opts);
    } catch (const std::exception& e) {
        delete strings;
        throw std::runtime_error(std::string("NRT rendering failed: ") + e.what());
    }

    delete strings;
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

    m.def("world_buffer_info", &py_world_buffer_info,
          nb::arg("world"), nb::arg("buffer_id"),
          "Return (frames, channels, sample_rate) for a buffer.");

    m.def("world_buffer_get", &py_world_buffer_get,
          nb::arg("world"), nb::arg("buffer_id"),
          "Copy a buffer's samples into a new (frames, channels) float32 array.");

    m.def("world_buffer_set", &py_world_buffer_set,
          nb::arg("world"), nb::arg("buffer_id"), nb::arg("data"),
          "Copy a (frames, channels) float32 array into a buffer's samples.");

    m.def("set_reply_func", &py_set_reply_func,
          nb::arg("func").none(),
          "Set the reply callback for OSC responses. Pass None to clear.");

    m.def("world_nrt_render", &py_world_nrt_render,
          nb::arg("cmd_filename"),
          nb::arg("output_filename"),
          nb::arg("sample_rate") = 44100u,
          nb::arg("input_filename") = nb::none(),
          nb::arg("header_format") = nb::none(),
          nb::arg("sample_format") = nb::none(),
          nb::arg("num_output_bus_channels") = 2u,
          nb::arg("num_input_bus_channels") = 0u,
          nb::arg("block_size") = 64u,
          nb::arg("num_buffers") = 1024u,
          nb::arg("max_nodes") = 1024u,
          nb::arg("max_graph_defs") = 1024u,
          nb::arg("realtime_memory_size") = 8192u,
          nb::arg("preferred_hardware_buffer_size") = 8192u,
          nb::arg("verbosity") = 0,
          nb::arg("ugen_plugins_path") = nb::none(),
          nb::arg("num_audio_bus_channels") = 1024u,
          nb::arg("num_control_bus_channels") = 16384u,
          nb::arg("max_wire_bufs") = 64u,
          nb::arg("num_rgens") = 64u,
          "Render a binary OSC command file to an audio file (non-real-time).");
}
