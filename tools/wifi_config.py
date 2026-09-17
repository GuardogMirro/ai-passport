#!/usr/bin/env python3
"""tools/wifi_config.py -- manage the device's stored Wi-Fi profiles over USB.

The firmware keeps up to 8 profiles in NVS and auto-connects to the
strongest visible one; this tool adds/deletes/lists them via the serial
host protocol (line commands, same channel as FAP_SCREENSHOT_V1).

usage:
  python tools/wifi_config.py COM5 list
  python tools/wifi_config.py COM5 add "SSID" "PASSWORD"
  python tools/wifi_config.py COM5 del "SSID"

Notes:
  * SSIDs containing a comma need no special handling here -- the tool
    sends fields separated by a TAB, which SSIDs/passphrases never use.
  * 2.4 GHz networks only (ESP32-C3 has no 5 GHz radio).
  * The password is sent to the device but never echoed or logged.
"""
import serial
import sys
import time

# Same lesson as tools/capture_screen.py (2026-09-16): pyserial toggles
# DTR/RTS on open, which resets the ESP32-C3. Hold both inactive instead.


def open_port(port):
    s = serial.Serial()
    s.port = port
    s.baudrate = 115200
    s.timeout = 2
    s.dtr = False
    s.rts = False
    s.open()
    time.sleep(0.3)
    s.reset_input_buffer()
    return s


def read_replies(s, prefix, settle=1.5, timeout=8.0):
    """Collect reply lines for prefix; stop after a quiet period or OK/ERR."""
    lines = []
    t0 = time.time()
    last = time.time()
    buf = b""
    while time.time() - t0 < timeout and time.time() - last < settle:
        ch = s.read(1)
        if not ch:
            continue
        buf += ch
        if buf.endswith(b"\n"):
            text = buf.decode("ascii", "replace").strip()
            buf = b""
            if text.startswith(prefix) or text.startswith("FAP_WIFI_ERR"):
                lines.append(text)
                last = time.time()
                if " OK " in text + " " or " ERR" in text:
                    break
    return lines


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    port, action = sys.argv[1], sys.argv[2].lower()
    s = open_port(port)
    try:
        if action == "list":
            s.write(b"FAP_WIFI_LIST_V1\n")
            s.flush()
            for line in read_replies(s, "FAP_WIFI") or ["(no reply)"]:
                print(line)
            return 0
        if action == "add" and len(sys.argv) == 5:
            ssid, pwd = sys.argv[3], sys.argv[4]
            payload = ("FAP_WIFI_ADD_V1 %s\t%s\n" % (ssid, pwd)).encode("utf-8")
            s.write(payload)
            s.flush()
            for line in read_replies(s, "FAP_WIFI_ADD_V1") or ["(no reply)"]:
                print(line)
            return 0
        if action == "del" and len(sys.argv) == 4:
            payload = ("FAP_WIFI_DEL_V1 %s\n" % sys.argv[3]).encode("utf-8")
            s.write(payload)
            s.flush()
            for line in read_replies(s, "FAP_WIFI_DEL_V1") or ["(no reply)"]:
                print(line)
            return 0
        print(__doc__)
        return 2
    finally:
        s.dtr = False
        s.rts = False
        s.close()


if __name__ == "__main__":
    raise SystemExit(main())
