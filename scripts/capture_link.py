#!/usr/bin/env python3
"""Capture existing WFB statistics on demand; never transmit test traffic."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time

STREAMS = ("control", "telemetry", "debug", "test_up", "test_down")


def capture_node(role, duration):
    port = 8102 if role == "robot" else 8103
    deadline = time.monotonic() + duration
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        pending = b""
        while time.monotonic() < deadline:
            sock.settimeout(min(3, deadline - time.monotonic()))
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                if time.monotonic() >= deadline:
                    break
                raise RuntimeError("WFB statistics stopped arriving")
            if not chunk:
                raise RuntimeError("WFB statistics connection closed")
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                msg = json.loads(line)
                if msg.get("type") in ("tx", "rx") and msg.get("id", "").split()[0] in STREAMS:
                    print(json.dumps({"node": role, "message": msg}), flush=True)


def counter(message, name):
    value = message["packets"].get(name, 0)
    return value[-1] if isinstance(value, list) else value


def summarize(records):
    groups = {}
    for record in records:
        msg = record["message"]
        groups.setdefault((record["node"], msg["id"]), []).append(msg)
    result = {}
    for key, messages in groups.items():
        first, last = messages[0], messages[-1]
        elapsed = last["timestamp"] - first["timestamp"]
        if len(messages) < 2 or elapsed <= 0:
            raise ValueError(f"insufficient samples: {key}")
        delta = {name: counter(last, name) - counter(first, name) for name in last["packets"]}
        # Check every adjacent sample: a mid-window counter reset invalidates the window.
        for before, after in zip(messages, messages[1:]):
            if after["timestamp"] <= before["timestamp"] or any(
                counter(after, name) < counter(before, name) for name in after["packets"]
            ):
                raise ValueError(f"WFB restarted/counters reset: {key}; capture again")
        result[key] = {"seconds": elapsed, "delta": delta, "last": last}
    return result


def describe(summary):
    lines = ["OAL passive capture of existing continuous traffic", "",
             "Stream / direction       TX fps   RX fps   TX kbit/s  RX kbit/s  RX payload kbit/s  Loss %  FEC recovered"]
    rows = []
    for stream, sender, receiver, payload_size in [
        ("control", "controller", "robot", 36),
        ("telemetry", "robot", "controller", 340),
        ("debug", "robot", "controller", None),
    ]:
        tx = summary[(sender, stream + " tx")]
        rx = summary[(receiver, stream + " rx")]
        td, rd = tx["delta"], rx["delta"]
        tx_fps, rx_fps = td["incoming"] / tx["seconds"], rd["out"] / rx["seconds"]
        tx_kbps = td["incoming_bytes"] * 8 / tx["seconds"] / 1000
        rx_kbps = rd["out_bytes"] * 8 / rx["seconds"] / 1000
        payload_kbps = (rd["out"] * payload_size if payload_size is not None else
                        max(0, rd["out_bytes"] - rd["out"] * 28)) * 8 / rx["seconds"] / 1000
        lost = rd["lost"]
        total = rd["out"] + lost
        loss = 100 * lost / total if total else None
        row = {"stream": stream, "sender": sender, "receiver": receiver,
               "tx_seconds": tx["seconds"], "rx_seconds": rx["seconds"],
               "tx_fps": tx_fps, "rx_fps": rx_fps, "tx_kbps": tx_kbps,
               "rx_kbps": rx_kbps, "rx_payload_kbps": payload_kbps,
               "rx_packets": rd["out"], "fec_lost": lost, "loss_pct": loss,
               "fec_recovered": rd["fec_rec"], "tx_dropped": td["dropped"],
               "tx_truncated": td["truncated"],
               "injected_kbps": td["injected_bytes"] * 8 / tx["seconds"] / 1000}
        rows.append(row)
        loss_text = f"{loss:.3f}" if loss is not None else "n/a"
        lines.append(f"{stream:10} {sender[:1]}->{receiver[:1]}       {tx_fps:7.2f}  {rx_fps:7.2f}  "
                     f"{tx_kbps:9.3f}  {rx_kbps:9.3f}  {payload_kbps:17.3f}  {loss_text:>6}  {rd['fec_rec']:13}")
    lines += ["", "c=controller; r=robot; kbit/s uses 1000 bits/s.",
              "TX/RX kbit/s include the 28-byte OAL header, excluding UDP/IP/WFB/FEC overhead.",
              "RX payload excludes the OAL header; delivery is measured at WFB's local UDP output.",
              "Loss = receiver FEC lost / (receiver output + FEC lost), within its own window.",
              "TX/RX windows are independently sampled; raw count subtraction is not a loss measurement."]
    for row in rows:
        lines.append(f"{row['stream']}: TX window={row['tx_seconds']:.3f}s, RX window={row['rx_seconds']:.3f}s, "
                     f"TX drop/truncate={row['tx_dropped']}/{row['tx_truncated']}, "
                     f"WFB injected={row['injected_kbps']:.3f} kbit/s (not full PHY airtime)")
    active_tests = [f"{node}/{ident}" for (node, ident), item in summary.items()
                    if ident.split()[0].startswith("test_") and
                    (item["delta"].get("incoming", 0) or item["delta"].get("out", 0))]
    lines.append("Extra test streams: " + (", ".join(active_tests) if active_tests else "idle"))
    lines.append("No probe traffic injected. No RTT/one-way latency inferred from these counters.")
    if any(row["tx_fps"] == 0 or row["rx_fps"] == 0 for row in rows[:2]):
        lines.append("WARNING: a primary stream has no traffic.")
    return "\n".join(lines) + "\n", rows


def run_capture(command, target):
    with target.open("w") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(f"{target.name}: {result.stderr.strip()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot", help="robot SSH target, e.g. arespi@10.166.241.115")
    parser.add_argument("--robot-repo", default="/home/arespi/omni-arm-link")
    parser.add_argument("--ssh-option", action="append", default=[], help="SSH option, e.g. ControlPath=/tmp/socket")
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--dir", type=Path, help="capture/report directory")
    parser.add_argument("--node", choices=("controller", "robot"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.duration < 3:
        parser.error("duration must be at least 3 seconds")
    if args.node:
        capture_node(args.node, args.duration)
        return
    if not args.robot:
        parser.error("--robot is required")
    directory = args.dir or Path("captures") / time.strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=False)
    local = [sys.executable, str(Path(__file__).resolve()), "--node", "controller", "--duration", str(args.duration)]
    remote = ["ssh"]
    for option in args.ssh_option:
        remote += ["-o", option]
    remote += [args.robot, shlex.join(["python3", args.robot_repo + "/scripts/capture_link.py",
                                     "--node", "robot", "--duration", str(args.duration)])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run_capture, command, directory / (role + ".jsonl"))
                for command, role in [(local, "controller"), (remote, "robot")]]
        for job in jobs:
            job.result()
    records = [json.loads(line) for role in ("controller", "robot")
               for line in (directory / (role + ".jsonl")).read_text().splitlines()]
    report, rows = describe(summarize(records))
    (directory / "report.txt").write_text(report)
    (directory / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(report, end="")
    print(f"Saved to {directory}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        sys.exit(str(exc))
