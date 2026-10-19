# miio-cloudfree

Control Xiaomi **miIO** Wi-Fi devices (smart plugs and similar) entirely on your
LAN — **no Mi Home account, no cloud, no router changes, no firmware flashing.**

### Tested device

| | |
|---|---|
| Model | `chuangmi.plug.m1` (Xiaomi Mi Smart Plug, Wi-Fi) |
| Hardware / chipset | Marvell MW300 (`hw_ver` = `MW300`) |
| Firmware | `1.4.5_2` |
| Wi-Fi firmware | `SD878x-14.76.36.p84-702.1.0-WM` |

The method is protocol-level (the miIO `config_router` `country_domain` field), so
it should apply to other Xiaomi miIO Wi-Fi devices that accept `country_domain` —
but only the device above has been verified. Reports of other working (or
non-working) devices are very welcome via an issue.

## The problem this solves

Xiaomi plugs are controllable locally over the **miIO** UDP protocol, but every
command is signed with a 16-byte device **token**. You can read that token during
pairing — but the first time the plug reaches **Xiaomi's cloud**, the token is
silently **re-keyed**, and your captured copy stops working. That is why the usual
"grab the setup token" trick fails on current firmware, and why people fall back to
a Mi Home account + cloud token extractor.

## The trick

During pairing, `miIO.config_router` lets you set the plug's cloud server region via
a `country_domain` field. The plug builds its cloud address as
`<country_domain>.ot.io.mi.com`. Real regions resolve (`us`, `de`, `sg`, …); a
**bogus region has no DNS record** and there is **no wildcard**, so
`zz.ot.io.mi.com` is `NXDOMAIN` everywhere.

So we provision the plug with `country_domain=zz`: it joins your Wi-Fi normally
(and may have full internet), but it can **never resolve its own cloud endpoint**,
never reaches Xiaomi, and therefore **never re-keys the token**. Local control keeps
working indefinitely. It's a config value baked into the device, so it needs no
router rules and travels with the plug. A factory reset undoes it.

See [`docs/how-it-works.md`](docs/how-it-works.md) for the full protocol detail and
the evidence this is a cloud-triggered re-key.

## Requirements

- Python 3.9+
- `pip install cryptography`
- A computer with Wi-Fi (to connect to the plug's pairing network once)

## Usage

### 1. Pair the plug (one time)

1. Factory-reset the plug into pairing mode: hold its button ~5s until the LED
   blinks amber/fast. Unplug any load first.
2. Connect **this computer** to the plug's own Wi-Fi — an open network named like
   `chuangmi-plug-m1_miapXXXX`.
3. Provision it onto your Wi-Fi with a dead cloud domain (captures the token):

   ```bash
   python cloudfree_plug.py provision --ssid "YourWiFi" --password "YourPassword"
   ```

   This saves the token to `plug.token` (git-ignored — keep it secret).

### 2. Control it (any time, from any machine on your Wi-Fi)

Reconnect this computer to your normal Wi-Fi, then:

```bash
python cloudfree_plug.py discover                 # find the plug's IP
python cloudfree_plug.py status --ip 192.168.1.50
python cloudfree_plug.py on     --ip 192.168.1.50
python cloudfree_plug.py off    --ip 192.168.1.50
python cloudfree_plug.py toggle --ip 192.168.1.50
```

Pass `--token <hex>` instead of relying on `plug.token` if you prefer. The token
also works with [`python-miio`](https://github.com/rytilahti/python-miio)
(`miiocli device --ip <ip> --token <token> on`) and with Home Assistant / openHAB —
see [`docs/openhab.md`](docs/openhab.md).

## Good to know

- Because the plug can't reach Xiaomi, the Mi Home app won't control it and it gets
  no cloud features or OTA updates — that's the point.
- The token is a secret stored in `plug.token`. Anyone who has it (and can reach the
  plug) can control the plug. `.gitignore` keeps it out of commits.
- Everything is reversible: a **factory reset** clears the config; just re-run
  `provision` to get a fresh token.
- This does not weaken the plug's authentication and does not touch other devices or
  your router.

## Credits / prior art

Built on the shoulders of the miIO community:

- [python-miio](https://github.com/rytilahti/python-miio) — the reference miIO
  protocol implementation.
- [Dennis Giese's dustcloud](https://github.com/dgiese/dustcloud-documentation) —
  Xiaomi device research and flash dumps.
- [openHAB miio binding](https://www.openhab.org/addons/bindings/miio/) — mature
  local control + discovery for miIO devices.

## License

MIT — see [`LICENSE`](LICENSE).
