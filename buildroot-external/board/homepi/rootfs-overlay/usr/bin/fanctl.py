#!/usr/bin/env python3
"""Home Pi fan manager: uses whatever fan the board has, degrades quietly.
- Pi 5 active cooler: kernel/firmware already drive it via the device tree;
  fanctl detects that (pwm1_enable != manual) and leaves it alone.
- GPIO/PWM fan (hwmon pwm1 in manual mode, or MODE=manual): applies a
  temperature curve with hysteresis.
- No fan hardware at all: exits cleanly, nothing breaks.
Config: /etc/homepi/fan.conf (ENABLED=1, MODE=auto|manual|off).
Tests: --once with FANCTL_SYSFS=<fake sysfs root>, FANCTL_CONF=<file>."""
import glob, os, signal, sys, time

VERSION = '1.0.0'
SYSFS = os.environ.get('FANCTL_SYSFS', '/sys')
CONF = os.environ.get('FANCTL_CONF', '/etc/homepi/fan.conf')

# (below this temp C -> pwm). First match wins.
CURVE = [(45, 0), (55, 96), (65, 160), (75, 224), (10 ** 9, 255)]
HYSTERESIS_C = 2
SETTLE_S = 5


def read_conf(path):
    conf = {'ENABLED': '1', 'MODE': 'auto'}
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


def cpu_temp_c():
    with open(os.path.join(SYSFS, 'class/thermal/thermal_zone0/temp')) as f:
        return int(f.read().strip()) / 1000.0


def find_pwm():
    """Returns (pwm_path, enable_path, enable_value) of the first fan, or None."""
    for pwm in sorted(glob.glob(os.path.join(SYSFS, 'class/hwmon/hwmon*/pwm1'))):
        enable = pwm + '_enable'
        val = None
        if os.path.exists(enable):
            try:
                with open(enable) as f:
                    val = int(f.read().strip())
            except Exception:
                val = None
        return pwm, enable, val
    return None


def curve_target(temp_c, last_pwm):
    target = CURVE[-1][1]
    for limit, pwm in CURVE:
        if temp_c < limit:
            target = pwm
            break
    if target < last_pwm and last_pwm != 0:
        # hysteresis: only step down when clearly below the band
        for limit, pwm in CURVE:
            if pwm == last_pwm and temp_c > limit - HYSTERESIS_C:
                return last_pwm
    return target


def apply_once(mode):
    """One control pass. Returns a status string (used by tests and logs)."""
    found = find_pwm()
    if not found:
        return 'no-fan'
    pwm, enable, enable_val = found
    if mode == 'off':
        _write(pwm, 0)
        return 'off'
    if mode == 'auto' and enable_val is not None and enable_val != 1:
        return 'kernel-managed'          # e.g. Pi 5 active cooler: leave it
    if enable_val is not None:
        _write(enable, 1)                # take manual control
    temp = cpu_temp_c()
    try:
        with open(pwm) as f:
            last = int(f.read().strip())
    except Exception:
        last = 0
    target = curve_target(temp, last)
    _write(pwm, target)
    return 'pwm=%d temp=%.1f' % (target, temp)


def _write(path, value):
    with open(path, 'w') as f:
        f.write(str(value))


def main():
    if '--version' in sys.argv:
        print(VERSION)
        return 0
    conf = read_conf(CONF)
    if conf.get('ENABLED') != '1':
        print('fanctl: disabled in %s' % CONF)
        return 0
    mode = conf.get('MODE', 'auto')
    if '--once' in sys.argv:
        print(apply_once(mode))
        return 0
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    while not stop:
        try:
            apply_once(mode)
        except Exception as e:
            print('fanctl: %s' % e, file=sys.stderr)
        time.sleep(SETTLE_S)
    return 0


if __name__ == '__main__':
    sys.exit(main())
