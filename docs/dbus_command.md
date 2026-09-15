KStars / Ekos / INDI を操作する D-BUS コマンド
--

# KStars

## 調査

基本構造

```
gdbus introspect --session --dest org.kde.kstars --object-path /KStars
```

# INDI

## INDI のインターフェース情報

```bash
gdbus introspect --session --dest org.kde.kstars --object-path /KStars/INDI
node /KStars/INDI {
  interface org.kde.kstars.INDI {
    methods:
      start(in  i port,
            in  as drivers,
            out b arg_0);
      stop(in  s port,
           out b arg_0);
      connect(in  s host,
              in  i port,
              out b arg_0);
      disconnect(in  s host,
                 in  i port,
                 out b arg_0);
      getDevices(out as arg_0);
      getProperties(in  s device,
                    out as arg_0);
      getPropertyState(in  s device,
                       in  s property,
                       out s arg_0);
      getDevicesPaths(in  i interface,
                      out as arg_0);
      sendProperty(in  s device,
                   in  s property,
                   out b arg_0);
      getLight(in  s device,
               in  s property,
               in  s lightName,
               out s arg_0);
      setSwitch(in  s device,
                in  s property,
                in  s switchName,
                in  s status,
                out b arg_0);
      getSwitch(in  s device,
                in  s property,
                in  s switchName,
                out s arg_0);
      setText(in  s device,
              in  s property,
              in  s textName,
              in  s text,
              out b arg_0);
      getText(in  s device,
              in  s property,
              in  s textName,
              out s arg_0);
      setNumber(in  s device,
                in  s property,
                in  s numberName,
                in  d value,
                out b arg_0);
      getNumber(in  s device,
                in  s property,
                in  s numberName,
                out d arg_0);
      getBLOBData(in  s device,
                  in  s property,
                  in  s blobName,
                  out ay arg_0,
                  out s blobFormat,
                  out i size);
      getBLOBFile(in  s device,
                  in  s property,
                  in  s blobName,
                  out s arg_0,
                  out s blobFormat,
                  out i size);
    signals:
    properties:
  };
  interface org.freedesktop.DBus.Properties {
    methods:
      Get(in  s interface_name,
          in  s property_name,
          out v value);
      Set(in  s interface_name,
          in  s property_name,
          in  v value);
      @org.qtproject.QtDBus.QtTypeName.Out0("QVariantMap")
      GetAll(in  s interface_name,
             out a{sv} values);
    signals:
      @org.qtproject.QtDBus.QtTypeName.Out1("QVariantMap")
      PropertiesChanged(s interface_name,
                        a{sv} changed_properties,
                        as invalidated_properties);
    properties:
  };
  interface org.freedesktop.DBus.Introspectable {
    methods:
      Introspect(out s xml_data);
    signals:
    properties:
  };
  interface org.freedesktop.DBus.Peer {
    methods:
      Ping();
      GetMachineId(out s machine_uuid);
    signals:
    properties:
  };
  node GenericDevice {
  };
};
```

## 情報取得


デバイスの一覧
- デバイスの種類がわからないので使い道はない。
```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getDevices
```

デバイスの取得
- 以下コマンドでノードを取得する。
- ノードは `/KStars/INDI/GenericDevice/<ノード番号>` のパスを持つ。
- ノード番号は 1 から始まる整数値。

```bash
gdbus introspect --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice -r
```

デバイスの属性の取得

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice/1 --method org.freedesktop.DBus.Properties.GetAll org.kde.kstars.INDI.GenericDevice
```

デバイスの名前の取得

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice/1 --method org.freedesktop.DBus.Properties.Get org.kde.kstars.INDI.GenericDevice name
```

デバイスのドライバーインターフェース番号取得

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice/1 --method org.freedesktop.DBus.Properties.Get org.kde.kstars.INDI.GenericDevice driverInterface
```

| デバイス種別 | 判別方法 |
| - | - |
| MOUNT | driverInterface & 1 |
| ROTATOR | driverInterface & (1 << 12) |
| FOCUSER | driverInterface & (1 << 3) |
| FILTER | driverInterface & (1 << 4) |

参考）ドライバーインターフェースの定義

`basedvice.h`

```C++
        enum DRIVER_INTERFACE
        {
            GENERAL_INTERFACE       = 0,         /**< Default interface for all INDI devices */
            TELESCOPE_INTERFACE     = (1 << 0),  /**< Telescope interface, must subclass INDI::Telescope */
            CCD_INTERFACE           = (1 << 1),  /**< CCD interface, must subclass INDI::CCD */
            GUIDER_INTERFACE        = (1 << 2),  /**< Guider interface, must subclass INDI::GuiderInterface */
            FOCUSER_INTERFACE       = (1 << 3),  /**< Focuser interface, must subclass INDI::FocuserInterface */
            FILTER_INTERFACE        = (1 << 4),  /**< Filter interface, must subclass INDI::FilterInterface */
            DOME_INTERFACE          = (1 << 5),  /**< Dome interface, must subclass INDI::Dome */
            GPS_INTERFACE           = (1 << 6),  /**< GPS interface, must subclass INDI::GPS */
            WEATHER_INTERFACE       = (1 << 7),  /**< Weather interface, must subclass INDI::Weather */
            AO_INTERFACE            = (1 << 8),  /**< Adaptive Optics Interface */
            DUSTCAP_INTERFACE       = (1 << 9),  /**< Dust Cap Interface */
            LIGHTBOX_INTERFACE      = (1 << 10), /**< Light Box Interface */
            DETECTOR_INTERFACE      = (1 << 11), /**< Detector interface, must subclass INDI::Detector */
            ROTATOR_INTERFACE       = (1 << 12), /**< Rotator interface, must subclass INDI::RotatorInterface */
            SPECTROGRAPH_INTERFACE  = (1 << 13), /**< Spectrograph interface */
            CORRELATOR_INTERFACE    = (1 << 14), /**< Correlators (interferometers) interface */
            AUX_INTERFACE           = (1 << 15), /**< Auxiliary interface */
            OUTPUT_INTERFACE        = (1 << 16), /**< Digital Output (e.g. Relay) interface */
            INPUT_INTERFACE         = (1 << 17), /**< Digital/Analog Input (e.g. GPIO) interface */
            POWER_INTERFACE         = (1 << 18), /**< Power Controller interface */
            IMU_INTERFACE           = (1 << 19), /**< Intertial Measurement Unit interface */
            PAC_INTERFACE = (1 << 20), /**< Polar Alignment Correction interface, must subclass INDI::PACInterface */

            SENSOR_INTERFACE        = SPECTROGRAPH_INTERFACE | DETECTOR_INTERFACE | CORRELATOR_INTERFACE
        };
```

## FOCUSER - /KStars/INDI

### Focuser - インターフェース情報

Device番号の4が FOCUSER の場合

```bash
gdbus introspect --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice/4
node /KStars/INDI/GenericDevice/4 {
  interface org.kde.kstars.INDI.GenericDevice {
    methods:
      @org.freedesktop.DBus.Method.NoReply("true")
      Connect();
      @org.freedesktop.DBus.Method.NoReply("true")
      Disconnect();
    signals:
      Connected();
      Disconnected();
      ready();
    properties:
      readonly s name = 'Focuser Simulator';
      readonly i driverInterface = 8;
      readonly s driverVersion = '1.0';
      readonly b connected = true;
  };
  interface org.freedesktop.DBus.Properties {
    methods:
      Get(in  s interface_name,
          in  s property_name,
          out v value);
      Set(in  s interface_name,
          in  s property_name,
          in  v value);
      @org.qtproject.QtDBus.QtTypeName.Out0("QVariantMap")
      GetAll(in  s interface_name,
             out a{sv} values);
    signals:
      @org.qtproject.QtDBus.QtTypeName.Out1("QVariantMap")
      PropertiesChanged(s interface_name,
                        a{sv} changed_properties,
                        as invalidated_properties);
    properties:
  };
  interface org.freedesktop.DBus.Introspectable {
    methods:
      Introspect(out s xml_data);
    signals:
    properties:
  };
  interface org.freedesktop.DBus.Peer {
    methods:
      Ping();
      GetMachineId(out s machine_uuid);
    signals:
    properties:
  };
};
```
### Focuser - プロパティの一覧

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getProperties "Focuser Simulator"
([
    'Focuser Simulator.CONNECTION.CONNECT', 'Focuser Simulator.CONNECTION.DISCONNECT',
	'Focuser Simulator.DRIVER_INFO.DRIVER_NAME',
	'Focuser Simulator.DRIVER_INFO.DRIVER_EXEC',
	'Focuser Simulator.DRIVER_INFO.DRIVER_VERSION',
	'Focuser Simulator.DRIVER_INFO.DRIVER_INTERFACE',

	'Focuser Simulator.DEBUG.ENABLE',
	'Focuser Simulator.DEBUG.DISABLE',

	'Focuser Simulator.POLLING_PERIOD.PERIOD_MS',

	'Focuser Simulator.CONFIG_PROCESS.CONFIG_LOAD',
	'Focuser Simulator.CONFIG_PROCESS.CONFIG_SAVE',
	'Focuser Simulator.CONFIG_PROCESS.CONFIG_DEFAULT',
	'Focuser Simulator.CONFIG_PROCESS.CONFIG_PURGE',

	'Focuser Simulator.CONNECTION_MODE.CONNECTION_SERIAL',
	'Focuser Simulator.CONNECTION_MODE.CONNECTION_TCP',

	'Focuser Simulator.DEVICE_PORT.PORT',
	'Focuser Simulator.DEVICE_BAUD_RATE.9600',
	'Focuser Simulator.DEVICE_BAUD_RATE.19200',
	'Focuser Simulator.DEVICE_BAUD_RATE.38400',
	'Focuser Simulator.DEVICE_BAUD_RATE.57600',
	'Focuser Simulator.DEVICE_BAUD_RATE.115200',
	'Focuser Simulator.DEVICE_BAUD_RATE.230400',
	'Focuser Simulator.DEVICE_AUTO_SEARCH.INDI_ENABLED',
	'Focuser Simulator.DEVICE_AUTO_SEARCH.INDI_DISABLED',
	'Focuser Simulator.DEVICE_PORT_SCAN.Scan Ports',

	'Focuser Simulator.Mode.All',
	'Focuser Simulator.Mode.Absolute',
	'Focuser Simulator.Mode.Relative',
	'Focuser Simulator.Mode.Timer',

	'Focuser Simulator.FOCUS_MOTION.FOCUS_INWARD',
	'Focuser Simulator.FOCUS_MOTION.FOCUS_OUTWARD',
	'Focuser Simulator.FOCUS_SPEED.FOCUS_SPEED_VALUE',
	'Focuser Simulator.REL_FOCUS_POSITION.FOCUS_RELATIVE_POSITION',
	'Focuser Simulator.ABS_FOCUS_POSITION.FOCUS_ABSOLUTE_POSITION',
	'Focuser Simulator.FOCUS_MAX.FOCUS_MAX_VALUE',
	'Focuser Simulator.FOCUS_SYNC.FOCUS_SYNC_VALUE',

	'Focuser Simulator.FOCUS_BACKLASH_TOGGLE.INDI_ENABLED',
	'Focuser Simulator.FOCUS_BACKLASH_TOGGLE.INDI_DISABLED',
	'Focuser Simulator.FOCUS_BACKLASH_STEPS.FOCUS_BACKLASH_VALUE',

	'Focuser Simulator.Presets.PRESET_1',
	'Focuser Simulator.Presets.PRESET_2',
	'Focuser Simulator.Presets.PRESET_3',
	'Focuser Simulator.Goto.Preset 1',
	'Focuser Simulator.Goto.Preset 2',
	'Focuser Simulator.Goto.Preset 3',

	'Focuser Simulator.USEJOYSTICK.ENABLE',
	'Focuser Simulator.USEJOYSTICK.DISABLE',
	'Focuser Simulator.SNOOP_JOYSTICK.SNOOP_JOYSTICK_DEVICE',
	'Focuser Simulator.SEEING_SETTINGS.SIM_SEEING',
	'Focuser Simulator.FWHM.SIM_FWHM',
	'Focuser Simulator.FOCUS_TEMPERATURE.TEMPERATURE',
	'Focuser Simulator.DELAY.DELAY_VALUE'
],)
```

### Focus IN

```bash
# フォーカスの相対移動の状況のステータス "busy" の場合は以降のコマンドを送信しない。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getPropertyState "Focuser Simulator" "REL_FOCUS_POSITION"

# 移動方向の設定
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setSwitch "Focuser Simulator" "FOCUS_MOTION" "FOCUS_INWARD" "On"
# 設定値の送信
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Focuser Simulator" "FOCUS_MOTION"

# 相対移動
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setNumber "Focuser Simulator" "REL_FOCUS_POSITION" "FOCUS_RELATIVE_POSITION" "100"
# 設定値の送信
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Focuser Simulator" "REL_FOCUS_POSITION"
```

### Focus OUT

```bash
# フォーカスの相対移動の状況のステータス "busy" の場合は以降のコマンドを送信しない。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getPropertyState "Focuser Simulator" "REL_FOCUS_POSITION"

# 移動方向の設定
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setSwitch "Focuser Simulator" "FOCUS_MOTION" "FOCUS_OUTWARD" "On"
# 設定値の送信
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Focuser Simulator" "FOCUS_MOTION"

# 相対移動
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setNumber "Focuser Simulator" "REL_FOCUS_POSITION" "FOCUS_RELATIVE_POSITION" "100"
# 設置値の送信
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Focuser Simulator" "REL_FOCUS_POSITION"
```

### Focuser - 現在のステップの取得

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getNumber "Focuser Simulator" "REL_FOCUS_POSITION" "FOCUS_RELATIVE_POSITION"
```

## FILTER WHEEL

### Filter Wheel - インターフェース情報

Device番号の5が FILTER WHEEL の場合

```bash
gdbus introspect --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice/5
node /KStars/INDI/GenericDevice/5 {
  interface org.kde.kstars.INDI.GenericDevice {
    methods:
      @org.freedesktop.DBus.Method.NoReply("true")
      Connect();
      @org.freedesktop.DBus.Method.NoReply("true")
      Disconnect();
    signals:
      Connected();
      Disconnected();
      ready();
    properties:
      readonly s name = 'Filter Simulator';
      readonly i driverInterface = 16;
      readonly s driverVersion = '1.0';
      readonly b connected = true;
  };
  interface org.freedesktop.DBus.Properties {
    methods:
      Get(in  s interface_name,
          in  s property_name,
          out v value);
      Set(in  s interface_name,
          in  s property_name,
          in  v value);
      @org.qtproject.QtDBus.QtTypeName.Out0("QVariantMap")
      GetAll(in  s interface_name,
             out a{sv} values);
    signals:
      @org.qtproject.QtDBus.QtTypeName.Out1("QVariantMap")
      PropertiesChanged(s interface_name,
                        a{sv} changed_properties,
                        as invalidated_properties);
    properties:
  };
  interface org.freedesktop.DBus.Introspectable {
    methods:
      Introspect(out s xml_data);
    signals:
    properties:
  };
  interface org.freedesktop.DBus.Peer {
    methods:
      Ping();
      GetMachineId(out s machine_uuid);
    signals:
    properties:
  };
};
```

### Filter Wheel - プロパティの一覧

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getProperties "Filter Simulator"
([
	'Filter Simulator.CONFIG_PROCESS.CONFIG_LOAD',
	'Filter Simulator.CONFIG_PROCESS.CONFIG_SAVE',
	'Filter Simulator.CONFIG_PROCESS.CONFIG_DEFAULT',
	'Filter Simulator.CONFIG_PROCESS.CONFIG_PURGE',
	'Filter Simulator.CONNECTION.CONNECT',
	'Filter Simulator.CONNECTION.DISCONNECT',
	'Filter Simulator.DRIVER_INFO.DRIVER_NAME',
	'Filter Simulator.DRIVER_INFO.DRIVER_EXEC',
	'Filter Simulator.DRIVER_INFO.DRIVER_VERSION',
	'Filter Simulator.DRIVER_INFO.DRIVER_INTERFACE',

	'Filter Simulator.FILTER_SLOT.FILTER_SLOT_VALUE',
	
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_1', 
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_2', 
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_3',
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_4',
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_5',
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_6',
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_7',
	'Filter Simulator.FILTER_NAME.FILTER_SLOT_NAME_8',

	'Filter Simulator.USEJOYSTICK.ENABLE',
	'Filter Simulator.USEJOYSTICK.DISABLE',
	'Filter Simulator.SNOOP_JOYSTICK.SNOOP_JOYSTICK_DEVICE',
	'Filter Simulator.DELAY.VALUE'
],)
```

### Filter Wheel - スロット数のスキャン

```bash
# フィルタースロットに設定されたフィルター名の取得。フィルタースロットの最小値と最大値を超えた場合は "Invalid" を返す。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getText "Filter Simulator" "FILTER_NAME" "FILTER_SLOT_NAME_1"
```

### Filter Wheel - 現在のスロット

```bash
# Filter Wheel の現在のスロットの設定の状況のステータス "busy" の場合は以降のコマンドを送信しない。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getPropertyState "Filter Simulator" "FILTER_SLOT"

# 現在のスロット番号の取得
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getNumber "Filter Simulator" "FILTER_SLOT" "FILTER_SLOT_VALUE"

# 現在のスロット番号の設定
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setNumber "Filter Simulator" "FILTER_SLOT" "FILTER_SLOT_VALUE" 2
# 現在のスロット番号の設定送信
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Filter Simulator" "FILTER_SLOT"
```

## ROTATOR

### ROTATOR - インターフェース情報

Device番号の1が Rotator の場合

```bash
gdbus introspect --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice/1
node /KStars/INDI/GenericDevice/1 {
  interface org.kde.kstars.INDI.GenericDevice {
    methods:
      @org.freedesktop.DBus.Method.NoReply("true")
      Connect();
      @org.freedesktop.DBus.Method.NoReply("true")
      Disconnect();
    signals:
      Connected();
      Disconnected();
      ready();
    properties:
      readonly s name = 'Rotator Simulator';
      readonly i driverInterface = 4096;
      readonly s driverVersion = '1.0';
      readonly b connected = true;
  };
  interface org.freedesktop.DBus.Properties {
    methods:
      Get(in  s interface_name,
          in  s property_name,
          out v value);
      Set(in  s interface_name,
          in  s property_name,
          in  v value);
      @org.qtproject.QtDBus.QtTypeName.Out0("QVariantMap")
      GetAll(in  s interface_name,
             out a{sv} values);
    signals:
      @org.qtproject.QtDBus.QtTypeName.Out1("QVariantMap")
      PropertiesChanged(s interface_name,
                        a{sv} changed_properties,
                        as invalidated_properties);
    properties:
  };
  interface org.freedesktop.DBus.Introspectable {
    methods:
      Introspect(out s xml_data);
    signals:
    properties:
  };
  interface org.freedesktop.DBus.Peer {
    methods:
      Ping();
      GetMachineId(out s machine_uuid);
    signals:
    properties:
  };
};
```

### ROTATOR - プロパティの一覧

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getProperties "Rotator Simulator"
([
	'Rotator Simulator.CONNECTION.CONNECT',
	'Rotator Simulator.CONNECTION.DISCONNECT',
	'Rotator Simulator.DRIVER_INFO.DRIVER_NAME',
	'Rotator Simulator.DRIVER_INFO.DRIVER_EXEC',
	'Rotator Simulator.DRIVER_INFO.DRIVER_VERSION',
	'Rotator Simulator.DRIVER_INFO.DRIVER_INTERFACE',
	'Rotator Simulator.DEBUG.ENABLE',
	'Rotator Simulator.DEBUG.DISABLE',
	'Rotator Simulator.CONFIG_PROCESS.CONFIG_LOAD',
	'Rotator Simulator.CONFIG_PROCESS.CONFIG_SAVE',
	'Rotator Simulator.CONFIG_PROCESS.CONFIG_DEFAULT',
	'Rotator Simulator.CONFIG_PROCESS.CONFIG_PURGE',
	'Rotator Simulator.CONNECTION_MODE.CONNECTION_SERIAL',
	'Rotator Simulator.CONNECTION_MODE.CONNECTION_TCP',
	'Rotator Simulator.DEVICE_PORT.PORT',
	'Rotator Simulator.DEVICE_BAUD_RATE.9600',
	'Rotator Simulator.DEVICE_BAUD_RATE.19200',
	'Rotator Simulator.DEVICE_BAUD_RATE.38400',
	'Rotator Simulator.DEVICE_BAUD_RATE.57600',
	'Rotator Simulator.DEVICE_BAUD_RATE.115200',
	'Rotator Simulator.DEVICE_BAUD_RATE.230400',
	'Rotator Simulator.DEVICE_AUTO_SEARCH.INDI_ENABLED',
	'Rotator Simulator.DEVICE_AUTO_SEARCH.INDI_DISABLED',
	'Rotator Simulator.DEVICE_PORT_SCAN.Scan Ports',

	'Rotator Simulator.ABS_ROTATOR_ANGLE.ANGLE',

	'Rotator Simulator.ROTATOR_ABORT_MOTION.ABORT',
	'Rotator Simulator.SYNC_ROTATOR_ANGLE.ANGLE',
	'Rotator Simulator.ROTATOR_REVERSE.INDI_ENABLED',
	'Rotator Simulator.ROTATOR_REVERSE.INDI_DISABLED',
	'Rotator Simulator.ROTATOR_LIMITS.ROTATOR_LIMITS_VALUE',
	'Rotator Simulator.Presets.PRESET_1',
	'Rotator Simulator.Presets.PRESET_2',
	'Rotator Simulator.Presets.PRESET_3',
	'Rotator Simulator.Goto.Preset 1',
	'Rotator Simulator.Goto.Preset 2',
	'Rotator Simulator.Goto.Preset 3'
],)
```

### Rotator - 回転

```bash
# 現在のローテーターの移動状況の取得。"busy" の場合は以後の処理をしない。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getPropertyState "Rotator Simulator" "ABS_ROTATOR_ANGLE"

# ローテーターの最大回転角を取得。戻り値0は制限なし。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getNumber "Rotator Simulator" "ROTATOR_LIMITS" "ROTATOR_LIMITS_VALUE"

# 現在のローテーターの角度を取得
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getNumber "Rotator Simulator" "ABS_ROTATOR_ANGLE" "ANGLE"

# ローテーターの角度を設定
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setNumber "Rotator Simulator" "ABS_ROTATOR_ANGLE" "ANGLE" 10
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Rotator Simulator" "ABS_ROTATOR_ANGLE"
```

-------------------

##### MOUNT

### MOUNT - インターフェース情報

Device番号の6が MOUNT の場合

```bash
gdbus introspect --session --dest org.kde.kstars --object-path /KStars/INDI/GenericDevice/6
node /KStars/INDI/GenericDevice/6 {
  interface org.kde.kstars.INDI.GenericDevice {
    methods:
      @org.freedesktop.DBus.Method.NoReply("true")
      Connect();
      @org.freedesktop.DBus.Method.NoReply("true")
      Disconnect();
    signals:
      Connected();
      Disconnected();
      ready();
    properties:
      readonly s name = 'Telescope Simulator';
      readonly i driverInterface = 5;
      readonly s driverVersion = '1.0';
      readonly b connected = true;
  };
  interface org.freedesktop.DBus.Properties {
    methods:
      Get(in  s interface_name,
          in  s property_name,
          out v value);
      Set(in  s interface_name,
          in  s property_name,
          in  v value);
      @org.qtproject.QtDBus.QtTypeName.Out0("QVariantMap")
      GetAll(in  s interface_name,
             out a{sv} values);
    signals:
      @org.qtproject.QtDBus.QtTypeName.Out1("QVariantMap")
      PropertiesChanged(s interface_name,
                        a{sv} changed_properties,
                        as invalidated_properties);
    properties:
  };
  interface org.freedesktop.DBus.Introspectable {
    methods:
      Introspect(out s xml_data);
    signals:
    properties:
  };
  interface org.freedesktop.DBus.Peer {
    methods:
      Ping();
      GetMachineId(out s machine_uuid);
    signals:
    properties:
  };
};
```

### MOUNT - プロパティの一覧

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getProperties "Telescope Simulator"
([
	'Telescope Simulator.CONNECTION.CONNECT',
	'Telescope Simulator.CONNECTION.DISCONNECT',
	'Telescope Simulator.DRIVER_INFO.DRIVER_NAME',
	'Telescope Simulator.DRIVER_INFO.DRIVER_EXEC',
	'Telescope Simulator.DRIVER_INFO.DRIVER_VERSION',
	'Telescope Simulator.DRIVER_INFO.DRIVER_INTERFACE',
	'Telescope Simulator.POLLING_PERIOD.PERIOD_MS',
	'Telescope Simulator.DEBUG.ENABLE',
	'Telescope Simulator.DEBUG.DISABLE',
	'Telescope Simulator.ALIGNMENT_POINT_MANDATORY_NUMBERS.ALIGNMENT_POINT_ENTRY_OBSERVATION_JULIAN_DATE',
	'Telescope Simulator.ALIGNMENT_POINT_MANDATORY_NUMBERS.ALIGNMENT_POINT_ENTRY_RA',
	'Telescope Simulator.ALIGNMENT_POINT_MANDATORY_NUMBERS.ALIGNMENT_POINT_ENTRY_DEC',
	'Telescope Simulator.ALIGNMENT_POINT_MANDATORY_NUMBERS.ALIGNMENT_POINT_ENTRY_VECTOR_X',
	'Telescope Simulator.ALIGNMENT_POINT_MANDATORY_NUMBERS.ALIGNMENT_POINT_ENTRY_VECTOR_Y',
	'Telescope Simulator.ALIGNMENT_POINT_MANDATORY_NUMBERS.ALIGNMENT_POINT_ENTRY_VECTOR_Z',
	'Telescope Simulator.ALIGNMENT_POINT_OPTIONAL_BINARY_BLOB.ALIGNMENT_POINT_ENTRY_PRIVATE',
	'Telescope Simulator.ALIGNMENT_POINTSET_SIZE.ALIGNMENT_POINTSET_SIZE',
	'Telescope Simulator.ALIGNMENT_POINTSET_CURRENT_ENTRY.ALIGNMENT_POINTSET_CURRENT_ENTRY',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.APPEND',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.INSERT',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.EDIT',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.DELETE',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.CLEAR',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.READ',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.READ INCREMENT',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.LOAD DATABASE',
	'Telescope Simulator.ALIGNMENT_POINTSET_ACTION.SAVE DATABASE',
	'Telescope Simulator.ALIGNMENT_POINTSET_COMMIT.ALIGNMENT_POINTSET_COMMIT',
	'Telescope Simulator.ALIGNMENT_SUBSYSTEM_MATH_PLUGINS.INBUILT_MATH_PLUGIN',
	'Telescope Simulator.ALIGNMENT_SUBSYSTEM_MATH_PLUGINS.Nearest Math Plugin',
	'Telescope Simulator.ALIGNMENT_SUBSYSTEM_MATH_PLUGINS.SPK Math Plugin',
	'Telescope Simulator.ALIGNMENT_SUBSYSTEM_MATH_PLUGINS.SVD Math Plugin',
	'Telescope Simulator.ALIGNMENT_SUBSYSTEM_MATH_PLUGIN_INITIALISE.ALIGNMENT_SUBSYSTEM_MATH_PLUGIN_INITIALISE',
	'Telescope Simulator.ALIGNMENT_SUBSYSTEM_ACTIVE.ALIGNMENT SUBSYSTEM ACTIVE',
	'Telescope Simulator.CONFIG_PROCESS.CONFIG_LOAD',
	'Telescope Simulator.CONFIG_PROCESS.CONFIG_SAVE',
	'Telescope Simulator.CONFIG_PROCESS.CONFIG_DEFAULT',
	'Telescope Simulator.CONFIG_PROCESS.CONFIG_PURGE',
	'Telescope Simulator.CONNECTION_MODE.CONNECTION_SERIAL',
	'Telescope Simulator.CONNECTION_MODE.CONNECTION_TCP',
	'Telescope Simulator.DEVICE_PORT.PORT',
	'Telescope Simulator.DEVICE_BAUD_RATE.9600',
	'Telescope Simulator.DEVICE_BAUD_RATE.19200',
	'Telescope Simulator.DEVICE_BAUD_RATE.38400',
	'Telescope Simulator.DEVICE_BAUD_RATE.57600',
	'Telescope Simulator.DEVICE_BAUD_RATE.115200',
	'Telescope Simulator.DEVICE_BAUD_RATE.230400',
	'Telescope Simulator.DEVICE_AUTO_SEARCH.INDI_ENABLED',
	'Telescope Simulator.DEVICE_AUTO_SEARCH.INDI_DISABLED',
	'Telescope Simulator.DEVICE_PORT_SCAN.Scan Ports',
	'Telescope Simulator.ACTIVE_DEVICES.ACTIVE_GPS',
	'Telescope Simulator.ACTIVE_DEVICES.ACTIVE_DOME',
	'Telescope Simulator.DOME_POLICY.DOME_IGNORED',
	'Telescope Simulator.DOME_POLICY.DOME_LOCKS',
	'Telescope Simulator.SIM_PIER_SIDE.PS_OFF',
	'Telescope Simulator.SIM_PIER_SIDE.PS_ON',
	'Telescope Simulator.MOUNT_MODEL.MM_IH',
	'Telescope Simulator.MOUNT_MODEL.MM_ID',
	'Telescope Simulator.MOUNT_MODEL.MM_CH',
	'Telescope Simulator.MOUNT_MODEL.MM_NP',
	'Telescope Simulator.MOUNT_MODEL.MM_MA',
	'Telescope Simulator.MOUNT_MODEL.MM_ME',
	'Telescope Simulator.MOUNT_AXES.PRIMARY',
	'Telescope Simulator.MOUNT_AXES.SECONDARY',
	'Telescope Simulator.FLIP_HA.FLIP_HA',
	'Telescope Simulator.DEC_BACKLASH.DEC_BACKLASH',
	'Telescope Simulator.ACTIVE_PAC.PAC_DEVICE',
	'Telescope Simulator.ON_COORD_SET.TRACK',
	'Telescope Simulator.ON_COORD_SET.SLEW',
	'Telescope Simulator.ON_COORD_SET.SYNC',
	'Telescope Simulator.EQUATORIAL_EOD_COORD.RA',
	'Telescope Simulator.EQUATORIAL_EOD_COORD.DEC',
	'Telescope Simulator.TELESCOPE_ABORT_MOTION.ABORT',
	'Telescope Simulator.TELESCOPE_TRACK_MODE.TRACK_SIDEREAL',
	'Telescope Simulator.TELESCOPE_TRACK_MODE.TRACK_SOLAR',
	'Telescope Simulator.TELESCOPE_TRACK_MODE.TRACK_LUNAR',
	'Telescope Simulator.TELESCOPE_TRACK_MODE.TRACK_CUSTOM',
	'Telescope Simulator.TELESCOPE_TRACK_STATE.TRACK_ON',
	'Telescope Simulator.TELESCOPE_TRACK_STATE.TRACK_OFF',
	'Telescope Simulator.TELESCOPE_TRACK_RATE.TRACK_RATE_RA',
	'Telescope Simulator.TELESCOPE_TRACK_RATE.TRACK_RATE_DE',
	'Telescope Simulator.TELESCOPE_HOME.FIND',
	'Telescope Simulator.TELESCOPE_HOME.SET',
	'Telescope Simulator.TELESCOPE_HOME.GO',

	'Telescope Simulator.TELESCOPE_MOTION_NS.MOTION_NORTH',
	'Telescope Simulator.TELESCOPE_MOTION_NS.MOTION_SOUTH',
	'Telescope Simulator.TELESCOPE_MOTION_WE.MOTION_WEST',
	'Telescope Simulator.TELESCOPE_MOTION_WE.MOTION_EAST',

	'Telescope Simulator.TELESCOPE_REVERSE_MOTION.REVERSE_NS',
	'Telescope Simulator.TELESCOPE_REVERSE_MOTION.REVERSE_WE',

	'Telescope Simulator.TELESCOPE_SLEW_RATE.1x',
	'Telescope Simulator.TELESCOPE_SLEW_RATE.2x',
	'Telescope Simulator.TELESCOPE_SLEW_RATE.3x',
	'Telescope Simulator.TELESCOPE_SLEW_RATE.4x',

	'Telescope Simulator.TARGET_EOD_COORD.RA',
	'Telescope Simulator.TARGET_EOD_COORD.DEC',
	'Telescope Simulator.TELESCOPE_MOUNT_TYPE.ALTAZ',
	'Telescope Simulator.TELESCOPE_MOUNT_TYPE.EQ_FORK',
	'Telescope Simulator.TELESCOPE_MOUNT_TYPE.EQ_GEM',
	'Telescope Simulator.TIME_UTC.UTC',
	'Telescope Simulator.TIME_UTC.OFFSET',
	'Telescope Simulator.GEOGRAPHIC_COORD.LAT',
	'Telescope Simulator.GEOGRAPHIC_COORD.LONG',
	'Telescope Simulator.GEOGRAPHIC_COORD.ELEV',
	'Telescope Simulator.TELESCOPE_PARK.PARK',
	'Telescope Simulator.TELESCOPE_PARK.UNPARK',
	'Telescope Simulator.TELESCOPE_PARK_POSITION.PARK_HA',
	'Telescope Simulator.TELESCOPE_PARK_POSITION.PARK_DEC',
	'Telescope Simulator.TELESCOPE_PARK_OPTION.PARK_CURRENT',
	'Telescope Simulator.TELESCOPE_PARK_OPTION.PARK_DEFAULT',
	'Telescope Simulator.TELESCOPE_PARK_OPTION.PARK_WRITE_DATA',
	'Telescope Simulator.TELESCOPE_PARK_OPTION.PARK_PURGE_DATA',
	'Telescope Simulator.TELESCOPE_PIER_SIDE.PIER_WEST',
	'Telescope Simulator.TELESCOPE_PIER_SIDE.PIER_EAST',
	'Telescope Simulator.USEJOYSTICK.ENABLE',
	'Telescope Simulator.USEJOYSTICK.DISABLE',
	'Telescope Simulator.SNOOP_JOYSTICK.SNOOP_JOYSTICK_DEVICE',
	'Telescope Simulator.GUIDE_RATE.GUIDE_RATE_WE',
	'Telescope Simulator.GUIDE_RATE.GUIDE_RATE_NS',
	'Telescope Simulator.EQUATORIAL_PE.RA_PE',
	'Telescope Simulator.EQUATORIAL_PE.DEC_PE',
	'Telescope Simulator.TELESCOPE_TIMED_GUIDE_NS.TIMED_GUIDE_N',
	'Telescope Simulator.TELESCOPE_TIMED_GUIDE_NS.TIMED_GUIDE_S',
	'Telescope Simulator.TELESCOPE_TIMED_GUIDE_WE.TIMED_GUIDE_W',
	'Telescope Simulator.TELESCOPE_TIMED_GUIDE_WE.TIMED_GUIDE_E'
],)
```

### MOUNT - Slew Speed

Slewスピードのスイッチを取得する。

- マウントの INDI ドライバーごとに TELESCOPE_SLEW_RATE の設定が異なる。プロパティ一覧から取得する必要がある。
- プロパティの一覧から 'Telescope Simulator.TELESCOPE_SLEW_RATE' の属性を取得する。
- 	"Telescope Simurator の場合は "`Telescope Simulator.TELESCOPE_SLEW_RATE.1x`, `Telescope Simulator.TELESCOPE_SLEW_RATE.2x`, `Telescope Simulator.TELESCOPE_SLEW_RATE.3x`, `Telescope Simulator.TELESCOPE_SLEW_RATE.4x` を取得できる。

```bash
# プロパティの一覧の取得
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getProperties "Telescope Simulator"
```

Slew Spped の設定
- 以下は 2x に設定する例

```bash
# 設定が可能か確認。"busy" の場合は以後の設定をしない。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getPropertyState "Telescope Simulator" "TELESCOPE_SLEW_RATE"

# Slew Rate を設定する。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setSwitch "Telescope Simulator" "TELESCOPE_SLEW_RATE" "2x" "On"
# Slew Rate を設定送信する。
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Telescope Simulator" "TELESCOPE_SLEW_RATE"
```

### MOUNT - Slew

＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊＊

```bash
# 北 へ Slew
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setSwitch "Telescope Simulator" "TELESCOPE_MOTION_NS" "MOTION_NORTH" "On"
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Telescope Simulator" "TELESCOPE_MOTION_NS"

# 南 へ Slew
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setSwitch "Telescope Simulator" "TELESCOPE_MOTION_NS" "MOTION_SOUTH" "On"
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Telescope Simulator" "TELESCOPE_MOTION_NS"
```

### MOUNT - Abort Slewing

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.setSwitch "Telescope Simulator" "TELESCOPE_ABORT_MOTION" "ABORT" "On"
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.sendProperty "Telescope Simulator" "TELESCOPE_ABORT_MOTION"
```

### 参考）MOUNT SLEW に関する情報取得

```bash
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getSwitch "Telescope Simulator" "TELESCOPE_MOTION_NS" "MOTION_NORTH"
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getSwitch "Telescope Simulator" "TELESCOPE_MOTION_NS" "MOTION_SOUTH"
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getSwitch "Telescope Simulator" "TELESCOPE_MOTION_WE" "MOTION_WEST"
gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getSwitch "Telescope Simulator" "TELESCOPE_MOTION_WE" "MOTION_EAST"
```





## KStars

gdbus call --session --dest org.kde.kstars --object-path /KStars --method org.kde.kstars.zoomIn
gdbus call --session --dest org.kde.kstars --object-path /KStars --method org.kde.kstars.zoomOut
gdbus call --session --dest org.kde.kstars --object-path /KStars --method org.kde.kstars.getSkyMapRotation
gdbus call --session --dest org.kde.kstars --object-path /KStars --method org.kde.kstars.setSkyMapRotation "90.0"







gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos/Capture --method org.freedesktop.DBus.Properties.GetAll org.kde.kstars.Ekos.Capture
gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos/Capture --method org.freedesktop.DBus.Properties.GetAll org.kde.kstars.Ekos.Capture


gdbus introspect --session --dest org.kde.kstars --object-path /KStars/Ekos/Capture



gdbus introspect --session --dest org.kde.kstars --object-path /KStars/INDI


gdbus call --session --dest org.kde.kstars --object-path /KStars/INDI --method org.kde.kstars.INDI.getDevices

gdbus introspect --session --dest org.kde.kstars --object-path /KStars/Ekos
gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos --method org.kde.kstars.Ekos.getProfiles 

busctl list

        QDBusInterface capture(
            "org.kde.kstars",
            "/KStars/Ekos/Capture",
            "org.kde.kstars.Ekos.Capture",
            QDBusConnection::sessionBus());

        QVariant opticalTrainValue = capture.property("opticalTrain"); // 



# Ekos

※Ekosは使わない

## 調査

基本構造

```bash
$ gdbus introspect --session --dest org.kde.kstars --object-path /KStars/Ekos
```

全プロパティ取得

```bash
$ gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos --method org.freedesktop.DBus.Properties.GetAll org.kde.kstars.Ekos
({'ekosLiveStatus': <true>, 'ekosStatus': <2>, 'extensionStatus': <3>, 'indiStatus': <2>, 'logText': <[*****]>, 'settleStatus': <uint32 2>},)
```

全 Ekos Profile 取得

```bash
$ gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos --method org.kde.kstars.Ekos.getProfiles
(['Simulators', 'sim sm5', 'RC6', 'sim sv241pro', 'sim'],)
```

Optical Train 取得

```bash
$ gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos/Capture --method org.freedesktop.DBus.Properties.Get org.kde.kstars.Ekos.Capture opticalTrain
```
※/KStars/Ekos に Optical Train を取得する method や property はない。

## FOCUS - /KStars/Ekos/Focus

```bash
# /KStars/Ekos/Focusの 構造調査
$ gdbus introspect --session --dest org.kde.kstars --object-path /KStars/Ekos/Focus

# 停止
$ gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos/Focus --method org.kde.kstars.Ekos.Focus.abort "Primary"

# フォーカスIN
$ gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos/Focus --method org.kde.kstars.Ekos.Focus.focusIn "Primary" 100

# フォーカスOUT
$ gdbus call --session --dest org.kde.kstars --object-path /KStars/Ekos/Focus --method org.kde.kstars.Ekos.Focus.focusOut "Primary" 100
```


## MOUNT - /KStars/Ekos/Mount

※相対移動がないので /KStars/Ekos/Mount は使えない・・・
