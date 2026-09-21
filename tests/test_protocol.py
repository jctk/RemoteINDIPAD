import io
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
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

    def test_debug_json_output_is_single_line(self):
        rendered = receiver.format_debug_json({"left_x": 0.5, "button_0": True})
        self.assertNotIn("\n", rendered)
        self.assertIn('"left_x":0.5', rendered)
        self.assertIn('"button_0":true', rendered)

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
        self.assertNotIn("\n", rendered)
        self.assertIn('"left_x":-0.25', rendered)
        self.assertIn('"button_1":false', rendered)

    def test_default_sender_mapping_includes_filterwheel_actions(self):
        self.assertEqual(sender.DEFAULT_ACTION_MAPPING.get("button_11"), "FILTERWHEEL_PREV")
        self.assertEqual(sender.DEFAULT_ACTION_MAPPING.get("button_12"), "FILTERWHEEL_NEXT")
        self.assertIn("FILTERWHEEL_PREV", sender.AVAILABLE_ACTIONS)
        self.assertIn("FILTERWHEEL_NEXT", sender.AVAILABLE_ACTIONS)

    def test_empty_string_mapping_is_preserved(self):
        resolved = sender._resolve_flat_action_mapping({"axis_4": ""})
        self.assertEqual(resolved["axis_4"], "")

    def test_action_mapping_sorts_all_buttons_before_axes(self):
        resolved = sender._resolve_flat_action_mapping({
            "axis_1": "SKYMAP_MOVE",
            "button_16": "",
            "button_13": "",
        })
        keys = list(resolved)
        self.assertLess(keys.index("button_12"), keys.index("button_13"))
        self.assertLess(keys.index("button_16"), keys.index("axis_1"))

    def test_action_mapping_store_omits_redundant_default_entry(self):
        normalized = sender._normalize_action_mapping_store({
            "controllers": [
                {
                    "name": "JC-U3712T",
                    "guid": "abc",
                    "mapping": {"axis_1": "SKYMAP_MOVE", "axis_2": "SKYMAP_MOVE"},
                }
            ]
        }, controller_name="JC-U3712T", controller_guid="abc")
        self.assertNotIn("default", normalized)
        self.assertIn("controllers", normalized)
        self.assertEqual(normalized["controllers"][0]["mapping"]["axis_1"], "SKYMAP_MOVE")

    def test_gamepad_input_rows_follow_detected_axis_count(self):
        class FakeJoy:
            def get_name(self):
                return "TestPad"

            def get_numaxes(self):
                return 2

            def get_numbuttons(self):
                return 16

            def init(self):
                return None

        class FakeJoystickModule:
            def get_init(self):
                return True

            def init(self):
                return None

            def get_count(self):
                return 1

            def Joystick(self, index):
                return FakeJoy()

        class FakePygame:
            joystick = FakeJoystickModule()

            @staticmethod
            def get_init():
                return True

            @staticmethod
            def init():
                return None

        original_pygame = sender.pygame
        try:
            sender.pygame = FakePygame()
            rows = sender.get_gamepad_input_rows("TestPad")
        finally:
            sender.pygame = original_pygame

        axis_labels = [label for label, key in rows if key.startswith("axis_")]
        button_labels = [label for label, key in rows if key.startswith("button_")]
        self.assertEqual(axis_labels, ["Axis 1", "Axis 2"])
        self.assertEqual(button_labels, [f"Button {index}" for index in range(1, 17)])

    def test_apply_mapping_preserves_other_controller_entries(self):
        window = sender.IndipadWindow.__new__(sender.IndipadWindow)
        window.gui_settings = {
            "controller": "JC-U3712T",
            "controller_guid": "0300b561790000000600000000000000",
            "host": "localhost",
            "port": 50007,
            "heartbeat": False,
            "focus_step": 500,
            "action_mapping": {
                "default": {
                    "axis_1": "SKYMAP_MOVE",
                    "axis_2": "SKYMAP_MOVE",
                    "axis_3": "SKYMAP_ROTATE",
                    "axis_4": "SKYMAP_ZOOM",
                    "axis_5": "",
                    "axis_6": "",
                },
                "controllers": [
                    {"name": "JC-U3712T", "guid": "0300b561790000000600000000000000", "mapping": {"axis_1": "SKYMAP_MOVE", "axis_2": "SKYMAP_MOVE", "axis_3": "SKYMAP_ROTATE", "axis_4": "SKYMAP_ZOOM", "axis_5": "", "axis_6": ""}},
                    {"name": "Xbox One S Controller", "guid": "030082795e040000e002000000007200", "mapping": {"axis_1": "SKYMAP_MOVE", "axis_2": "SKYMAP_MOVE", "axis_3": "SKYMAP_ROTATE", "axis_4": "SKYMAP_ZOOM", "axis_5": "", "axis_6": ""}},
                ],
            },
        }
        class FakeCombo:
            def currentText(self):
                return "JC-U3712T"
        window.controller_combo = FakeCombo()
        window.save_settings = lambda: None

        window._apply_mapping({"axis_1": "SKYMAP_MOVE", "axis_2": "SKYMAP_MOVE", "axis_3": "SKYMAP_ROTATE", "axis_4": "", "axis_5": "SKYMAP_ZOOM", "axis_6": ""})

        self.assertEqual(len(window.gui_settings["action_mapping"]["controllers"]), 2)
        self.assertEqual(window.gui_settings["action_mapping"]["controllers"][0]["mapping"]["axis_4"], "")

    def test_controller_change_reconnects_an_active_worker(self):
        class FakeWorker:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        class FakeCombo:
            def currentText(self):
                return "Xbox One S Controller"

        window = sender.IndipadWindow.__new__(sender.IndipadWindow)
        active_worker = FakeWorker()
        window.worker = active_worker
        window.controller_combo = FakeCombo()
        messages = []
        window.log = messages.append
        reconnected = []
        window.on_connect = lambda: reconnected.append(True)

        window._on_controller_changed(1)

        self.assertTrue(active_worker.stopped)
        self.assertIsNone(window.worker)
        self.assertEqual(reconnected, [True])
        self.assertIn("switching controller to Xbox One S Controller", messages[0])

    def test_stale_worker_disconnect_does_not_clear_current_worker(self):
        window = sender.IndipadWindow.__new__(sender.IndipadWindow)
        old_worker = object()
        current_worker = object()
        window.worker = current_worker
        states = []
        window.set_connection_button_state = states.append

        window._handle_connection_update("Disconnected", old_worker)

        self.assertIs(window.worker, current_worker)
        self.assertEqual(states, [])

    def test_mapping_editor_save_keeps_window_open(self):
        window = sender.MappingEditorWindow.__new__(sender.MappingEditorWindow)
        window.input_rows = {
            "axis_1": type("FakeCombo", (), {"currentText": lambda self: "SKYMAP_MOVE"})(),
            "button_1": type("FakeCombo", (), {"currentText": lambda self: "Unassigned"})(),
        }
        window.mapping = {}
        emitted = {}

        class FakeSignal:
            def emit(self, value):
                emitted["mapping"] = value

        window.mapping_applied = FakeSignal()
        window.closed = False
        window.close = lambda: setattr(window, "closed", True)

        window.apply_mapping()

        self.assertFalse(window.closed)
        self.assertEqual(emitted["mapping"]["axis_1"], "SKYMAP_MOVE")

    def test_gui_settings_round_trip_includes_focus_step(self):
        settings = {
            "controller": "JC-U3712T",
            "host": "localhost",
            "port": 50007,
            "heartbeat": False,
            "focus_step": 250,
            "deadzone": 0.6,
            "action_mapping": {"button_1": "FOCUS_STEP_UP"},
        }
        path = Path("test_sender_gui_settings.json")
        try:
            sender.save_gui_settings(settings, path)
            loaded = sender.load_gui_settings(path)
            self.assertEqual(loaded["focus_step"], 250)
            self.assertEqual(loaded["deadzone"], 0.6)
        finally:
            if path.exists():
                path.unlink()

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

    def test_filter_slot_count_stops_at_first_invalid_slot(self):
        responses = [("R",), ("G",), ("Invalid",)]

        async def wrapped_call(method_name, *args):
            index = wrapped_call.calls
            wrapped_call.calls += 1
            if index >= len(responses):
                index = len(responses) - 1
            return responses[index]

        wrapped_call.calls = 0

        with patch("remote_indipad_receiver._call_indi_method", side_effect=wrapped_call):
            self.assertEqual(receiver.get_filter_slot_count("Filter Simulator"), 2)

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

    def test_axis_normalizes_deadzone_and_initial_state(self):
        self.assertEqual(sender.normalize_axis_value(-0.2, 0.1), -1)
        self.assertEqual(sender.normalize_axis_value(-0.09, 0.1), 0)
        self.assertEqual(sender.normalize_axis_value(0.0, 0.1), 0)
        self.assertEqual(sender.normalize_axis_value(0.12, 0.1), 1)

        mapping = {
            "axis_1": {
                "NEGATIVE": "SKYMAP_ZOOM_OUT",
                "CENTER": "",
                "POSITIVE": "SKYMAP_ZOOM_IN",
            }
        }
        events = sender.build_action_events(
            axes={"axis_1": -0.2},
            previous_axes={},
            action_map=mapping,
        )
        self.assertIn({"action": "SKYMAP_ZOOM_OUT", "pressed": True, "source": "axis"}, events)

        moved = sender.build_action_events(
            axes={"axis_1": 0.0},
            previous_axes={"axis_1": -0.2},
            action_map=mapping,
        )
        self.assertIn({"action": "SKYMAP_ZOOM_OUT", "pressed": False, "source": "axis"}, moved)
        self.assertNotIn({"action": "", "pressed": True, "source": "axis"}, moved)

    def test_state_signature_suppresses_idle_updates(self):
        idle_a = sender.state_signature({"left_x": 0.0, "left_y": 0.0}, {"button_1": False})
        idle_b = sender.state_signature({"left_x": 0.0, "left_y": 0.0}, {"button_1": False})
        changed = sender.state_signature({"left_x": 0.1, "left_y": 0.0}, {"button_1": False})
        self.assertEqual(idle_a, idle_b)
        self.assertNotEqual(idle_a, changed)

    def test_gamepad_pov_is_exposed_as_dpad_buttons(self):
        class FakeJoy:
            def __init__(self):
                self._hat = (1, 0)

            def get_numaxes(self):
                return 4

            def get_axis(self, index):
                values = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}
                return values.get(index, 0.0)

            def get_hat(self, index):
                return self._hat

            def get_numbuttons(self):
                return 0

        axes, buttons, dpad = sender.read_gamepad_state(FakeJoy())
        self.assertEqual(axes["axis_1"], 0.0)
        self.assertTrue(dpad["dpad_right"])
        self.assertFalse(dpad.get("dpad_left", False))
        self.assertNotIn("dpad_right", buttons)

    def test_gamepad_pov_y_direction_matches_pygame_convention(self):
        class FakeJoy:
            def __init__(self, hat):
                self._hat = hat

            def get_numaxes(self):
                return 0

            def get_numbuttons(self):
                return 0

            def get_hat(self, index):
                return self._hat

        _, _, up_dpad = sender.read_gamepad_state(FakeJoy((0, 1)))
        _, _, down_dpad = sender.read_gamepad_state(FakeJoy((0, -1)))
        self.assertTrue(up_dpad["dpad_up"])
        self.assertFalse(up_dpad["dpad_down"])
        self.assertFalse(down_dpad["dpad_up"])
        self.assertTrue(down_dpad["dpad_down"])

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

    def test_rotator_target_angle_clamps_to_fixed_360_range(self):
        self.assertEqual(receiver.normalize_rotator_target_angle(45.0, -50.0, 180.0), 0.0)
        self.assertEqual(receiver.normalize_rotator_target_angle(45.0, 200.0, 180.0), 245.0)
        self.assertEqual(receiver.normalize_rotator_target_angle(300.0, 120.0, 0), 360.0)
        self.assertEqual(receiver.normalize_rotator_target_angle(300.0, -120.0, 0), 180.0)

    def test_rotator_action_ignores_busy_property(self):
        class FakeInterface:
            async def call_get_property_state(self, *args):
                return "busy"

        class FakeProxy:
            def get_interface(self, name):
                return FakeInterface()

        class FakeBus:
            def __init__(self, *args, **kwargs):
                pass

            async def connect(self):
                pass

            async def introspect(self, *args):
                return object()

            def get_proxy_object(self, *args):
                return FakeProxy()

            def disconnect(self):
                pass

        with patch("remote_indipad_receiver.MessageBus", FakeBus):
            fake_bus_type = type("FakeBusType", (), {"SESSION": "session"})
            with patch("remote_indipad_receiver.BusType", fake_bus_type):
                with patch("remote_indipad_receiver.get_active_indi_device", return_value="Rotator Simulator"):
                    result = receiver.execute_rotator_action("CAA_ROTATE_CLOCKWISE", 45, driver_name="Rotator Simulator")
        self.assertIsNone(result)

    def test_rotator_hold_loop_repeats_until_stop_event(self):
        calls = []
        stop_event = threading.Event()

        def fake_execute(direction, angle=None, driver_name=None):
            calls.append((direction, angle, driver_name))
            if len(calls) >= 3:
                stop_event.set()
            return 1.0

        receiver._run_rotator_hold_loop(
            "CAA_ROTATE_CLOCKWISE",
            "Rotator Simulator",
            stop_event=stop_event,
            interval=0.0,
            executor=fake_execute,
        )

        self.assertGreaterEqual(len(calls), 3)
        self.assertTrue(all(direction == "CAA_ROTATE_CLOCKWISE" for direction, _, _ in calls))
        self.assertTrue(all(angle == 1 for _, angle, _ in calls))

    def test_stop_rotator_hold_clears_active_event(self):
        stop_event = threading.Event()
        receiver._ROTATOR_HOLD_EVENTS["CAA_ROTATE_COUNTER_CLOCKWISE"] = stop_event

        receiver.stop_rotator_hold("CAA_ROTATE_COUNTER_CLOCKWISE")

        self.assertTrue(stop_event.is_set())
        self.assertNotIn("CAA_ROTATE_COUNTER_CLOCKWISE", receiver._ROTATOR_HOLD_EVENTS)

    def test_queue_log_handler_buffers_messages_thread_safely(self):
        handler = receiver.QueueLogHandler()
        handler.emit("[receiver] start")
        handler.emit("[receiver] action")

        self.assertEqual(handler.drain(), ["[receiver] start", "[receiver] action"])
        self.assertEqual(handler.drain(), [])

    def test_build_focus_dbus_calls_uses_selected_driver_name(self):
        calls = receiver.build_focus_dbus_calls("GEMINI EAF GS150RC", "FOCUS_IN")
        self.assertEqual(calls[0], ("setSwitch", ("GEMINI EAF GS150RC", "FOCUS_MOTION", "FOCUS_INWARD", "On")))
        self.assertEqual(calls[1], ("sendProperty", ("GEMINI EAF GS150RC", "FOCUS_MOTION")))
        self.assertEqual(calls[2][0], "setNumber")
        self.assertEqual(calls[3], ("sendProperty", ("GEMINI EAF GS150RC", "REL_FOCUS_POSITION")))

    def test_indi_method_uses_dbus_next_proxy_method_names(self):
        calls = []

        class FakeInterface:
            async def call_set_switch(self, *args):
                calls.append(("set_switch", args))
                return None

        class FakeProxy:
            def get_interface(self, name):
                self.interface_name = name
                return FakeInterface()

        class FakeBus:
            def __init__(self, *args, **kwargs):
                pass

            async def connect(self):
                pass

            async def introspect(self, *args):
                return object()

            def get_proxy_object(self, *args):
                return FakeProxy()

            def disconnect(self):
                pass

        with patch("remote_indipad_receiver.MessageBus", FakeBus):
            fake_bus_type = type("FakeBusType", (), {"SESSION": "session"})
            with patch("remote_indipad_receiver.BusType", fake_bus_type):
                import asyncio
                asyncio.run(receiver._call_indi_method("setSwitch", "Device", "FOCUS_MOTION", "FOCUS_INWARD", "On"))

        self.assertEqual(calls, [("set_switch", ("Device", "FOCUS_MOTION", "FOCUS_INWARD", "On"))])

    def test_focus_step_uses_step_from_protocol(self):
        calls = receiver.build_focus_dbus_calls("GEMINI EAF GS150RC", "FOCUS_IN", step=250)
        self.assertIn(250, calls[2][1])
        self.assertAlmostEqual(float(calls[2][1][-1]), 250.0)

    def test_abstract_axis_names_are_used_instead_of_left_right_sticks(self):
        class FakeJoy:
            def get_numaxes(self):
                return 4

            def get_axis(self, index):
                values = {0: 0.2, 1: -0.8, 2: 0.6, 3: -0.3}
                return values.get(index, 0.0)

            def get_numbuttons(self):
                return 0

        axes, buttons, dpad = sender.read_gamepad_state(FakeJoy())
        self.assertEqual(sorted(axes), ["axis_1", "axis_2", "axis_3", "axis_4"])
        self.assertAlmostEqual(axes["axis_1"], 0.2)
        self.assertAlmostEqual(axes["axis_2"], -0.8)
        self.assertAlmostEqual(axes["axis_3"], 0.6)
        self.assertAlmostEqual(axes["axis_4"], -0.3)
        self.assertEqual(buttons, {})
        self.assertEqual(dpad, {})

    def test_resolve_gamepad_selection_by_name_or_index(self):
        names = ["DualSense Wireless Controller", "Xbox Controller"]
        self.assertEqual(sender.resolve_gamepad_selection(names, "xbox"), 1)
        self.assertEqual(sender.resolve_gamepad_selection(names, "1"), 0)

    def test_build_gamepad_monitor_snapshot_reports_pressed_state(self):
        snapshot = sender.build_gamepad_monitor_snapshot(
            device_name="JC-U3712T",
            guid="0300...",
            axes={"axis_1": 1.0, "axis_2": -0.5, "axis_3": 0.0, "axis_4": 0.125},
            buttons={"button_1": True, "button_2": False, "button_5": True},
            dpad={"dpad_up": True, "dpad_down": False, "dpad_left": False, "dpad_right": True},
            axis_count=6,
            button_count=16,
            hat_count=1,
        )
        self.assertEqual(snapshot["device_name"], "JC-U3712T")
        self.assertEqual(snapshot["axis_count"], 6)
        self.assertEqual(snapshot["button_count"], 16)
        self.assertEqual(snapshot["axes"]["axis_1"], 1.0)
        self.assertTrue(snapshot["buttons"]["button_1"])
        self.assertTrue(snapshot["dpad"]["dpad_up"])
        self.assertTrue(snapshot["dpad"]["dpad_right"])

    def test_build_action_payload_uses_abstract_gamepad_actions(self):
        payload = protocol.build_action_payload(action="MOUNT_NORTH", pressed=True, source="dpad")
        self.assertEqual(payload["type"], "action")
        self.assertEqual(payload["action"], "MOUNT_NORTH")
        self.assertTrue(payload["pressed"])
        self.assertEqual(payload["source"], "dpad")

    def test_focus_actions_include_current_step_and_step_buttons_stay_local(self):
        focus_events = sender.build_action_events(
            {},
            {"button_1": True, "button_6": True},
            {},
            {},
            action_map={"button_1": "FOCUS_STEP_UP", "button_6": "FOCUS_IN"},
            focus_step=250,
        )
        self.assertNotIn({"action": "FOCUS_STEP_UP", "pressed": True, "source": "button"}, focus_events)
        self.assertIn({"action": "FOCUS_IN", "pressed": True, "source": "button", "step": 250}, focus_events)

        payload = protocol.build_action_payload(action="FOCUS_IN", pressed=True, source="button", step=250)
        self.assertEqual(payload["step"], 250)

    def test_axis_focus_step_actions_update_step_on_state_transitions(self):
        focus_step_state = {"value": 50}
        mapping = {
            "axis_2": {
                "NEGATIVE": "FOCUS_STEP_UP",
                "CENTER": "",
                "POSITIVE": "FOCUS_STEP_DOWN",
            }
        }

        events = sender.build_action_events(
            axes={"axis_2": -1.0},
            previous_axes={"axis_2": 0.0},
            action_map=mapping,
            focus_step=focus_step_state["value"],
            focus_step_state=focus_step_state,
        )
        self.assertEqual(events, [])
        self.assertEqual(focus_step_state["value"], 100)

        events = sender.build_action_events(
            axes={"axis_2": 1.0},
            previous_axes={"axis_2": -1.0},
            action_map=mapping,
            focus_step=focus_step_state["value"],
            focus_step_state=focus_step_state,
        )
        self.assertEqual(events, [])
        self.assertEqual(focus_step_state["value"], 50)

    def test_validate_message_accepts_action_payload(self):
        payload = {
            "ts": 1.0,
            "type": "action",
            "device": "gamepad",
            "action": "MOUNT_STOP",
            "pressed": False,
            "source": "dpad",
        }
        self.assertTrue(protocol.validate_message(payload))

    def test_validate_message_accepts_rotation_angle_payload(self):
        payload = {
            "ts": 1.0,
            "type": "action",
            "device": "gamepad",
            "action": "CAA_ROTATE_CLOCKWISE",
            "pressed": False,
            "source": "button",
            "angle": 5,
        }
        self.assertTrue(protocol.validate_message(payload))
        payload["angle"] = -5
        self.assertTrue(protocol.validate_message(payload))

    def test_rotation_actions_use_same_action_with_pressed_flag(self):
        events = sender.build_action_events(
            {},
            {"button_3": True, "button_4": False},
            {},
            {},
            action_map={"button_3": "CAA_ROTATE_COUNTER_CLOCKWISE", "button_4": "CAA_ROTATE_CLOCKWISE"},
        )
        self.assertIn({"action": "CAA_ROTATE_COUNTER_CLOCKWISE", "pressed": True, "source": "button"}, events)
        self.assertNotIn({"action": "CAA_ROTATE_ABORT", "pressed": False, "source": "button"}, events)

        release = sender.build_action_events(
            {},
            {"button_3": False, "button_4": False},
            {},
            {"button_3": True, "button_4": False},
            action_map={"button_3": "CAA_ROTATE_COUNTER_CLOCKWISE", "button_4": "CAA_ROTATE_CLOCKWISE"},
        )
        self.assertIn({"action": "CAA_ROTATE_COUNTER_CLOCKWISE", "pressed": False, "source": "button"}, release)
        self.assertNotIn({"action": "CAA_ROTATE_ABORT", "pressed": False, "source": "button"}, release)

    def test_rotation_button_press_times_are_trackable_but_not_emitted_as_abort(self):
        press_times = {}
        first = sender.build_action_events(
            {},
            {"button_4": True},
            {},
            {},
            action_map={"button_4": "CAA_ROTATE_CLOCKWISE"},
            button_press_times=press_times,
            now=10.0,
        )
        self.assertEqual(first, [{"action": "CAA_ROTATE_CLOCKWISE", "pressed": True, "source": "button"}])
        self.assertIn("button_4", press_times)
        self.assertEqual(press_times["button_4"], 10.0)

        release = sender.build_action_events(
            {},
            {"button_4": False},
            {},
            {"button_4": True},
            action_map={"button_4": "CAA_ROTATE_CLOCKWISE"},
            button_press_times=press_times,
            now=10.7,
        )
        self.assertIn({"action": "CAA_ROTATE_CLOCKWISE", "pressed": False, "source": "button"}, release)
        self.assertNotIn({"action": "CAA_ROTATE_ABORT", "pressed": False, "source": "button"}, release)

    def test_rotator_hold_uses_1_degree_then_5_degree_then_10_degree_steps(self):
        stop_event = threading.Event()
        calls = []

        def fake_executor(direction, angle, driver_name=None):
            calls.append(float(angle))
            if len(calls) >= 9:
                stop_event.set()

        with patch.object(receiver, "read_rotator_state", return_value="ok"), patch.object(receiver, "stop_rotator_hold"):
            receiver._run_rotator_hold_loop("CAA_ROTATE_CLOCKWISE", "rotator_driver", stop_event, interval=0, executor=fake_executor)

        self.assertEqual(calls, [1.0, 1.0, 1.0, 1.0, 1.0, 5.0, 5.0, 5.0, 10.0])

    def test_release_rotator_stop_stops_loop_and_aborts_motion(self):
        calls = []

        def fake_stop_rotator_hold(direction=None):
            calls.append(("stop", direction))

        def fake_abort(driver_name=None):
            calls.append(("abort", driver_name))

        with patch.object(receiver, "stop_rotator_hold", side_effect=fake_stop_rotator_hold), \
             patch.object(receiver, "execute_rotator_abort", side_effect=fake_abort), \
             patch.object(receiver, "get_active_indi_device", return_value="Rotator Simulator"):
            receiver.handle_caa_rotate_clockwise(False)

        self.assertIn(("stop", "CAA_ROTATE_CLOCKWISE"), calls)
        self.assertIn(("abort", "Rotator Simulator"), calls)

    def test_sender_disconnect_event_resets_button_state(self):
        class FakeButton:
            def __init__(self):
                self.text = "Disconnect"
                self.stylesheet = ""

            def setText(self, text):
                self.text = text

            def setStyleSheet(self, stylesheet):
                self.stylesheet = stylesheet

        window = sender.IndipadWindow.__new__(sender.IndipadWindow)
        window.connection_button = FakeButton()
        window.worker = object()

        window._handle_connection_update("Disconnected")
        self.assertEqual(window.connection_button.text, "Connect")
        self.assertIsNone(window.worker)

        window.worker = object()
        window._handle_connection_update("Connected: Test Controller")
        self.assertEqual(window.connection_button.text, "Disconnect")

    def test_receiver_gui_settings_have_expected_defaults(self):
        defaults = receiver.load_gui_settings(path=Path("/tmp/does-not-exist.json"))
        self.assertIn("mount", defaults)
        self.assertIn("focuser", defaults)
        self.assertIn("rotator", defaults)
        self.assertIn("host", defaults)
        self.assertIn("port", defaults)
        self.assertIn("heartbeat", defaults)
        self.assertEqual(defaults["host"], "0.0.0.0")
        self.assertEqual(defaults["port"], 50007)
        self.assertFalse(defaults["heartbeat"])

    def test_dpad_to_abstract_action_mapping(self):
        mapping = sender.build_action_events({"dpad_up": False, "dpad_left": False, "dpad_right": False, "dpad_down": True}, {})
        self.assertIn({"action": "MOUNT_SOUTH", "pressed": True, "source": "dpad"}, mapping)

        mapping = sender.build_action_events(
            {"dpad_up": False, "dpad_left": False, "dpad_right": False, "dpad_down": False},
            {},
            previous_dpad={"dpad_down": True},
        )
        self.assertIn({"action": "MOUNT_SOUTH", "pressed": False, "source": "dpad"}, mapping)
        self.assertNotIn({"action": "MOUNT_STOP", "pressed": False, "source": "dpad"}, mapping)

    def test_dpad_stop_is_emitted_only_after_all_directions_are_released(self):
        mapping = sender.build_action_events(
            {"dpad_up": False, "dpad_left": True, "dpad_right": False, "dpad_down": False},
            {},
            previous_dpad={"dpad_up": True, "dpad_left": False, "dpad_right": False, "dpad_down": False},
        )
        self.assertNotIn({"action": "MOUNT_STOP", "pressed": False, "source": "dpad"}, mapping)
        self.assertIn({"action": "MOUNT_NORTH", "pressed": False, "source": "dpad"}, mapping)
        self.assertIn({"action": "MOUNT_WEST", "pressed": True, "source": "dpad"}, mapping)

        mapping = sender.build_action_events(
            {"dpad_up": False, "dpad_left": False, "dpad_right": False, "dpad_down": False},
            {},
            previous_dpad={"dpad_up": False, "dpad_left": True, "dpad_right": False, "dpad_down": False},
        )
        self.assertIn({"action": "MOUNT_WEST", "pressed": False, "source": "dpad"}, mapping)
        self.assertNotIn({"action": "MOUNT_STOP", "pressed": False, "source": "dpad"}, mapping)

    def test_policy_button_mapping_matches_documented_gamepad_layout(self):
        mapping = sender.build_action_events(
            {},
            {
                "button_5": True,
                "button_6": True,
                "button_7": True,
                "button_8": True,
                "button_9": True,
                "button_10": True,
                "button_1": True,
                "button_2": True,
                "button_3": True,
                "button_4": True,
            },
        )

        expected_actions = {
            "MOUNT_STEP_UP",
            "FOCUS_IN",
            "MOUNT_STEP_DOWN",
            "FOCUS_OUT",
            "MOUNT_STOP",
            "FOCUS_STOP",
        }
        self.assertTrue(expected_actions.issubset({event["action"] for event in mapping}))
        self.assertNotIn("FOCUS_STEP_UP", {event["action"] for event in mapping})
        self.assertNotIn("FOCUS_STEP_DOWN", {event["action"] for event in mapping})
        self.assertIn("CAA_ROTATE_COUNTER_CLOCKWISE", {event["action"] for event in mapping})
        self.assertIn("CAA_ROTATE_CLOCKWISE", {event["action"] for event in mapping})

    def test_action_mapping_can_be_defined_in_gui_settings(self):
        settings = {
            "controller": "JC-U3712T",
            "host": "localhost",
            "port": 50007,
            "heartbeat": False,
            "action_mapping": {
                "dpad_down": "CUSTOM_NORTH",
                "button_6": "CUSTOM_FOCUS_IN",
            },
        }

        resolved = sender.resolve_action_mapping(settings)
        self.assertEqual(resolved["dpad_down"], "CUSTOM_NORTH")
        self.assertEqual(resolved["button_6"], "CUSTOM_FOCUS_IN")
        self.assertEqual(resolved["dpad_up"], "MOUNT_NORTH")

        mapping = sender.build_action_events({"dpad_down": True}, {}, action_map=resolved)
        self.assertIn({"action": "CUSTOM_NORTH", "pressed": True, "source": "dpad"}, mapping)

    def test_action_mapping_uses_guid_and_name_to_select_controller_profile(self):
        settings = {
            "controller": "JC-U3712T",
            "controller_guid": "guid-1",
            "action_mapping": {
                "default": {"dpad_down": "MOUNT_NORTH", "button_1": "FOCUS_STEP_UP"},
                "controllers": [
                    {"name": "JC-U3712T", "guid": "guid-1", "mapping": {"dpad_down": "CUSTOM_NORTH", "button_1": "CUSTOM_FOCUS_UP"}},
                    {"name": "Xbox Controller", "guid": "guid-2", "mapping": {"dpad_down": "MOUNT_EAST", "button_1": "FOCUS_IN"}},
                ],
            },
        }

        resolved = sender.resolve_action_mapping(settings, device_name="JC-U3712T", device_guid="guid-1")
        self.assertEqual(resolved["dpad_down"], "CUSTOM_NORTH")
        self.assertEqual(resolved["button_1"], "CUSTOM_FOCUS_UP")

        default_for_other = sender.resolve_action_mapping(settings, device_name="Xbox Controller", device_guid="guid-2")
        self.assertEqual(default_for_other["dpad_down"], "MOUNT_EAST")
        self.assertEqual(default_for_other["button_1"], "FOCUS_IN")

    def test_sender_worker_resolves_selected_controller_mapping(self):
        worker = sender.SenderWorker(
            host="localhost",
            port=50007,
            device_name="JC-U3712T",
            controller_guid="guid-1",
            action_map={
                "controllers": [
                    {
                        "name": "JC-U3712T",
                        "guid": "guid-1",
                        "mapping": {"dpad_up": "MOUNT_NORTH", "dpad_down": "MOUNT_SOUTH"},
                    }
                ]
            },
        )
        self.assertEqual(worker.action_map["dpad_up"], "MOUNT_NORTH")
        self.assertEqual(worker.action_map["dpad_down"], "MOUNT_SOUTH")

    def test_default_mapping_uses_gamepad_profile_value(self):
        config = sender.load_axis_config(Path("D:/Projects/RemoteINDIPAD/gamepad_profiles.json"))
        default_mapping = sender.get_default_action_mapping("JC-U3712T", config)
        self.assertEqual(default_mapping["dpad_down"], "MOUNT_SOUTH")
        self.assertEqual(default_mapping["button_6"], "FOCUS_OUT")

    def test_idle_state_does_not_emit_action_events(self):
        mapping = sender.build_action_events(
            {"dpad_up": False, "dpad_left": False, "dpad_right": False, "dpad_down": False},
            {"button_1": False, "button_2": False, "button_3": False, "button_4": False},
        )
        self.assertEqual(mapping, [])

    def test_load_axis_config_falls_back_when___file___is_missing(self):
        original = sender.__dict__.get("__file__")
        sender.__dict__.pop("__file__", None)
        try:
            config = sender.load_axis_config()
            self.assertIn("profiles", config)
            self.assertIn("default", config["profiles"])
        finally:
            if original is not None:
                sender.__dict__["__file__"] = original

    def test_resolve_gamepad_selection_by_index_and_name(self):
        names = ["DualSense Wireless Controller", "Xbox Controller"]
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

    def test_receiver_dispatches_abstract_actions_as_debug_entries(self):
        with patch("builtins.print") as mocked_print:
            receiver.dispatch_abstract_action("MOUNT_NORTH", True, "dpad")
            receiver.dispatch_abstract_action("MOUNT_STOP", False, "dpad")
            receiver.dispatch_abstract_action("SKYMAP_MOVE", True, "left_stick")

        printed = "\n".join(call.args[0] for call in mocked_print.call_args_list if call.args)
        self.assertIn("MOUNT_NORTH", printed)
        self.assertIn("MOUNT_STOP", printed)
        self.assertIn("SKYMAP_MOVE", printed)

    def test_mount_actions_toggle_indi_switches_and_abort(self):
        receiver.set_active_indi_device("mount", "INDI_MOUNT")

        mock_calls = unittest.mock.AsyncMock(return_value=[True])
        with patch("remote_indipad_receiver._run_indi_calls", mock_calls):
            receiver.handle_mount_north(True, "dpad")
            receiver.handle_mount_south(False, "dpad")
            receiver.handle_mount_west(True, "dpad")
            receiver.handle_mount_east(False, "dpad")
            receiver.handle_mount_stop(True, "dpad")

        self.assertEqual(mock_calls.call_count, 5)
        calls = [call.args[0] for call in mock_calls.call_args_list]
        self.assertEqual(calls[0][0][0], "setSwitch")
        self.assertEqual(calls[0][0][1][0], "INDI_MOUNT")
        self.assertEqual(calls[0][0][1][1], "TELESCOPE_MOTION_NS")
        self.assertEqual(calls[0][0][1][2], "MOTION_NORTH")
        self.assertEqual(calls[0][0][1][3], "On")
        self.assertEqual(calls[1][0][1][2], "MOTION_SOUTH")
        self.assertEqual(calls[1][0][1][3], "Off")
        self.assertEqual(calls[2][0][1][1], "TELESCOPE_MOTION_WE")
        self.assertEqual(calls[2][0][1][2], "MOTION_WEST")
        self.assertEqual(calls[3][0][1][2], "MOTION_EAST")
        self.assertEqual(calls[3][0][1][3], "Off")
        self.assertEqual(calls[4][0][1][1], "TELESCOPE_ABORT_MOTION")
        self.assertEqual(calls[4][0][1][2], "ABORT")
        self.assertEqual(calls[4][0][1][3], "On")

    def test_mount_step_actions_cycle_slew_rates(self):
        receiver.set_active_indi_device("mount", "INDI_MOUNT")

        with patch.object(receiver, "get_mount_slew_rates", return_value=["1x", "2x", "3x", "4x"]), \
             patch.object(receiver, "get_current_mount_slew_rate", return_value="2x"), \
             patch.object(receiver, "set_mount_slew_rate") as mock_set:
            receiver.handle_mount_step_up(True, "button")
            receiver.handle_mount_step_down(True, "button")

        self.assertEqual(mock_set.call_count, 2)
        self.assertEqual(mock_set.call_args_list[0].args[0], "INDI_MOUNT")
        self.assertEqual(mock_set.call_args_list[0].args[1], "3x")
        self.assertEqual(mock_set.call_args_list[1].args[0], "INDI_MOUNT")
        self.assertEqual(mock_set.call_args_list[1].args[1], "1x")


if __name__ == "__main__":
    unittest.main()
