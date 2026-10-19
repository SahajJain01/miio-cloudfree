#!/usr/bin/env python3
"""cloudfree-xiaomi-plug — set up and control a Xiaomi chuangmi.plug.m1 (and
similar miIO Wi-Fi plugs) entirely on your LAN, with no Mi Home account and no
cloud dependency.

Why this exists
---------------
Xiaomi plugs speak a local UDP protocol (miIO) that signs every command with a
16-byte device *token*. The token is disclosed during pairing, but the first
time the plug reaches Xiaomi's cloud it is silently **re-keyed**, which breaks
any token you captured and is why "just grab the setup token" stopped working.

The trick this tool uses: during pairing we (a) capture the token and (b) tell
the plug, via miIO.config_router's `country_domain` field, to use a cloud server
name that does not exist in DNS (e.g. "zz" -> zz.ot.io.mi.com, which is NXDOMAIN
with no wildcard). The plug can then never reach Xiaomi on *any* network, so the
token is never re-keyed and local control keeps working — even on an
internet-connected Wi-Fi, with no router changes.

Tested on chuangmi.plug.m1 (Marvell MW300, firmware 1.4.5_2). Likely works on
other miIO Wi-Fi plugs that expose country_domain; untested there.

Requires: Python 3.9+ and `cryptography` (pip install cryptography).

Quick start
-----------
1. Factory-reset the plug into pairing mode (hold the button ~5s until the LED
   blinks amber/fast).
2. Connect THIS computer to the plug's Wi-Fi (an open network named like
   `chuangmi-plug-m1_miapXXXX`).
3. Provision it onto your Wi-Fi with a dead cloud domain, capturing the token:
       python cloudfree_plug.py provision --ssid "YourWiFi" --password "secret"
4. Reconnect this computer to "YourWiFi", find the plug and control it:
       python cloudfree_plug.py discover
       python cloudfree_plug.py on  --ip <plug-ip>
       python cloudfree_plug.py off --ip <plug-ip>
"""
import argparse
import hashlib
import json
import os
import socket
import struct
import sys
import time

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:  # pragma: no cover
    sys.exit("Missing dependency. Install it with:  pip install cryptography")

HELLO = bytes.fromhex("21310020" + "ffffffff" * 7)  # miIO discovery "hello"
SETUP_IP = "192.168.13.1"        # chuangmi.plug.m1 pairing-AP gateway
MIIO_PORT = 54321
DEFAULT_TOKEN_FILE = "plug.token"
PLACEHOLDERS = (bytes(16), b"\xff" * 16)
_rid = 1000


# ---------------------------------------------------------------- miIO codec
def _key_iv(token):
    key = hashlib.md5(token).digest()
    iv = hashlib.md5(key + token).digest()
    return key, iv


def encrypt(data, token):
    key, iv = _key_iv(token)
    pad = padding.PKCS7(128).padder()
    data = pad.update(data) + pad.finalize()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return enc.update(data) + enc.finalize()


def decrypt(data, token):
    key, iv = _key_iv(token)
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    data = dec.update(data) + dec.finalize()
    unpad = padding.PKCS7(128).unpadder()
    return unpad.update(data) + unpad.finalize()


def hello(ip, timeout=5.0):
    """Return (device_id_bytes, stamp, token_field) from a miIO hello reply."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(HELLO, (ip, MIIO_PORT))
        pkt, _ = s.recvfrom(1024)
    if len(pkt) < 32 or pkt[:2] != b"\x21\x31":
        raise RuntimeError("not a miIO device at %s" % ip)
    return pkt[8:12], int.from_bytes(pkt[12:16], "big"), pkt[16:32]


def rpc(ip, token, method, params, timeout=5.0):
    """Send one authenticated miIO command and return its `result`."""
    global _rid
    _rid += 1
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.connect((ip, MIIO_PORT))
        s.send(HELLO)
        h = s.recv(1024)
        did, stamp = h[8:12], int.from_bytes(h[12:16], "big")
        plain = json.dumps({"id": _rid, "method": method, "params": params},
                           separators=(",", ":")).encode() + b"\x00"
        payload = encrypt(plain, token)
        header = struct.pack(">HHI4sI", 0x2131, 32 + len(payload), 0, did, stamp)
        s.send(header + hashlib.md5(header + token + payload).digest() + payload)
        reply = s.recv(4096)
    if len(reply) <= 32:
        raise RuntimeError("no response payload — token rejected (has the plug "
                           "reached Xiaomi's cloud and re-keyed?)")
    if hashlib.md5(reply[:16] + token + reply[32:]).digest() != reply[16:32]:
        raise RuntimeError("checksum mismatch — wrong token")
    out = json.loads(decrypt(reply[32:], token).rstrip(b"\x00"))
    if "error" in out:
        raise RuntimeError("device error: %s" % out["error"])
    return out.get("result")


# ---------------------------------------------------------------- token I/O
def load_token(args):
    if getattr(args, "token", None):
        tok = bytes.fromhex(args.token.strip())
    else:
        path = args.token_file
        if not os.path.exists(path):
            sys.exit("No token. Pass --token <hex> or --token-file <path> "
                     "(run `provision` first).")
        tok = bytes.fromhex(open(path).read().strip())
    if len(tok) != 16:
        sys.exit("Token must be 32 hex characters (16 bytes).")
    return tok


def save_token(path, token):
    with open(path, "w") as f:
        f.write(token.hex())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------- commands
def cmd_provision(args):
    print("Looking for the plug's pairing AP at %s ..." % args.ip)
    did, _, token = hello(args.ip)
    if token in PLACEHOLDERS:
        sys.exit("The plug did not disclose a token. Make sure it is freshly "
                 "factory-reset into pairing mode and that THIS computer is "
                 "connected to the plug's own Wi-Fi.")
    info = rpc(args.ip, token, "miIO.info", [])
    model = info.get("model", "?") if isinstance(info, dict) else "?"
    fw = info.get("fw_ver", "?") if isinstance(info, dict) else "?"
    print("Found %s (firmware %s, id %s)." % (model, fw, did.hex()))

    params = {"ssid": args.ssid, "passwd": args.password, "uid": 0}
    if args.country_domain:
        params["country_domain"] = args.country_domain
        print("Pinning cloud domain to %s.ot.io.mi.com (NXDOMAIN) so the plug "
              "can never reach Xiaomi." % args.country_domain)
    try:
        rpc(args.ip, token, "miIO.config_router", params)
        print("config_router acknowledged.")
    except (socket.timeout, OSError):
        # The pairing AP often drops before replying; that is normal. Never resend.
        print("No ack (the pairing AP dropped, which is normal) — not resending.")

    save_token(args.token_file, token)
    print("\nToken saved to %s (keep it secret; it is NOT in git)." % args.token_file)
    print("The plug is joining '%s'. Now:" % args.ssid)
    print("  1. Reconnect this computer to '%s'." % args.ssid)
    print("  2. Find the plug:     python cloudfree_plug.py discover")
    print("  3. Control it:        python cloudfree_plug.py on --ip <plug-ip>")


def _local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("8.8.8.8", 80))  # no packet sent; just picks the route
            return s.getsockname()[0]
        except OSError:
            return None


def cmd_discover(args):
    local = _local_ip()
    if args.broadcast:
        targets = [args.broadcast]
    else:
        targets = ["255.255.255.255"]
        if local:
            targets.append(local.rsplit(".", 1)[0] + ".255")  # subnet-directed
    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if local:
            try:
                s.bind((local, 0))  # pin to the LAN interface on multi-homed hosts
            except OSError:
                pass
        s.settimeout(0.6)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            for net in targets:
                try:
                    s.sendto(HELLO, (net, MIIO_PORT))
                except OSError:
                    pass
            try:
                while True:
                    pkt, peer = s.recvfrom(1024)
                    if len(pkt) >= 32 and pkt[:2] == b"\x21\x31":
                        found[peer[0]] = pkt[8:12].hex()
            except socket.timeout:
                pass
    if not found:
        print("No miIO devices found. Tip: pass --broadcast <your-subnet>.255 "
              "(e.g. 192.168.1.255), or find the plug's IP in your router's "
              "client list and use the commands with --ip directly.")
        return
    for ip, did in sorted(found.items()):
        print("%-15s  device-id %s" % (ip, did))


def cmd_rpc(args, method, params):
    token = load_token(args)
    result = rpc(args.ip, token, method, params)
    print(json.dumps(result))
    return result


def cmd_status(args):
    token = load_token(args)
    power = rpc(args.ip, token, "get_prop", ["power"])
    temp = None
    try:
        temp = rpc(args.ip, token, "get_prop", ["temperature"])
    except RuntimeError:
        pass
    print("power: %s" % (power[0] if isinstance(power, list) else power)
          + ("" if temp is None else "   temperature: %s" % (temp[0] if isinstance(temp, list) else temp)))


def cmd_on(args):
    print(rpc(args.ip, load_token(args), "set_power", ["on"]))


def cmd_off(args):
    print(rpc(args.ip, load_token(args), "set_power", ["off"]))


def cmd_toggle(args):
    token = load_token(args)
    cur = rpc(args.ip, token, "get_prop", ["power"])
    cur = cur[0] if isinstance(cur, list) else cur
    print(rpc(args.ip, token, "set_power", ["off" if cur == "on" else "on"]))


def cmd_selftest(args):
    tok = bytes(range(16))
    assert decrypt(encrypt(b'{"hello":1}', tok), tok).rstrip(b"\x00") == b'{"hello":1}'
    print("PASS: AES-128-CBC/MD5 miIO codec round-trip OK.")


# ---------------------------------------------------------------- CLI
def main():
    p = argparse.ArgumentParser(description="Cloud-free local control for Xiaomi miIO plugs.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("provision", help="run while connected to the plug's pairing AP")
    pv.add_argument("--ssid", required=True, help="your Wi-Fi name the plug should join")
    pv.add_argument("--password", required=True, help="your Wi-Fi password")
    pv.add_argument("--country-domain", default="zz",
                    help="bogus 1-3 char region -> NXDOMAIN cloud (default: zz). "
                         "Use '' to keep the normal cloud (NOT recommended).")
    pv.add_argument("--ip", default=SETUP_IP, help="pairing-AP gateway (default 192.168.13.1)")
    pv.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    pv.set_defaults(func=cmd_provision)

    dc = sub.add_parser("discover", help="find miIO devices on your LAN")
    dc.add_argument("--broadcast", default=None,
                    help="broadcast address (default: auto — global + your subnet)")
    dc.add_argument("--seconds", type=float, default=4.0)
    dc.set_defaults(func=cmd_discover)

    for name, fn, helptext in (("status", cmd_status, "read power/temperature"),
                               ("on", cmd_on, "turn the relay on"),
                               ("off", cmd_off, "turn the relay off"),
                               ("toggle", cmd_toggle, "flip the relay")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--ip", required=True, help="the plug's LAN IP")
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--token", help="16-byte token as 32 hex chars")
        g.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
        sp.set_defaults(func=fn)

    st = sub.add_parser("selftest", help="verify the crypto codec (no network)")
    st.set_defaults(func=cmd_selftest)

    args = p.parse_args()
    if getattr(args, "country_domain", None) == "":
        args.country_domain = None
    try:
        args.func(args)
    except RuntimeError as e:
        sys.exit("Error: %s" % e)
    except socket.timeout:
        sys.exit("Error: timed out talking to the plug (wrong IP, or not reachable).")


if __name__ == "__main__":
    main()
