// nanobind wrapper for RtMidiIn -- thin binding for MIDI input.
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
    std::lock_guard<std::mutex> lock(handle->callback_mutex);
    if (handle->callback.ptr() != nullptr && !handle->callback.is_none()) {
        nb::gil_scoped_acquire gil;
        try {
            nb::bytes data(
                reinterpret_cast<const char*>(message->data()),
                message->size()
            );
            handle->callback(data);
        } catch (...) {
            // Swallow Python exceptions to avoid crashing the MIDI thread.
        }
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

static nb::capsule py_open_input(unsigned int port, const std::string& name) {
    auto* handle = new MidiInHandle();
    try {
        handle->midi_in = new RtMidiIn();
        handle->midi_in->openPort(port, name);
    } catch (const RtMidiError& e) {
        delete handle;
        throw std::runtime_error(std::string("Failed to open MIDI port: ") + e.what());
    }
    return nb::capsule(handle, "MidiInHandle", [](void* p) noexcept {
        auto* h = static_cast<MidiInHandle*>(p);
        // Clear callback before destruction to avoid dangling references
        {
            std::lock_guard<std::mutex> lock(h->callback_mutex);
            h->callback = nb::object();
        }
        delete h;
    });
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
    return nb::capsule(handle, "MidiInHandle", [](void* p) noexcept {
        auto* h = static_cast<MidiInHandle*>(p);
        {
            std::lock_guard<std::mutex> lock(h->callback_mutex);
            h->callback = nb::object();
        }
        delete h;
    });
}

static void py_close_input(nb::capsule& cap) {
    auto* handle = extract_handle(cap);
    if (handle->midi_in) {
        handle->midi_in->cancelCallback();
        handle->midi_in->closePort();
    }
}

static void py_set_callback(nb::capsule& cap, nb::object func) {
    auto* handle = extract_handle(cap);
    {
        std::lock_guard<std::mutex> lock(handle->callback_mutex);
        if (func.is_none()) {
            handle->callback = nb::object();
            handle->midi_in->cancelCallback();
        } else {
            handle->callback = func;
            // Ignore sysex, timing, and active sensing by default
            handle->midi_in->ignoreTypes(true, true, true);
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
// Module definition
// ---------------------------------------------------------------------------

NB_MODULE(_midi, m) {
    m.doc() = "MIDI input via RtMidi";

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
          "Set the MIDI callback. Called with raw bytes. Pass None to clear.");

    m.def("clear_callback", &py_clear_callback,
          nb::arg("handle"),
          "Clear the MIDI callback.");
}
