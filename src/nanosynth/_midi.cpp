// nanobind wrapper for RtMidiIn/RtMidiOut -- thin binding for MIDI I/O.
// Follows the same callback/capsule pattern as _scsynth.cpp.

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include <mutex>
#include <vector>
#include <string>

#include "RtMidi.h"

namespace nb = nanobind;

// ---------------------------------------------------------------------------
// RtMidiIn handle wrapped in a nanobind capsule
// ---------------------------------------------------------------------------

struct MidiInHandle {
    RtMidiIn* midi_in;
    nb::object callback;
    std::mutex callback_mutex;

    MidiInHandle() : midi_in(nullptr) {}
    ~MidiInHandle() {
        delete midi_in;
    }
};

static MidiInHandle* extract_handle(nb::capsule& cap) {
    if (!cap.data()) {
        throw std::runtime_error("MIDI handle is null (already closed?)");
    }
    return static_cast<MidiInHandle*>(cap.data());
}

// ---------------------------------------------------------------------------
// RtMidi callback -- routes raw MIDI bytes to Python
// ---------------------------------------------------------------------------

static void rtmidi_callback(
    double /*timeStamp*/,
    std::vector<unsigned char>* message,
    void* userData
) {
    auto* handle = static_cast<MidiInHandle*>(userData);
    // Do not touch Python if the interpreter is finalizing/gone: acquiring the
    // GIL on a torn-down interpreter is undefined. Narrow shutdown-ordering
    // guard (the port is normally closed before finalization).
    if (!Py_IsInitialized()) {
        return;
    }
    // GIL before mutex. set_callback/clear_callback and the capsule destructor
    // all run with the GIL held and then take callback_mutex; taking the mutex
    // first here and blocking on the GIL afterwards would invert that order
    // and deadlock the process.
    nb::gil_scoped_acquire gil;
    nb::object callback;
    {
        std::lock_guard<std::mutex> lock(handle->callback_mutex);
        callback = handle->callback;  // refcount bump is safe: GIL is held
    }
    if (callback.ptr() == nullptr || callback.is_none()) {
        return;
    }
    // Dispatched outside the lock, and against our own reference, so the
    // handler stays alive even if it is cleared concurrently.
    try {
        nb::bytes data(
            reinterpret_cast<const char*>(message->data()),
            message->size()
        );
        callback(data);
    } catch (nb::python_error &e) {
        // Do not crash the RtMidi thread, but do not silently swallow a broken
        // handler either -- report it via sys.unraisablehook (prints to stderr
        // by default) so a bug surfaces during live performance. The GIL is
        // held here, so PyErr_* is safe.
        e.restore();
        PyErr_WriteUnraisable(callback.ptr());
    } catch (...) {
        PyErr_SetString(PyExc_RuntimeError,
                        "unknown C++ exception in MIDI handler");
        PyErr_WriteUnraisable(callback.ptr());
    }
}

// ---------------------------------------------------------------------------
// Module functions
// ---------------------------------------------------------------------------

static nb::list py_list_input_ports() {
    RtMidiIn midi_in;
    nb::list result;
    unsigned int count = midi_in.getPortCount();
    for (unsigned int i = 0; i < count; i++) {
        result.append(nb::str(midi_in.getPortName(i).c_str()));
    }
    return result;
}

// Capsule destructor. Runs with the GIL held (Python dealloc). Deleting the
// RtMidiIn joins its input thread, which may be blocked in rtmidi_callback
// waiting for the GIL, so the GIL is released around the delete.
static void destroy_input_handle(void* p) noexcept {
    auto* h = static_cast<MidiInHandle*>(p);
    {
        nb::gil_scoped_release release;
        delete h->midi_in;
        h->midi_in = nullptr;
    }
    {
        std::lock_guard<std::mutex> lock(h->callback_mutex);
        h->callback = nb::object();
    }
    delete h;
}

static nb::capsule py_open_input(unsigned int port, const std::string& name) {
    auto* handle = new MidiInHandle();
    try {
        handle->midi_in = new RtMidiIn();
        handle->midi_in->openPort(port, name);
    } catch (const RtMidiError& e) {
        delete handle;
        throw std::runtime_error(std::string("Failed to open MIDI port: ") + e.what());
    }
    return nb::capsule(handle, "MidiInHandle", destroy_input_handle);
}

static nb::capsule py_open_virtual_input(const std::string& name) {
    auto* handle = new MidiInHandle();
    try {
        handle->midi_in = new RtMidiIn();
        handle->midi_in->openVirtualPort(name);
    } catch (const RtMidiError& e) {
        delete handle;
        throw std::runtime_error(std::string("Failed to open virtual MIDI port: ") + e.what());
    }
    return nb::capsule(handle, "MidiInHandle", destroy_input_handle);
}

static void py_close_input(nb::capsule& cap) {
    auto* handle = extract_handle(cap);
    if (handle->midi_in) {
        // closePort joins the input thread (ALSA), which may be blocked in
        // rtmidi_callback waiting for the GIL: release it or both deadlock.
        nb::gil_scoped_release release;
        handle->midi_in->closePort();
    }
}

static void py_set_callback(nb::capsule& cap, nb::object func,
                            bool ignore_sysex, bool ignore_timing,
                            bool ignore_sensing) {
    auto* handle = extract_handle(cap);
    {
        std::lock_guard<std::mutex> lock(handle->callback_mutex);
        if (func.is_none()) {
            handle->callback = nb::object();
            handle->midi_in->cancelCallback();
        } else {
            handle->callback = func;
            handle->midi_in->ignoreTypes(ignore_sysex, ignore_timing, ignore_sensing);
            handle->midi_in->setCallback(rtmidi_callback, handle);
        }
    }
}

static void py_clear_callback(nb::capsule& cap) {
    auto* handle = extract_handle(cap);
    {
        std::lock_guard<std::mutex> lock(handle->callback_mutex);
        handle->callback = nb::object();
    }
    handle->midi_in->cancelCallback();
}

// ---------------------------------------------------------------------------
// MIDI output
// ---------------------------------------------------------------------------

static RtMidiOut* extract_output(nb::capsule& cap) {
    if (!cap.data()) {
        throw std::runtime_error("MIDI output handle is null (already closed?)");
    }
    return static_cast<RtMidiOut*>(cap.data());
}

static nb::capsule wrap_output(RtMidiOut* out) {
    return nb::capsule(out, "RtMidiOut", [](void* p) noexcept {
        delete static_cast<RtMidiOut*>(p);
    });
}

static nb::list py_list_output_ports() {
    RtMidiOut midi_out;
    nb::list result;
    unsigned int count = midi_out.getPortCount();
    for (unsigned int i = 0; i < count; i++) {
        result.append(nb::str(midi_out.getPortName(i).c_str()));
    }
    return result;
}

static nb::capsule py_open_output(unsigned int port, const std::string& name) {
    auto* out = new RtMidiOut();
    try {
        out->openPort(port, name);
    } catch (const RtMidiError& e) {
        delete out;
        throw std::runtime_error(std::string("Failed to open MIDI port: ") + e.what());
    }
    return wrap_output(out);
}

static nb::capsule py_open_virtual_output(const std::string& name) {
    auto* out = new RtMidiOut();
    try {
        out->openVirtualPort(name);
    } catch (const RtMidiError& e) {
        delete out;
        throw std::runtime_error(std::string("Failed to open virtual MIDI port: ") + e.what());
    }
    return wrap_output(out);
}

static void py_close_output(nb::capsule& cap) {
    extract_output(cap)->closePort();
}

static void py_send_message(nb::capsule& cap, nb::bytes data) {
    auto* out = extract_output(cap);
    const auto* bytes = static_cast<const unsigned char*>(data.data());
    std::vector<unsigned char> message(bytes, bytes + data.size());
    // sendMessage may block briefly in the OS MIDI layer; let other threads run.
    nb::gil_scoped_release release;
    try {
        out->sendMessage(&message);
    } catch (const RtMidiError& e) {
        throw std::runtime_error(std::string("Failed to send MIDI message: ") + e.what());
    }
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

NB_MODULE(_midi, m) {
    m.doc() = "MIDI input and output via RtMidi";

    m.def("list_input_ports", &py_list_input_ports,
          "Return a list of available MIDI input port names.");

    m.def("open_input", &py_open_input,
          nb::arg("port"), nb::arg("name") = "nanosynth",
          "Open a MIDI input port by index. Returns an opaque handle.");

    m.def("open_virtual_input", &py_open_virtual_input,
          nb::arg("name") = "nanosynth",
          "Open a virtual MIDI input port. Returns an opaque handle.");

    m.def("close_input", &py_close_input,
          nb::arg("handle"),
          "Close a MIDI input port.");

    m.def("set_callback", &py_set_callback,
          nb::arg("handle"), nb::arg("func").none(),
          nb::arg("ignore_sysex") = true, nb::arg("ignore_timing") = true,
          nb::arg("ignore_sensing") = true,
          "Set the MIDI callback. Called with raw bytes. Pass None to clear.");

    m.def("clear_callback", &py_clear_callback,
          nb::arg("handle"),
          "Clear the MIDI callback.");

    m.def("list_output_ports", &py_list_output_ports,
          "Return a list of available MIDI output port names.");

    m.def("open_output", &py_open_output,
          nb::arg("port"), nb::arg("name") = "nanosynth",
          "Open a MIDI output port by index. Returns an opaque handle.");

    m.def("open_virtual_output", &py_open_virtual_output,
          nb::arg("name") = "nanosynth",
          "Open a virtual MIDI output port. Returns an opaque handle.");

    m.def("close_output", &py_close_output,
          nb::arg("handle"),
          "Close a MIDI output port.");

    m.def("send_message", &py_send_message,
          nb::arg("handle"), nb::arg("data"),
          "Send one raw MIDI message.");
}
