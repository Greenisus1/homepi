#!/usr/bin/env python3
"""Home Pi watchdog pinger: the reboot-before-freeze feature, on by default.
Pings /dev/watchdog (kernel bcm2835_wdt, built into the Pi kernel) every
PING_SECONDS. If this process freezes, the kernel reboots the board after
the hardware timeout (~15s on bcm2835_wdt). On clean SIGTERM it writes the
magic character 'V' first so a deliberate stop does NOT reboot.
No /dev/watchdog (or disabled in /etc/homepi/watchdog.conf): exits cleanly.
Tests: --once with WATCHDOGD_DEV=<regular file>."""
import os, signal, sys, time

VERSION = '1.0.2'
DEV = os.environ.get('WATCHDOGD_DEV', '/dev/watchdog')
CONF = os.environ.get('WATCHDOGD_CONF', '/etc/homepi/watchdog.conf')


def read_conf(path):
    conf = {'ENABLED': '1', 'PING_SECONDS': '10'}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    conf[k.strip()] = v.strip()
    except Exception:
        pass
    return conf


def main():
    if '--version' in sys.argv:
        print(VERSION)
        return 0
    conf = read_conf(CONF)
    if conf.get('ENABLED') != '1':
        print('watchdogd: disabled in %s' % CONF)
        return 0
    if not os.path.exists(DEV):
        print('watchdogd: no %s - nothing to do' % DEV)
        return 0
    ping = max(1, int(conf.get('PING_SECONDS', '10')))
    try:
        fd = os.open(DEV, os.O_WRONLY)
        os.write(fd, b'1')
    except OSError as e:
        print('watchdogd: %s is not usable here (%s) - nothing to do' % (DEV, e))
        return 0
    if '--once' in sys.argv:
        os.write(fd, b'V')            # magic close: disarm for the test
        os.close(fd)
        print('watchdogd: ping ok, disarmed (test mode)')
        return 0
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    signal.signal(signal.SIGINT, lambda *a: stop.append(1))
    print('watchdogd: armed, pinging every %ds' % ping)
    rc = 0
    try:
        while not stop:
            time.sleep(ping)
            if stop:
                break
            try:
                os.write(fd, b'1')
            except OSError as e:
                print('watchdogd: ping failed: %s' % e)
                rc = 1
                break
    finally:
        # Whatever happens, never leave the hardware timer armed:
        # the magic character 'V' makes the close a clean disarm.
        try:
            os.write(fd, b'V')
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
    print('watchdogd: disarmed, stopped')
    return rc


if __name__ == '__main__':
    sys.exit(main())
