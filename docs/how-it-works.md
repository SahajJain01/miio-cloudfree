# How it works

## The miIO protocol (the short version)

Xiaomi Wi-Fi devices speak **miIO** over UDP port `54321`:

- A **hello** packet (`21310020ffffffff…`, 32 bytes) asks a device to identify
  itself. The reply carries the device id and a 32-byte header whose token field is
  either the real 16-byte **token** (during pairing) or zeros (once "token privacy"
  is on).
- Every real command is a header + `md5(header + token + ciphertext)` + ciphertext,
  where the ciphertext is AES-128-CBC with `key = md5(token)` and
  `iv = md5(key + token)`. Without the current token you cannot form a valid command
  and the device replies with a 32-byte signature-failure packet.

So **local control == having the current token.**

## Why the naive approach fails

During pairing the plug *discloses* its token, so you can read it. But on
`chuangmi.plug.m1` (firmware `1.4.5_2`) the token you capture at pairing stops
working once the plug has been online for a moment.

This was confirmed by a controlled test:

1. The plug was provisioned onto a network with **no path to Xiaomi**. The captured
   token authenticated fine and could switch the relay on/off.
2. That same network was then given a normal internet uplink. Within ~2 minutes the
   plug contacted `*.ot.io.mi.com` on UDP `8053` (Xiaomi's cloud), and the **same
   token was now rejected**.
3. Repeating step 1 but keeping the plug off Xiaomi's cloud: the token kept working
   indefinitely, including with full internet on the network.

Conclusion: the token is **re-keyed on first contact with Xiaomi's cloud**, not on
reboot and not on a timer. Firmware analysis is consistent with this — the local
"provisioning done" path does not regenerate the token; only a reset-to-pairing or a
cloud exchange changes it.

## The fix: a dead cloud domain

`miIO.config_router` (the account-free command that tells the plug which Wi-Fi to
join) also accepts a `country_domain` field. The firmware builds the cloud server
address as:

```
<country_domain>.ot.io.mi.com
```

Real regions resolve:

```
ot.io.mi.com      -> 8.219.62.149
us.ot.io.mi.com   -> 47.84.232.143
de.ot.io.mi.com   -> 20.33.1.228
```

Bogus regions do **not** — there is no wildcard record:

```
zz.ot.io.mi.com   -> NXDOMAIN
qz.ot.io.mi.com   -> NXDOMAIN
```

Because DNS resolves the same on any network, a plug provisioned with
`country_domain=zz` can never resolve its own cloud endpoint, so it never reaches
Xiaomi, so the token is never re-keyed. Verified live: with full internet, the plug
issued only failing DNS lookups and made **zero** connections to Xiaomi's `:8053`,
and the captured token continued to authenticate.

## What this does and does not do

- It does **not** bypass authentication, weaken encryption, or expose the token to
  the network — token privacy stays on, so discovery still reports zeros.
- It does **not** touch your router or any other device.
- It simply points one field at a name that does not exist, so the device cannot
  phone home. A factory reset clears it.

## Reproducing the DNS check

```bash
for r in "" us. de. sg. zz. qz. xx.; do
  printf '%-16s ' "${r}ot.io.mi.com"
  nslookup "${r}ot.io.mi.com" 1.1.1.1 >/dev/null 2>&1 && echo resolves || echo NXDOMAIN
done
```
