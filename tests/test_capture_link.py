import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("capture_link", Path(__file__).resolve().parents[1] / "scripts/capture_link.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def records():
    out = []
    for stream, sender, receiver, size, received, lost in [
        ("control", "controller", "robot", 64, 5940, 60),
        ("telemetry", "robot", "controller", 368, 5970, 30),
        ("debug", "robot", "controller", 82, 150, 0),
    ]:
        sent = 150 if stream == "debug" else 6000
        for node, kind, counts in [
            (sender, "tx", {"incoming": sent, "incoming_bytes": sent*size,
                            "injected_bytes": sent*(size+28)*2, "dropped": 0, "truncated": 0}),
            (receiver, "rx", {"out": received, "out_bytes": received*size,
                              "lost": lost, "fec_rec": 20}),
        ]:
            for timestamp, factor in [(10, 0), (40, 1)]:
                out.append({"node": node, "message": {"type": kind, "id": stream+" "+kind,
                    "timestamp": timestamp,
                    "packets": {name: [0, 100+factor*value] for name, value in counts.items()}}})
    return out


class CaptureTests(unittest.TestCase):
    def test_rates_and_receiver_loss(self):
        report, rows = capture.describe(capture.summarize(records()))
        control, telemetry, debug = rows
        self.assertEqual(control["tx_fps"], 200)
        self.assertEqual(control["rx_fps"], 198)
        self.assertAlmostEqual(control["tx_kbps"], 102.4)
        self.assertAlmostEqual(control["rx_kbps"], 101.376)
        self.assertAlmostEqual(control["rx_payload_kbps"], 57.024)
        self.assertEqual(control["loss_pct"], 1)
        self.assertAlmostEqual(telemetry["tx_kbps"], 588.8)
        self.assertEqual(telemetry["loss_pct"], .5)
        self.assertEqual(debug["tx_fps"], 5)
        self.assertIn("Extra test streams: idle", report)

    def test_counter_reset_inside_window(self):
        data = records()
        reset = {"node": "controller", "message": {"type": "tx", "id": "control tx",
                 "timestamp": 20, "packets": {"incoming": [0, 0]}}}
        data.insert(1, reset)
        with self.assertRaisesRegex(ValueError, "reset"):
            capture.summarize(data)

    def test_missing_samples_rejected(self):
        with self.assertRaisesRegex(ValueError, "insufficient"):
            capture.summarize(records()[:1])


if __name__ == "__main__":
    unittest.main()
