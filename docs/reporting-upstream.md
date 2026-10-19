# Sharing this finding upstream

The `country_domain` trick is protocol-level (it concerns miIO / Xiaomi's cloud,
not openHAB specifically), so it is useful to the whole ecosystem. Good venues, in
order:

1. **openHAB community forum** — https://community.openhab.org (category: *Add-ons →
   Bindings*, tag `miio`). Best place to make it known to openHABians. Post the text
   below as a "how-to / solved" topic.
2. **openhab-addons GitHub** — https://github.com/openhab/openhab-addons. Open a
   **Discussion** (not a bug issue), or a small **docs PR** adding a "cloud-free
   token" note to `bundles/org.openhab.binding.miio/README.md`.
3. **python-miio** — https://github.com/rytilahti/python-miio (Discussions). This is
   upstream of most miIO tooling (incl. Home Assistant), so it reaches the widest
   audience.

Do **not** paste your device token or Wi-Fi password into any public post.

---

## Draft post (copy/paste, adjust the repo link)

**Title:** Cloud-free, stable local token for Xiaomi miIO plugs via a dead `country_domain`

You can keep a Xiaomi Wi-Fi plug (tested: `chuangmi.plug.m1`, MW300, fw `1.4.5_2`) on
your normal Wi-Fi and control it locally **indefinitely** — no Mi Home account, no
cloud token extractor, and no router firewall rules.

**The problem.** miIO signs every command with the device token. You can read the
token during pairing, but the first time the plug reaches Xiaomi's cloud it is
**re-keyed**, so the captured token stops working. That's why people normally need a
Mi Home account + cloud token extractor.

**The trick.** The account-free `miIO.config_router` command (used during pairing to
set the Wi-Fi) also takes a `country_domain` field, from which the firmware builds
its cloud server name `<country_domain>.ot.io.mi.com`. Real regions resolve; bogus
ones do **not** (no wildcard):

```
ot.io.mi.com    -> 8.219.62.149      us.ot.io.mi.com -> 47.84.232.143
de.ot.io.mi.com -> 20.33.1.228       zz.ot.io.mi.com -> NXDOMAIN
```

Provision the plug with `country_domain=zz` and its cloud endpoint is unresolvable on
**every** network, so it never reaches Xiaomi and the token is never re-keyed. The
plug can still have full internet on the LAN; it just can't phone home.

**Evidence (controlled test).** Provisioned onto an isolated network the token
authenticated and switched the relay. The network was then given a real uplink: the
plug contacted `*.ot.io.mi.com:8053` and within ~2 min the same token was rejected.
Repeating with `country_domain=zz` and a real uplink, packet capture showed the plug
made only failing DNS lookups and **zero** connections to `:8053`, and the token kept
working.

**Why it matters for the miio binding.** The binding already does LAN discovery and
direct IP+token control (`communication="direct"`). The only piece it couldn't get
without the cloud was a *stable* token. This method provides one, so a plug can be
added to openHAB fully cloud-free and stay working. Might be worth a short note in the
binding docs.

**Scope / caveats.** Tested on `chuangmi.plug.m1` only; likely applies to other miIO
plugs that accept `country_domain`, untested. Reversible with a factory reset. The
plug loses Mi Home app control and OTA updates (that's the point).

**Tooling.** Small MIT CLI that pairs + controls the plug this way:
https://github.com/SahajJain01/cloudfree-xiaomi-plug

Credits: python-miio, Dennis Giese's dustcloud, and the openHAB miio binding.
