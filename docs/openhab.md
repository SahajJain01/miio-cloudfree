# Using the plug with openHAB (cloud-free)

**You do not need a new binding.** openHAB already ships a mature
[**miio binding**](https://www.openhab.org/addons/bindings/miio/) that controls and
auto-discovers `chuangmi.plug.m1` over the LAN. The only thing it cannot do without
the Mi Home cloud is obtain the **token** — and this project gives you a stable,
cloud-free token. So the openHAB recipe is: provision with this tool, then hand the
token to the existing binding.

## Steps

1. **Provision the plug** with this tool so it is on your Wi-Fi with a dead cloud
   domain and you have its token (`plug.token`). See the main
   [README](../README.md).

2. **Install the Miio binding** in openHAB (Settings → Bindings → *Xiaomi Mi IO*).

3. **Add the Thing.** The binding's background discovery will find the plug on your
   LAN and create an inbox entry for it. Open it and fill in:
   - **IP address** — the plug's LAN IP (`cloudfree_plug.py discover`).
   - **Token** — the 32-hex-character token from `plug.token`.
   - **Model / Device ID** — usually auto-filled (`chuangmi.plug.m1`).

   Or define it in a `.things` file:

   ```java
   Thing miio:basic:plug "Smart Plug" [
       host="192.168.1.50",
       token="PUT_YOUR_32_HEX_CHAR_TOKEN_HERE",
       deviceId="02b37890",
       model="chuangmi.plug.m1",
       communication="direct"
   ]
   ```

   `communication="direct"` keeps all traffic on the LAN (no cloud fallback).

4. **Use the channels.** The binding exposes `power` (switch), `temperature`, and
   power-measurement channels. Link `power` to an Item and you're done:

   ```java
   Switch Plug_Power "Plug" { channel="miio:basic:plug:power" }
   ```

## Notes

- Keep the token out of version control (the openHAB Thing config holds it; treat
  `.things` files and the JSONDB as secret).
- Because the plug can't reach Xiaomi, the binding's cloud-token features are
  irrelevant — you supplied the token directly, and `communication="direct"` avoids
  any cloud path.
- If a future device model isn't in the binding's database, the binding still works
  in a generic/experimental mode given IP + token; report the model upstream so it
  can be added.

## Why not a standalone binding?

A separate openHAB binding for this plug would duplicate the existing miio binding
(same protocol, same model support, same discovery) and would not be accepted
upstream. The genuinely missing piece was always the cloud-free token, which this
project solves. If you want to contribute to openHAB specifically, the highest-value
paths are: adding any unsupported plug models to the miio binding's device database,
or improving its docs — not a competing binding.
