# Troubleshooting

## Calibration fails near the far end

Compare repeated stationary position readings. If their spread is comparable to calibration displacement, single samples cannot provide a dependable scale. Check target visibility and alignment across travel. Mechanical backlash or missed steps are also possible; the log alone cannot distinguish them. See [Calibration](calibration.html).

## Target moves say calibration is required

A failed calibration clears the scale, even if an earlier attempt succeeded. Target moves remain disabled until the next successful calibration. Startup and reset also require a new calibration.

## Maximum steps exceeded

Estimate distance × steps/mm. A 100 mm move at about 222 steps/mm requires about 22,200 steps. Slide-node manifests use a 100,000-step cap. Preserve a finite cap and inspect calibration quality rather than increasing it indefinitely.

## Target is outside the configured range

The demo defaults to 30–300 mm in the adapter's coordinate frame. `slide_nodes.set_range(30, 300)` changes the running provider; manifest edits set startup defaults. Position samples use metres while helper targets use millimetres.

## TOF timeout or invalid range status

Use `position()` without motion first. Verify the wiring, I2C address and target. Reinstall the full package and reset to ensure both driver files are current. A fresh-measurement timeout raises `RuntimeError` with a sensor-specific message.

## Client times out

Check entity, node identities, channel, provider startup, and radio reachability. A timeout may be a lost command, a lost reply, or a long-running operation. Do not automatically resend a move. Stop/inspect the provider first; stopping the client device does not stop the provider.

## Native crash during startup

Retain the full dump and last startup message. The slide launcher preloads imports on the foreground stack and allocates explicit worker stacks; use the complete current package. CPython or Unix MicroPython tests do not reproduce every ESP32 firmware failure.

## Useful diagnostic record

Record the firmware/board variant, installed manifest configuration, startup log, calibration report, stationary readings, target command, terminal event, and whether the carriage physically moved. Distinguish measured position from the target you requested.
