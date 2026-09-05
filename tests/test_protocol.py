import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import remote_indipad_protocol as protocol
import remote_indipad_receiver as receiver
import remote_indipad_sender as sender


class ProtocolTests(unittest.TestCase):
    def test_build_payload_has_expected_fields(self):
        payload = protocol.build_payload(
            axes={"left_x": 0.25, "left_y": -0.5},
            buttons={"button_0": True, "button_1": False},
            dpad={"dpad_right": True, "dpad_left": False},
            mode="slew",
        )
        self.assertIn("ts", payload)
        self.assertEqual(payload["type"], "axis")
        self.assertEqual(payload["device"], "gamepad")
        self.assertEqual(payload["mode"], "slew")
        self.assertAlmostEqual(payload["axes"]["left_x"], 0.25)
        self.assertTrue(payload["dpad"]["dpad_right"])
        self.assertEqual(payload["buttons"]["button_0"], True)
        self.assertEqual(list(payload.keys())[3:6], ["axes", "dpad", "buttons"])

    def test_round_trip_serialization(self):
        original = protocol.build_payload(
            axes={"left_x": 0.0, "left_y": 1.0},
            buttons={"button_5": True},
            dpad={"dpad_up": False, "dpad_right": True},
            mode="track",
        )
        serialized = protocol.serialize_message(original)
        recovered = protocol.parse_message(serialized)
        self.assertEqual(recovered["mode"], "track")
        self.assertTrue(recovered["dpad"]["dpad_right"])
        self.assertEqual(recovered["buttons"]["button_5"], True)

    def test_validate_message_rejects_missing_axes(self):
        invalid = {"ts": 1.0, "type": "axis", "device": "gamepad", "dpad": {}, "buttons": {}, "mode": "slew"}
        self.assertFalse(protocol.validate_message(invalid))

    def test_build_heartbeat_payload_has_expected_fields(self):
        payload = protocol.build_heartbeat_payload()
        self.assertIn("ts", payload)
        self.assertEqual(payload["type"], "heartbeat")
        self.assertEqual(payload["device"], "gamepad")
        self.assertEqual(payload["status"], "alive")

    def test_validate_message_accepts_heartbeat_payload(self):
        heartbeat = {"ts": 1.0, "type": "heartbeat", "device": "gamepad", "status": "alive"}
        self.assertTrue(protocol.validate_message(heartbeat))

    def test_heartbeat_timeout_is_detected_only_after_threshold(self):
        now = 100.0
        self.assertFalse(receiver.Receiver.heartbeat_is_lost(now - 4.9, 5.0, now))
        self.assertTrue(receiver.Receiver.heartbeat_is_lost(now - 5.1, 5.0, now))

    def test_debug_json_output_is_pretty_and_readable(self):
        rendered = receiver.format_debug_json({"left_x": 0.5, "button_0": True})
        self.assertIn("\n", rendered)
        self.assertIn('  "left_x": 0.5', rendered)
        self.assertIn('  "button_0": true', rendered)

    def test_debug_json_keeps_numeric_button_order(self):
        rendered = receiver.format_debug_json({
            "axes": {},
            "dpad": {},
            "buttons": {
                "button_1": False,
                "button_10": False,
                "button_11": False,
                "button_12": False,
                "button_2": False,
                "button_3": False,
                "button_4": False,
                "button_5": False,
                "button_6": False,
                "button_7": False,
                "button_8": False,
                "button_9": False,
            },
        })
        self.assertLess(rendered.index('"button_1"'), rendered.index('"button_2"'))
        self.assertLess(rendered.index('"button_9"'), rendered.index('"button_10"'))
        self.assertLess(rendered.index('"button_10"'), rendered.index('"button_11"'))

    def test_sender_debug_json_output_is_pretty_and_readable(self):
        rendered = sender.format_debug_json({"left_x": -0.25, "button_1": False})
        self.assertIn("\n", rendered)
        self.assertIn('  "left_x": -0.25', rendered)
        self.assertIn('  "button_1": false', rendered)

    def test_debug_json_output_reserves_an_own_update_area(self):
        sender._DEBUG_JSON_CURSOR_SAVED = False
        sender._DEBUG_JSON_LAST_LINES = 0
        stream = io.StringIO()
        with redirect_stdout(stream):
            sender.print_debug_json("[sender] json", {"left_x": 0.5, "button_0": True})
            first_output = stream.getvalue()
            self.assertIn("\x1b[s", first_output)
            self.assertNotIn("A\r", first_output)
            sender.print_debug_json("[sender] json", {"left_x": 0.6, "button_0": False})
            second_output = stream.getvalue()
            self.assertIn("\x1b[u", second_output)
        self.assertTrue(sender._DEBUG_JSON_CURSOR_SAVED)

    def test_gamepad_name_is_exposed_for_startup_status(self):
        class FakeJoy:
            def get_name(self):
                return "DualSense Wireless Controller"

        self.assertEqual(sender.get_gamepad_name(FakeJoy()), "DualSense Wireless Controller")

    def test_clear_console_emits_screen_clear_sequence(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            sender.clear_console()
        output = stream.getvalue()
        self.assertIn("\x1b[2J", output)
        self.assertIn("\x1b[H", output)

    def test_deadzone_zeroes_idle_values(self):
        axes = sender.normalize_axes({"left_x": 0.05, "left_y": -0.03, "right_x": 0.0, "right_y": 0.12})
        self.assertEqual(axes["left_x"], 0.0)
        self.assertEqual(axes["left_y"], 0.0)
        self.assertEqual(axes["right_y"], 0.12)

    def test_state_signature_suppresses_idle_updates(self):
        idle_a = sender.state_signature({"left_x": 0.0, "left_y": 0.0}, {"button_1": False})
        idle_b = sender.state_signature({"left_x": 0.0, "left_y": 0.0}, {"button_1": False})
        changed = sender.state_signature({"left_x": 0.1, "left_y": 0.0}, {"button_1": False})
        self.assertEqual(idle_a, idle_b)
        self.assertNotEqual(idle_a, changed)

    def test_elecom_right_stick_axis_order_is_normalized(self):
        class FakeJoy:
            def __init__(self):
                self._axes = {2: 0.8, 3: 0.0, 4: -0.7}

            def get_axis(self, index):
                return self._axes.get(index, 0.0)

            def get_numaxes(self):
                return 5

            def get_name(self):
                return "ELECOM JC-U3712T"

        right_x, right_y = sender.resolve_right_stick_axes(FakeJoy())
        self.assertAlmostEqual(right_x, 0.8)
        self.assertAlmostEqual(right_y, -0.7)

    def test_elecom_right_stick_keeps_raw_axis_values(self):
        class FakeJoy:
            def get_axis(self, index):
                values = {2: 0.8, 4: 0.05}
                return values.get(index, 0.0)

            def get_numaxes(self):
                return 5

            def get_name(self):
                return "JC-U3712T"

        right_x, right_y = sender.resolve_right_stick_axes(FakeJoy())
        self.assertAlmostEqual(right_x, 0.8)
        self.assertAlmostEqual(right_y, 0.05)

    def test_stick_axis_indices_follow_config_values(self):
        class FakeJoy:
            def get_axis(self, index):
                values = {5: 0.8, 7: -0.4}
                return values.get(index, 0.0)

        axis_config = {"left_x": 0, "left_y": 1, "right_x": 5, "right_y": 7}
        right_x, right_y = sender.resolve_right_stick_axes(FakeJoy(), axis_config)
        self.assertAlmostEqual(right_x, 0.8)
        self.assertAlmostEqual(right_y, -0.4)

    def test_gamepad_pov_is_exposed_as_dpad_buttons(self):
        class FakeJoy:
            def __init__(self):
                self._hat = (1, 0)

            def get_axis(self, index):
                values = {0: 0.0, 1: 0.0, 2: 0.0, 4: 0.0}
                return values.get(index, 0.0)

            def get_hat(self, index):
                return self._hat

            def get_numbuttons(self):
                return 0

        axes, buttons, dpad = sender.read_gamepad_state(FakeJoy())
        self.assertEqual(axes["left_x"], 0.0)
        self.assertTrue(dpad["dpad_right"])
        self.assertFalse(dpad.get("dpad_left", False))
        self.assertNotIn("dpad_right", buttons)

    def test_receiver_extracts_dpad_state_from_payload(self):
        payload = {
            "axes": {"left_x": 0.0, "left_y": 0.0},
            "dpad": {"dpad_up": False, "dpad_right": True},
            "buttons": {"button_1": True},
            "mode": "slew",
        }
        summary = receiver.extract_dpad_state(payload)
        self.assertEqual(summary["pressed"], ["dpad_right"])
        self.assertEqual(summary["all"], ["dpad_up", "dpad_right"])

    def test_device_profile_selection_and_force_override(self):
        config = {
            "default_device": "ELECOM JC-U3712T",
            "profiles": {
                "ELECOM JC-U3712T": {"stick_axes": {"left_x": 0, "left_y": 1, "right_x": 2, "right_y": 4}},
                "DualSense Wireless Controller": {"stick_axes": {"left_x": 0, "left_y": 1, "right_x": 3, "right_y": 5}},
            },
        }

        class FakeJoy:
            def get_name(self):
                return "DualSense Wireless Controller"

        self.assertEqual(
            sender.select_device_profile(FakeJoy(), config),
            config["profiles"]["DualSense Wireless Controller"],
        )
        self.assertEqual(
            sender.select_device_profile(FakeJoy(), config, forced_device="ELECOM JC-U3712T"),
            config["profiles"]["ELECOM JC-U3712T"],
        )

    def test_resolve_gamepad_selection_by_name_or_index(self):
        names = ["DualSense Wireless Controller", "Xbox Controller"]
        self.assertEqual(sender.resolve_gamepad_selection(names, "xbox"), 1)
        self.assertEqual(sender.resolve_gamepad_selection(names, "1"), 0)
        self.assertEqual(sender.resolve_gamepad_selection(names, "2"), 1)
        self.assertEqual(sender.resolve_gamepad_selection(names, "DualSense Wireless Controller"), 0)

    def test_resolve_gamepad_selection_prompts_when_not_specified(self):
        names = ["DualSense Wireless Controller", "Xbox Controller"]
        with patch("builtins.input", return_value="1"):
            self.assertEqual(sender.resolve_gamepad_selection(names, None), 0)

    def test_numeric_input_is_not_treated_as_partial_name_match(self):
        names = ["Xbox One S Controller", "JC-U3712T"]
        self.assertRaises(ValueError, sender.resolve_gamepad_selection, names, "3")
        with patch("builtins.input", side_effect=["3", "2"]):
            self.assertEqual(sender.resolve_gamepad_selection(names, None), 1)


if __name__ == "__main__":
    unittest.main()
