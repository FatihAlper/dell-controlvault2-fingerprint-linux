#!/usr/bin/env python3
# CV2 fingerprint probe using the EXACT userspace transport reverse-engineered
# from processCommand() in the closed CV3 driver libfprint-2-tod-1-broadcom.so:
#   - claim interface 0 (NO vendor power-gate; the CV path doesn't use one)
#   - write the RAW 44-byte CV-encap command to bulk OUT 0x01 (no SPI wrapper)
#   - read 32 bytes from INTERRUPT IN 0x85   <-- the step earlier probes skipped
#   - read the payload from bulk IN 0x81
# Header layout from cvhEncapsulateCmd disasm:
#   +00 u32=1 | +04 u32=totalLen | +08 u16=cmdID | +0a u16=flags(0x40 plaintext)
#   +0c u32=libver | +10 u32=0 | +14 u32=0 | +18..27 reserved=0 | +28 u32=numParams | +2c params
import struct, logging, usb.core, usb.util
logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger("cv")
VID, PID = 0x0a5c, 0x5834
EP_OUT, EP_BULK_IN, EP_INTR_IN = 0x01, 0x81, 0x85
H = lambda b: ' '.join('%02x' % x for x in bytes(b))
A = lambda b: ''.join(chr(c) if 32 <= c < 127 else '.' for c in bytes(b))

def encap(cmd_id, params=b'', flags=0x0040, libver=0):
    h = bytearray(0x2c)
    struct.pack_into('<I', h, 0x00, 1)
    struct.pack_into('<I', h, 0x04, 0x2c + len(params))
    struct.pack_into('<H', h, 0x08, cmd_id)
    struct.pack_into('<H', h, 0x0a, flags)
    struct.pack_into('<I', h, 0x0c, libver)
    struct.pack_into('<I', h, 0x28, len(params))   # numParams/param-bytes
    return bytes(h) + params

# read-only / bring-up commands recovered from the driver's .dynsym (from-symbols)
CMDS = [
    (0x39, "cv_get_ush_ver"),
    (0x02, "cv_open"),
    (0x06, "cv_init"),
    (0x80, "cv_detect_fp"),
    (0x3f, "cv_enable (0x3f)"),
    (0x41, "cv_enable_fingerprint"),
]

dev = usb.core.find(idVendor=VID, idProduct=PID)
assert dev, "device not found"
log.info("[*] %04x:%04x  iface0 transport (RAW encap, intr 0x85 + bulk 0x81)", VID, PID)
try:
    if dev.is_kernel_driver_active(0): dev.detach_kernel_driver(0)
except Exception: pass
usb.util.claim_interface(dev, 0)

any_reply = False
for cid, name in CMDS:
    pkt = encap(cid)
    log.info("\n=== %s (0x%02x) ===", name, cid)
    log.info("[>] OUT 0x01 raw (%dB): %s", len(pkt), H(pkt))
    try:
        n = dev.write(EP_OUT, pkt, timeout=3000)
        log.info("    wrote %d bytes", n)
    except usb.core.USBError as e:
        log.info("    write FAILED: %s", e.strerror or e); continue
    # the KEY step: interrupt IN 0x85
    try:
        r = dev.read(EP_INTR_IN, 32, timeout=4000).tobytes()
        any_reply = True
        log.info("[<] INTR 0x85 (%dB): %s | %s", len(r), H(r), A(r))
    except usb.core.USBError as e:
        log.info("[<] INTR 0x85: nothing (%s)", e.strerror or e)
    # then bulk IN 0x81
    try:
        r = dev.read(EP_BULK_IN, 256, timeout=4000).tobytes()
        any_reply = True
        log.info("[<] BULK 0x81 (%dB): %s | %s", len(r), H(r), A(r))
    except usb.core.USBError as e:
        log.info("[<] BULK 0x81: nothing (%s)", e.strerror or e)

log.info("\n[*] RESULT: %s", "GOT A REPLY from iface0 CV layer!" if any_reply else "total silence on iface0 CV layer")
usb.util.release_interface(dev, 0)
usb.util.dispose_resources(dev)
