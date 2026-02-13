// OSC encode/decode module for nanosynth.
// Implements the same wire format as the pure Python osc.py:
//   - Standard OSC 1.0 types: i (int32), f (float32), s (string), b (blob)
//   - Extended types: T (true), F (false), N (nil), d (double)
//   - Arrays: [ ... ]
//   - Bundles: #bundle\0 + timestamp + size-prefixed elements
// Blob decoding attempts to parse as OscBundle then OscMessage (nanosynth convention).

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>
#include <nanobind/stl/optional.h>

#include <Python.h>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include <stdexcept>
#include <algorithm>

namespace nb = nanobind;

// --- Utility: big-endian read/write ---

static inline void write_be_i32(std::vector<uint8_t>& buf, int32_t v) {
    uint32_t u;
    std::memcpy(&u, &v, 4);
    buf.push_back(static_cast<uint8_t>((u >> 24) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >> 16) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >>  8) & 0xFF));
    buf.push_back(static_cast<uint8_t>( u        & 0xFF));
}

static inline void write_be_u32(std::vector<uint8_t>& buf, uint32_t u) {
    buf.push_back(static_cast<uint8_t>((u >> 24) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >> 16) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >>  8) & 0xFF));
    buf.push_back(static_cast<uint8_t>( u        & 0xFF));
}

static inline void write_be_f32(std::vector<uint8_t>& buf, float v) {
    uint32_t u;
    std::memcpy(&u, &v, 4);
    write_be_u32(buf, u);
}

static inline void write_be_u64(std::vector<uint8_t>& buf, uint64_t u) {
    buf.push_back(static_cast<uint8_t>((u >> 56) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >> 48) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >> 40) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >> 32) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >> 24) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >> 16) & 0xFF));
    buf.push_back(static_cast<uint8_t>((u >>  8) & 0xFF));
    buf.push_back(static_cast<uint8_t>( u        & 0xFF));
}

static inline int32_t read_be_i32(const uint8_t* p) {
    uint32_t u = (static_cast<uint32_t>(p[0]) << 24) |
                 (static_cast<uint32_t>(p[1]) << 16) |
                 (static_cast<uint32_t>(p[2]) <<  8) |
                  static_cast<uint32_t>(p[3]);
    int32_t v;
    std::memcpy(&v, &u, 4);
    return v;
}

static inline uint32_t read_be_u32(const uint8_t* p) {
    return (static_cast<uint32_t>(p[0]) << 24) |
           (static_cast<uint32_t>(p[1]) << 16) |
           (static_cast<uint32_t>(p[2]) <<  8) |
            static_cast<uint32_t>(p[3]);
}

static inline float read_be_f32(const uint8_t* p) {
    uint32_t u = read_be_u32(p);
    float v;
    std::memcpy(&v, &u, 4);
    return v;
}

static inline double read_be_f64(const uint8_t* p) {
    uint64_t u = (static_cast<uint64_t>(p[0]) << 56) |
                 (static_cast<uint64_t>(p[1]) << 48) |
                 (static_cast<uint64_t>(p[2]) << 40) |
                 (static_cast<uint64_t>(p[3]) << 32) |
                 (static_cast<uint64_t>(p[4]) << 24) |
                 (static_cast<uint64_t>(p[5]) << 16) |
                 (static_cast<uint64_t>(p[6]) <<  8) |
                  static_cast<uint64_t>(p[7]);
    double v;
    std::memcpy(&v, &u, 8);
    return v;
}

static inline uint64_t read_be_u64(const uint8_t* p) {
    return (static_cast<uint64_t>(p[0]) << 56) |
           (static_cast<uint64_t>(p[1]) << 48) |
           (static_cast<uint64_t>(p[2]) << 40) |
           (static_cast<uint64_t>(p[3]) << 32) |
           (static_cast<uint64_t>(p[4]) << 24) |
           (static_cast<uint64_t>(p[5]) << 16) |
           (static_cast<uint64_t>(p[6]) <<  8) |
            static_cast<uint64_t>(p[7]);
}

// --- OSC string encoding ---

// Encode a string with null terminator, padded to 4-byte boundary.
static void encode_string(std::vector<uint8_t>& buf, const std::string& s) {
    size_t len = s.size() + 1; // include null terminator
    size_t padded = ((len + 3) / 4) * 4;
    buf.insert(buf.end(), s.begin(), s.end());
    buf.resize(buf.size() + (padded - s.size()), 0);
}

// Decode a null-terminated, 4-byte padded string. Returns (string, new offset).
static std::pair<std::string, size_t> decode_string(const uint8_t* data, size_t offset, size_t len) {
    size_t start = offset;
    while (offset < len && data[offset] != 0) offset++;
    std::string s(reinterpret_cast<const char*>(data + start), offset - start);
    size_t actual_length = offset - start;
    size_t padded = ((actual_length + 1 + 3) / 4) * 4;
    return {s, start + padded};
}

// --- OSC blob encoding ---

static void encode_blob(std::vector<uint8_t>& buf, const uint8_t* data, size_t size) {
    write_be_u32(buf, static_cast<uint32_t>(size));
    size_t total = 4 + size;
    buf.insert(buf.end(), data, data + size);
    size_t padded_total = ((total + 3) / 4) * 4;
    size_t pad = padded_total - total;
    for (size_t i = 0; i < pad; i++) buf.push_back(0);
}

// Decode blob. Returns (blob_data, blob_size, new offset).
static std::tuple<const uint8_t*, size_t, size_t> decode_blob(const uint8_t* data, size_t offset, size_t len) {
    if (offset + 4 > len) throw std::runtime_error("truncated blob size");
    uint32_t actual_length = read_be_u32(data + offset);
    offset += 4;
    size_t padded = ((actual_length + 3) / 4) * 4;
    if (offset + padded > len) throw std::runtime_error("truncated blob data");
    const uint8_t* blob_data = data + offset;
    return {blob_data, actual_length, offset + padded};
}

// --- Forward declarations for encode/decode ---

// Encode a single value. Appends type tags to `type_tags` and data to `encoded`.
static void encode_value(nb::handle value, std::string& type_tags, std::vector<uint8_t>& encoded);

// Decode a full message from raw data. Returns Python OscMessage.
static nb::object decode_message_from_raw(const uint8_t* data, size_t len);

// Decode a full bundle from raw data. Returns Python OscBundle.
static nb::object decode_bundle_from_raw(const uint8_t* data, size_t len);


static const uint8_t BUNDLE_PREFIX_BYTES[] = {'#','b','u','n','d','l','e','\0'};
static const uint64_t IMMEDIATELY_VALUE = 1;

// Check if raw data starts with "#bundle\0"
static bool starts_with_bundle(const uint8_t* data, size_t len) {
    if (len < 8) return false;
    return std::memcmp(data, BUNDLE_PREFIX_BYTES, 8) == 0;
}

// --- Encode ---

static void encode_value(nb::handle value, std::string& type_tags, std::vector<uint8_t>& encoded) {
    // Check for bool BEFORE int (Python bool is subclass of int)
    if (nb::isinstance<nb::bool_>(value)) {
        if (nb::cast<bool>(value))
            type_tags += 'T';
        else
            type_tags += 'F';
    }
    else if (value.is_none()) {
        type_tags += 'N';
    }
    else if (nb::isinstance<nb::int_>(value)) {
        type_tags += 'i';
        write_be_i32(encoded, nb::cast<int32_t>(value));
    }
    else if (nb::isinstance<nb::float_>(value)) {
        type_tags += 'f';
        write_be_f32(encoded, nb::cast<float>(value));
    }
    else if (nb::isinstance<nb::str>(value)) {
        type_tags += 's';
        encode_string(encoded, nb::cast<std::string>(value));
    }
    else if (nb::isinstance<nb::bytes>(value)) {
        type_tags += 'b';
        auto bytes_obj = nb::cast<nb::bytes>(value);
        encode_blob(encoded, reinterpret_cast<const uint8_t*>(bytes_obj.c_str()), bytes_obj.size());
    }
    else if (nb::hasattr(value, "to_datagram")) {
        // OscMessage or OscBundle -- encode as blob
        type_tags += 'b';
        nb::bytes datagram = nb::cast<nb::bytes>(value.attr("to_datagram")());
        encode_blob(encoded, reinterpret_cast<const uint8_t*>(datagram.c_str()), datagram.size());
    }
    else if (nb::isinstance<nb::list>(value) || nb::isinstance<nb::tuple>(value)) {
        type_tags += '[';
        for (auto item : value) {
            encode_value(item, type_tags, encoded);
        }
        type_tags += ']';
    }
    else {
        throw nb::type_error("Cannot encode OSC value");
    }
}

static nb::bytes encode_message(const std::string& address, nb::args contents) {
    std::vector<uint8_t> buf;

    // Encode address
    encode_string(buf, address);

    // Build type tags and encoded data
    std::string type_tags = ",";
    std::vector<uint8_t> encoded;

    for (size_t i = 0; i < contents.size(); i++) {
        encode_value(contents[i], type_tags, encoded);
    }

    // Encode type tag string
    encode_string(buf, type_tags);

    // Append encoded data
    buf.insert(buf.end(), encoded.begin(), encoded.end());

    return nb::bytes(reinterpret_cast<const char*>(buf.data()), buf.size());
}

static nb::bytes encode_message_int_address(int32_t address, nb::args contents) {
    std::vector<uint8_t> buf;

    // Encode int address as big-endian i32
    write_be_i32(buf, address);

    // Build type tags and encoded data
    std::string type_tags = ",";
    std::vector<uint8_t> encoded;

    for (size_t i = 0; i < contents.size(); i++) {
        encode_value(contents[i], type_tags, encoded);
    }

    encode_string(buf, type_tags);
    buf.insert(buf.end(), encoded.begin(), encoded.end());

    return nb::bytes(reinterpret_cast<const char*>(buf.data()), buf.size());
}


// --- Decode ---

static nb::tuple decode_message_clean(const uint8_t* data, size_t len) {
    size_t offset = 0;

    auto [address, off1] = decode_string(data, offset, len);
    offset = off1;

    auto [type_tags, off2] = decode_string(data, offset, len);
    offset = off2;

    // Use a vector of Python list handles for the array stack
    nb::list top_contents;
    std::vector<nb::list> array_stack;
    array_stack.push_back(top_contents);

    for (size_t i = 1; i < type_tags.size(); i++) {
        char tag = type_tags[i];
        switch (tag) {
            case 'i': {
                if (offset + 4 > len) throw std::runtime_error("truncated int");
                int32_t v = read_be_i32(data + offset);
                offset += 4;
                array_stack.back().append(nb::int_(v));
                break;
            }
            case 'f': {
                if (offset + 4 > len) throw std::runtime_error("truncated float");
                float v = read_be_f32(data + offset);
                offset += 4;
                array_stack.back().append(nb::float_(v));
                break;
            }
            case 'd': {
                if (offset + 8 > len) throw std::runtime_error("truncated double");
                double v = read_be_f64(data + offset);
                offset += 8;
                array_stack.back().append(nb::float_(v));
                break;
            }
            case 's': {
                auto [s, off3] = decode_string(data, offset, len);
                offset = off3;
                array_stack.back().append(nb::str(s.c_str()));
                break;
            }
            case 'b': {
                auto [blob_data, blob_size, off4] = decode_blob(data, offset, len);
                offset = off4;
                nb::object parsed;
                bool did_parse = false;
                if (starts_with_bundle(blob_data, blob_size)) {
                    try {
                        parsed = decode_bundle_from_raw(blob_data, blob_size);
                        did_parse = true;
                    } catch (...) { PyErr_Clear(); }
                }
                if (!did_parse) {
                    try {
                        parsed = decode_message_from_raw(blob_data, blob_size);
                        did_parse = true;
                    } catch (...) { PyErr_Clear(); }
                }
                if (did_parse) {
                    array_stack.back().append(parsed);
                } else {
                    array_stack.back().append(nb::bytes(reinterpret_cast<const char*>(blob_data), blob_size));
                }
                break;
            }
            case 'T':
                array_stack.back().append(nb::bool_(true));
                break;
            case 'F':
                array_stack.back().append(nb::bool_(false));
                break;
            case 'N':
                array_stack.back().append(nb::none());
                break;
            case '[': {
                nb::list new_array;
                array_stack.back().append(new_array);
                array_stack.push_back(new_array);
                break;
            }
            case ']': {
                if (array_stack.size() > 1)
                    array_stack.pop_back();
                break;
            }
            default:
                throw std::runtime_error(std::string("Unable to parse type '") + tag + "'");
        }
    }

    return nb::make_tuple(nb::str(address.c_str()), top_contents);
}

// Decode message: returns (address, contents) where blobs that parse as
// OscBundle/OscMessage are returned as such (Python-level objects).
static nb::object decode_message_from_raw(const uint8_t* data, size_t len) {
    // Import the Python OscMessage class and construct from decoded data
    nb::module_ osc_mod = nb::module_::import_("nanosynth.osc");
    nb::object OscMessage_cls = osc_mod.attr("OscMessage");
    nb::object OscBundle_cls = osc_mod.attr("OscBundle");

    auto result = decode_message_clean(data, len);
    nb::str address = nb::cast<nb::str>(result[0]);
    nb::list contents = nb::cast<nb::list>(result[1]);

    // Construct OscMessage(address, *contents)
    nb::tuple args = nb::make_tuple(address);
    // Build full args tuple
    nb::list all_args;
    all_args.append(address);
    for (size_t i = 0; i < nb::len(contents); i++) {
        all_args.append(contents[i]);
    }
    return OscMessage_cls(*nb::tuple(all_args));
}

static nb::object decode_bundle_from_raw(const uint8_t* data, size_t len) {
    if (!starts_with_bundle(data, len))
        throw std::runtime_error("datagram is not a bundle");

    nb::module_ osc_mod = nb::module_::import_("nanosynth.osc");
    nb::object OscBundle_cls = osc_mod.attr("OscBundle");

    size_t offset = 8; // skip "#bundle\0"

    // Decode timestamp
    if (offset + 8 > len) throw std::runtime_error("truncated bundle timestamp");
    uint64_t ts_raw = read_be_u64(data + offset);
    offset += 8;

    nb::object timestamp;
    if (ts_raw == IMMEDIATELY_VALUE) {
        timestamp = nb::none();
    } else {
        // Convert NTP timestamp to seconds since Unix epoch
        // Same as Python: (raw / 2**32) - NTP_DELTA
        double seconds = static_cast<double>(ts_raw) / 4294967296.0;
        // NTP_DELTA = (SYSTEM_EPOCH - NTP_EPOCH).days * 24 * 3600
        // For Unix epoch starting 1970-01-01, NTP epoch 1900-01-01:
        // delta = 70 years worth of seconds = 2208988800
        constexpr double NTP_DELTA = 2208988800.0;
        seconds -= NTP_DELTA;
        timestamp = nb::float_(seconds);
    }

    nb::list bundle_contents;
    while (offset < len) {
        if (offset + 4 > len) throw std::runtime_error("truncated bundle element size");
        int32_t element_len = read_be_i32(data + offset);
        offset += 4;
        if (offset + static_cast<size_t>(element_len) > len)
            throw std::runtime_error("truncated bundle element");
        const uint8_t* element_data = data + offset;
        if (starts_with_bundle(element_data, element_len)) {
            bundle_contents.append(decode_bundle_from_raw(element_data, element_len));
        } else {
            bundle_contents.append(decode_message_from_raw(element_data, element_len));
        }
        offset += element_len;
    }

    // Construct OscBundle(timestamp=..., contents=...)
    nb::dict kwargs;
    kwargs["contents"] = nb::tuple(bundle_contents);
    return OscBundle_cls(timestamp, **kwargs);
}

// Python-facing decode functions that take bytes
static nb::tuple decode_message_bytes(nb::bytes datagram) {
    const uint8_t* data = reinterpret_cast<const uint8_t*>(datagram.c_str());
    size_t len = datagram.size();
    return decode_message_clean(data, len);
}

static nb::tuple decode_bundle_bytes(nb::bytes datagram) {
    const uint8_t* data = reinterpret_cast<const uint8_t*>(datagram.c_str());
    size_t len = datagram.size();

    if (!starts_with_bundle(data, len))
        throw std::runtime_error("datagram is not a bundle");

    size_t offset = 8;

    if (offset + 8 > len) throw std::runtime_error("truncated bundle timestamp");
    uint64_t ts_raw = read_be_u64(data + offset);
    offset += 8;

    nb::object timestamp;
    if (ts_raw == IMMEDIATELY_VALUE) {
        timestamp = nb::none();
    } else {
        constexpr double NTP_DELTA = 2208988800.0;
        double seconds = static_cast<double>(ts_raw) / 4294967296.0 - NTP_DELTA;
        timestamp = nb::float_(seconds);
    }

    // Return raw element datagrams for Python-level reconstruction
    nb::list elements;
    while (offset < len) {
        if (offset + 4 > len) throw std::runtime_error("truncated bundle element size");
        int32_t element_len = read_be_i32(data + offset);
        offset += 4;
        if (offset + static_cast<size_t>(element_len) > len)
            throw std::runtime_error("truncated bundle element");
        elements.append(nb::bytes(reinterpret_cast<const char*>(data + offset), element_len));
        offset += element_len;
    }

    return nb::make_tuple(timestamp, elements);
}

NB_MODULE(_osc, m) {
    m.doc() = "Native OSC encode/decode for nanosynth";

    m.def("encode_message", &encode_message,
          nb::arg("address"), nb::arg("contents"),
          "Encode an OSC message with string address to bytes");

    m.def("encode_message_int", &encode_message_int_address,
          nb::arg("address"), nb::arg("contents"),
          "Encode an OSC message with int address to bytes");

    m.def("decode_message", &decode_message_bytes,
          nb::arg("datagram"),
          "Decode an OSC message datagram. Returns (address, contents).");

    m.def("decode_bundle", &decode_bundle_bytes,
          nb::arg("datagram"),
          "Decode an OSC bundle datagram. Returns (timestamp_or_None, [element_bytes, ...]).");
}
