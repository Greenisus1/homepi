# Raspberry Pi Connect on a console-only Home Pi

Home Pi 1.1.7 adds a system-wide user-unit drop-in for rpi-connect-wayvnc.service.
The reported failure was its ExecStartPre socket check: neither wayland-0 nor
wayland-1 existed. The main Connect daemon was still running and authenticated.
The new condition skips WayVNC when neither path exists, avoiding the startup
failure and restart loop. It does not install a desktop or change screen-sharing
permissions, sign-in state, or remote-shell settings. Existing vendor socket and
compositor checks remain in force when a display is present.

## Apply after this change is merged

On the Pi, update using the installed updater:

```sh
sudo hpupdate --auto
systemctl --user daemon-reload
systemctl --user stop rpi-connect-wayvnc.service
systemctl --user reset-failed rpi-connect-wayvnc.service
rpi-connect on
rpi-connect status
```

Run the user commands as homepi, without sudo. The explicit stop cancels an
already queued retry. A reboot also loads the drop-in. A desktop session that
starts later can start WayVNC normally; if needed run rpi-connect on again.

## Verify on the Pi

With no desktop, rpi-connect on should succeed, the main service should remain
active, and WayVNC should be inactive with an unmet condition rather than retrying.
Test a remote shell from connect.raspberrypi.com. With an existing supported
Wayland desktop and screen sharing allowed, verify that screen sharing still
starts. This patch does not make Connect share a text console.

## Validation limits

The drop-in matches the two paths shown in the affected Pi's vendor unit.
Its update manifest checksum was verified. Runtime systemd and hardware tests
must be run on the Pi; the development Mac cannot execute those tests.
