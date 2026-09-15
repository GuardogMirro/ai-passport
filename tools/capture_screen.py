import serial, sys, struct, time

port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
out_png = sys.argv[2] if len(sys.argv) > 2 else "screen.png"
s = serial.Serial(port, 115200, timeout=2)
time.sleep(0.3)
s.reset_input_buffer()
s.write(b"FAP_SCREENSHOT_V1\n")
s.flush()

hdr = None
t0 = time.time()
while time.time() - t0 < 8:
    line = b""
    while not line.endswith(b"\n"):
        ch = s.read(1)
        if not ch:
            break
        line += ch
    if not line:
        continue
    text = line.decode("ascii", "replace").strip()
    if text.startswith("FAP_SCREENSHOT_V1 "):
        hdr = text
        break
    # 其它行是日志,跳过
if not hdr:
    print("BAD/NO HEADER")
    sys.exit(1)
parts = hdr.split()
w, h, nbytes = int(parts[1]), int(parts[2]), int(parts[4])
print("header ok:", w, "x", h, nbytes, "bytes")
data = b""
t0 = time.time()
while len(data) < nbytes and time.time() - t0 < 30:
    chunk = s.read(nbytes - len(data))
    if chunk:
        data += chunk
if len(data) < nbytes:
    raise TimeoutError("pixel timeout at %d/%d" % (len(data), nbytes))
s.close()
print("captured", len(data), "bytes")

from PIL import Image
px = struct.unpack("<%dH" % (len(data) // 2), data)
rgb = bytearray()
for v in px:
    r = ((v >> 11) & 0x1F) << 3
    g = ((v >> 5) & 0x3F) << 2
    b = (v & 0x1F) << 3
    rgb += bytes((r, g, b))
img = Image.frombytes("RGB", (w, h), bytes(rgb))
img.save(out_png)
print("saved", out_png)
