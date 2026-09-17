import sys

import pygame

try:
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - depends on PySide6 being installed
    QApplication = None
    QTimer = None
    QLabel = None
    QPushButton = None
    QVBoxLayout = None
    QWidget = None
    QComboBox = None
    QFormLayout = None
    QHBoxLayout = None


def detect_joysticks():
    if not pygame.get_init():
        pygame.init()
    if not pygame.joystick.get_init():
        pygame.joystick.init()

    count = pygame.joystick.get_count()
    print(f"Number of joysticks: {count}")

    devices = []
    for i in range(count):
        js = pygame.joystick.Joystick(i)
        js.init()
        device = {
            "index": i,
            "name": js.get_name(),
            "instance_id": js.get_instance_id(),
            "guid": js.get_guid(),
            "axes": js.get_numaxes(),
            "buttons": js.get_numbuttons(),
            "hats": js.get_numhats(),
            "trackballs": js.get_numballs(),
        }
        devices.append(device)

        print(f"\n=== GAMEPAD {i} ===")
        print("Joystick system name:", device["name"])
        print("Instance ID:", device["instance_id"])
        print("GUID:", device["guid"])
        print("Number of axes:", device["axes"])
        print("Number of buttons:", device["buttons"])
        print("Number of hat controls:", device["hats"])
        print("Number of trackballs:", device["trackballs"])

    return devices


# Gamepad monitor window class
class GamepadMonitorWindow(QWidget):
    # Initialize the gamepad monitor window with the given devices and joystick index
    def __init__(self, devices, joystick_index: int):
        super().__init__()
        self.devices = devices
        self.joystick_index = joystick_index
        self.joy = pygame.joystick.Joystick(joystick_index)
        self.joy.init()

        # Initialize the gamepad monitor window UI components
        self.setWindowTitle("Gamepad Monitor")
        self.resize(600, 650)

        self.axis_values = {}
        self.button_values = {}
        self.hat_values = {}

        # Create the top-level layout for the window
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(10, 10, 10, 10)
        self.root_layout.setSpacing(10)

        # Create the main layout for the left/right split panel
        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(10)

        # Create the left panel for device selection and attributes
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)

        self.device_combo = QComboBox()
        for device in self.devices:
            self.device_combo.addItem(f"{device['index']}: {device['name']}")
        self.device_combo.setCurrentIndex(self.joystick_index)
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        self.left_layout.addWidget(QLabel("Detected GAMEPADs"))
        self.left_layout.addWidget(self.device_combo)

        self.attribute_form = QWidget()
        self.attribute_layout = QFormLayout(self.attribute_form)
        self.attribute_layout.setContentsMargins(0, 0, 0, 0)
        self.attribute_labels = {
            "name": QLabel(),
            "instance_id": QLabel(),
            "guid": QLabel(),
            "axes": QLabel(),
            "buttons": QLabel(),
            "hats": QLabel(),
            "trackballs": QLabel(),
        }
        for key, label in self.attribute_labels.items():
            self.attribute_layout.addRow(key.replace("_", " ").title() + ":", label)
        self.left_layout.addWidget(self.attribute_form)
        self.left_layout.addStretch()
        self.main_layout.addWidget(self.left_panel, 1)

        # Create the right panel for displaying gamepad input information
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)

        self.if_title = QLabel("IF Operation Information")
        self.if_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.right_layout.addWidget(self.if_title)

        axis_widget = QWidget()
        axis_layout = QVBoxLayout(axis_widget)
        axis_layout.addWidget(QLabel("Axes"))
        for axis_index in range(self.joy.get_numaxes()):
            display_index = axis_index + 1
            label = QLabel(f"Axis {display_index}: 0.000")
            self.axis_values[axis_index] = label
            axis_layout.addWidget(label)
        self.right_layout.addWidget(axis_widget)

        button_widget = QWidget()
        button_layout = QVBoxLayout(button_widget)
        button_layout.addWidget(QLabel("Buttons"))
        for button_index in range(self.joy.get_numbuttons()):
            display_index = button_index + 1
            label = QLabel(f"Button {display_index}: Released")
            self.button_values[button_index] = label
            button_layout.addWidget(label)
        self.right_layout.addWidget(button_widget)

        hat_widget = QWidget()
        hat_layout = QVBoxLayout(hat_widget)
        hat_layout.addWidget(QLabel("Hats"))
        for hat_index in range(self.joy.get_numhats()):
            display_index = hat_index + 1
            label = QLabel(f"Hat {display_index}: (0, 0)")
            self.hat_values[hat_index] = label
            hat_layout.addWidget(label)
        self.right_layout.addWidget(hat_widget)

        # Create the close button and its container for the right panel
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close_window)
        self.close_button.setMinimumWidth(180)
        self.close_button.setMaximumWidth(260)
        self.close_button.setFixedWidth(180)

        self.main_layout.addWidget(self.right_panel, 1)
        self.main_layout.setStretch(0, 1)
        self.main_layout.setStretch(1, 1)

        self.root_layout.addLayout(self.main_layout)
        self.root_layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.update_selected_device_attributes()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_values)
        self.timer.start(50)

    # Handle the event when the selected device in the combo box changes
    def on_device_changed(self, index: int):
        if index < 0 or index >= len(self.devices):
            return
        self.joystick_index = self.devices[index]["index"]
        self.joy = pygame.joystick.Joystick(self.joystick_index)
        self.joy.init()
        self.setWindowTitle(f"Gamepad Monitor: {self.joy.get_name()}")
        self.update_selected_device_attributes()
        self.clear_value_labels()

    # Clear the displayed values for axes, buttons, and hats
    def clear_value_labels(self):
        for label in self.axis_values.values():
            label.setText("")
        for label in self.button_values.values():
            label.setText("")
        for label in self.hat_values.values():
            label.setText("")

    # Update the displayed attributes for the currently selected device
    def update_selected_device_attributes(self):
        device = self.devices[self.device_combo.currentIndex()]
        self.attribute_labels["name"].setText(device["name"])
        self.attribute_labels["instance_id"].setText(str(device["instance_id"]))
        self.attribute_labels["guid"].setText(device["guid"])
        self.attribute_labels["axes"].setText(str(device["axes"]))
        self.attribute_labels["buttons"].setText(str(device["buttons"]))
        self.attribute_labels["hats"].setText(str(device["hats"]))
        self.attribute_labels["trackballs"].setText(str(device["trackballs"]))

    # Refresh the displayed values for axes, buttons, and hats
    def refresh_values(self):
        if self.joy is None:
            return
        pygame.event.pump()

        for axis_index in range(self.joy.get_numaxes()):
            value = self.joy.get_axis(axis_index)
            display_index = axis_index + 1
            self.axis_values[axis_index].setText(f"Axis {display_index}: {value:.3f}")

        for button_index in range(self.joy.get_numbuttons()):
            pressed = bool(self.joy.get_button(button_index))
            state = "Pressed" if pressed else "Released"
            display_index = button_index + 1
            self.button_values[button_index].setText(f"Button {display_index}: {state}")

        for hat_index in range(self.joy.get_numhats()):
            x, y = self.joy.get_hat(hat_index)
            display_index = hat_index + 1
            self.hat_values[hat_index].setText(f"Hat {display_index}: ({x}, {y})")

    # Close the gamepad monitor window and clean up resources
    def close_window(self):
        self.timer.stop()
        pygame.quit()
        self.close()


def main():
    if not pygame.get_init():
        pygame.init()
    pygame.joystick.init()

    devices = detect_joysticks()
    if not devices:
        print("No joystick found.")
        return 0

    if QApplication is None or QWidget is None or QTimer is None:
        raise RuntimeError("PySide6 is required to run the GUI. Install it with: pip install pyside6")

    app = QApplication(sys.argv)
    window = GamepadMonitorWindow(devices, 0)
    window.show()
    exit_code = app.exec()
    pygame.quit()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())