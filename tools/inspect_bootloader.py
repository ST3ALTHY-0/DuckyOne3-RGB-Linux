import os
import time
import glob
import select
import subprocess


def return_to_aprom(device):
    print("Returning to APROM...", flush=True)
    report = bytearray(65)
    report[1] = 0xAB
    fd = os.open(device, os.O_RDWR)
    try:
        os.write(fd, report)
    finally:
        os.close(fd)
    time.sleep(2)


def find_hidraw(pid):
    import glob
    import os

    expected = bytes.fromhex(
        "05 01 09 00 a1 01 15 00 25 ff "
        "19 00 29 ff 95 40 75 08 81 02 "
        "19 00 29 ff 91 02 c0"
    )

    pattern = f"/sys/bus/hid/devices/*3233:{pid:04X}*"

    for path in glob.glob(pattern):
        raw = glob.glob(path + "/hidraw/hidraw*")
        if not raw:
            continue

        if pid == 0x5311:
            with open(path + "/report_descriptor", "rb") as f:
                descriptor = f.read()

            if descriptor != expected:
                continue

        return "/dev/" + os.path.basename(raw[0])

    return None

# Step 1: Find keyboard in normal mode
device = find_hidraw(0x5311)

if not device:
    raise RuntimeError("Ducky keyboard not found in APROM mode")

print("Application interface:", device, flush=True)

# Step 2: Enter bootloader
fd = os.open(device, os.O_RDWR)
try:
    report = bytearray(65)
    report[1] = 0xCC
    os.write(fd, report)
finally:
    os.close(fd)

print("Switching to LDROM...", flush=True)

# Step 3: Wait for bootloader to appear
device = None

for _ in range(30):
    device = find_hidraw(0x5310)
    if device:
        break
    time.sleep(0.2)

if not device:
    raise RuntimeError("Bootloader did not appear")

print("Bootloader interface:", device, flush=True)

# Step 4: Send connect command
# Wait for udev permissions to be applied
for attempt in range(30):
    try:
        fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
        break
    except (PermissionError, FileNotFoundError):
        time.sleep(0.2)
else:
    raise RuntimeError(
        f"Cannot open bootloader interface {device} after 6 seconds"
    )
    
try:
    report = bytearray(65)
    report[1] = 0xAE

    print("Sending 0xAE connect...", flush=True)
    print("Bytes written:", os.write(fd, report), flush=True)

    ready, _, _ = select.select([fd], [], [], 5)

    if ready:
        response = os.read(fd, 64)
        print("Response:", response.hex(" "), flush=True)
    else:
        print("No response within 5 seconds", flush=True)

finally:
    os.close(fd)
    return_to_aprom(device)

subprocess.run(["lsusb", "-d", "3233:5311"])
