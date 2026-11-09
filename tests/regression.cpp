#include <algorithm>
#include <array>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>
#include <unistd.h>

#include "oal/codec.hpp"
#include "oal/config.hpp"
#include "oal/log.hpp"
#include "oal/wfb_link.hpp"

using namespace oal;

int main() {
    int failures = 0;
    const auto check = [&](bool condition, const char* message) {
        if (!condition) {
            std::fprintf(stderr, "%s\n", message);
            ++failures;
        }
    };

    const std::string path = "/tmp/oal-regression-" + std::to_string(::getpid()) + ".conf";
    {
        std::ofstream file(path);
        file << "[common]\nlog_level=error\ncolor=false\n"
                "[robot]\nrate=100\nmeasure_latency=true\n";
    }
    std::vector<std::string> arguments = {
        "oal_sim", "robot", "--config", path, "--rate", "250", "--no-measure-latency"};
    std::vector<char*> argv;
    for (auto& arg : arguments) argv.push_back(arg.data());
    Config config;
    std::string error;
    check(config.load_arguments(static_cast<int>(argv.size()), argv.data(), &error),
          "cannot load config/CLI");
    const OptionResolver robot(config, "robot");
    check(robot.number("rate", 0) == 250, "CLI must override file");
    check(!robot.boolean("measure_latency", true), "negated CLI must override file");
    check(config.positional() == std::vector<std::string>{"robot"},
          "config loading duplicated positional arguments");
    configure_logging(config);
    check(log_level() == LogLevel::Error, "common logging config ignored");
    std::array<std::string, 3> negative_args = {"test", "--rate", "-2.5"};
    std::array<char*, 3> negative_argv = {
        negative_args[0].data(), negative_args[1].data(), negative_args[2].data()};
    Config negative_config;
    check(negative_config.load_arguments(3, negative_argv.data()) &&
          negative_config.get_double("rate", 0) == -2.5 && negative_config.positional().empty(),
          "negative numeric argument was interpreted as an option");
    std::remove(path.c_str());
    check(!config.load_arguments(static_cast<int>(argv.size()), argv.data(), &error),
          "missing config must fail");
    arguments.push_back("--help");
    argv.clear();
    for (auto& arg : arguments) argv.push_back(arg.data());
    check(config.load_arguments(static_cast<int>(argv.size()), argv.data(), &error) &&
          config.help_requested(), "help must work without opening a missing config");

    ControlPayload control;
    control.axes = {1.0f, -2.5f, 0.25f, 0.0f};
    control.buttons = 0x1234;
    control.mode = 2;
    control.flags = 1;
    control.params = {1.0f, 2.0f, 3.0f, 4.0f};
    const std::vector<std::uint8_t> expected = {
        0,0,128,63, 0,0,32,192, 0,0,128,62, 0,0,0,0,
        0x34,0x12,2,1, 0,0,128,63, 0,0,0,64, 0,0,64,64, 0,0,128,64};
    std::vector<std::uint8_t> payload;
    encode_control(control, payload);
    check(payload == expected, "control wire format changed");
    ControlPayload decoded_control;
    for (std::size_t n = 0; n < payload.size(); ++n) {
        check(!decode_control(payload.data(), n, decoded_control), "short control accepted");
    }
    check(decode_control(payload.data(), payload.size(), decoded_control) &&
          decoded_control.axes == control.axes && decoded_control.params == control.params &&
          decoded_control.buttons == control.buttons && decoded_control.flags == control.flags,
          "control round trip failed");

    Frame frame;
    frame.header.stream = stream_id(Stream::Control);
    frame.header.flags = kFlagEstop;
    frame.header.seq = 0x12345678;
    frame.header.timestamp_ns = 0x0102030405060708ULL;
    frame.payload = payload;
    std::vector<std::uint8_t> wire;
    encode_frame(frame, wire);
    const std::array<std::uint8_t, 24> header = {
        'O','A','L','1', 1,0x80,1,0, 0x78,0x56,0x34,0x12,
        8,7,6,5,4,3,2,1, 36,0,0,0};
    check(wire.size() == 64 && std::equal(header.begin(), header.end(), wire.begin()),
          "frame header wire format changed");
    std::vector<std::uint8_t> direct;
    encode_frame(frame.header, payload.data(), payload.size(), direct);
    check(direct == wire, "direct serialization differs from Frame serialization");
    Frame decoded;
    for (std::size_t n = 0; n < wire.size(); ++n) {
        check(!decode_frame(wire.data(), n, decoded), "truncated frame accepted");
    }
    for (std::size_t offset : {std::size_t{0}, std::size_t{4}, std::size_t{20}, wire.size()-1}) {
        auto corrupt = wire;
        corrupt[offset] ^= 0xFF;
        check(!decode_frame(corrupt.data(), corrupt.size(), decoded), "invalid frame accepted");
    }
    const auto* allocation = wire.data();
    encode_frame(frame, wire);
    check(wire.data() == allocation && wire == direct, "serialization discarded output buffer");

    DebugPayload debug;
    debug.length = static_cast<std::uint8_t>(kDebugMaxBytes);
    debug.text.fill('x');
    encode_debug(debug, payload);
    DebugPayload debug_out;
    check(payload.size() == kDebugMaxBytes + kDebugHeaderBytes &&
          decode_debug(payload.data(), payload.size(), debug_out) && debug_out.length == 255,
          "maximum debug payload failed");
    check(!decode_debug(payload.data(), payload.size()-1, debug_out), "short debug accepted");

    UdpSocket receiver;
    check(receiver.bind("127.0.0.1", 0, &error), "cannot bind UDP test receiver");
    WfbTxChannel sender;
    check(sender.open("127.0.0.1", receiver.local_port(), &error), "cannot open UDP sender");
    payload.assign(kWfbMaxPacketBytes - kHeaderSize, 0x5A);
    check(sender.send(1, 0, 1, 123, payload, &error), "maximum frame send failed");
    std::array<std::uint8_t, kWfbRecvBufferBytes> received{};
    const auto count = receiver.recv(received.data(), received.size(), 1000);
    check(count == static_cast<std::int64_t>(kWfbMaxPacketBytes) &&
          decode_frame(received.data(), static_cast<std::size_t>(count), decoded) &&
          decoded.payload == payload, "maximum UDP frame round trip failed");
    payload.push_back(0);
    check(!sender.send(1, 0, 2, 123, payload, &error), "oversized total frame accepted");
    check(sender.send(1, 0, 3, 123, nullptr, 0, &error), "empty frame send failed");
    const auto empty_count = receiver.recv(received.data(), received.size(), 1000);
    check(empty_count == static_cast<std::int64_t>(kHeaderSize) &&
          decode_frame(received.data(), static_cast<std::size_t>(empty_count), decoded) &&
          decoded.payload.empty(), "empty frame round trip failed");
    return failures == 0 ? 0 : 1;
}
