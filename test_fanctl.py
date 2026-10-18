import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def make_sysfs(root, temp_mc, pwm=None, enable=None):
    os.makedirs(os.path.join(root, "class/thermal/thermal_zone0"), exist_ok=True)
    with open(os.path.join(root, 'class/thermal/thermal_zone0/temp'), 'w') as f:
        f.write(str(temp_mc))
    if pwm is not None:
        h = os.path.join(root, 'class/hwmon/hwmon0')
        os.makedirs(h, exist_ok=True)
        with open(os.path.join(h, 'pwm1'), 'w') as f:
            f.write(str(pwm))
        if enable is not None:
            with open(os.path.join(h, 'pwm1_enable'), 'w') as f:
                f.write(str(enable))
    return root


def run_once(root, conf=None):
    env = dict(os.environ, FANCTL_SYSFS=root,
               FANCTL_CONF=conf or os.path.join(root, 'no-such-conf'))
    r = subprocess.run(['python3', os.path.join(HERE, 'fanctl.py'), '--once'],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class TestFanCtl(unittest.TestCase):
    def test_no_fan_is_clean_noop(self):
        root = tempfile.mkdtemp()
        make_sysfs(root, 50000)
        self.assertEqual(run_once(root), 'no-fan')

    def test_kernel_managed_is_left_alone(self):
        root = tempfile.mkdtemp()
        make_sysfs(root, 80000, pwm=10, enable=2)   # automatic (Pi 5 cooler)
        self.assertEqual(run_once(root), 'kernel-managed')
        with open(os.path.join(root, 'class/hwmon/hwmon0/pwm1')) as f:
            self.assertEqual(f.read().strip(), '10')   # untouched

    def test_manual_curve_and_hysteresis(self):
        root = tempfile.mkdtemp()
        make_sysfs(root, 80000, pwm=0, enable=1)
        out = run_once(root)
        self.assertIn('pwm=255', out)                  # 80C -> full speed
        make_sysfs(root, 70000, pwm=255, enable=1)     # same hwmon files rewritten
        # rewrite files in same dirs
        out = run_once(root)
        self.assertIn('pwm=224', out)                  # 70C -> high
        make_sysfs(root, 73000, pwm=224, enable=1)
        out = run_once(root)
        self.assertIn('pwm=224', out)                  # hysteresis holds while near band
        make_sysfs(root, 30000, pwm=224, enable=1)
        out = run_once(root)
        self.assertIn('pwm=0', out)                    # cold -> off

    def test_off_mode_silences(self):
        root = tempfile.mkdtemp()
        make_sysfs(root, 90000, pwm=255, enable=1)
        conf = os.path.join(root, 'fan.conf')
        with open(conf, 'w') as f:
            f.write('ENABLED=1\nMODE=off\n')
        self.assertEqual(run_once(root, conf), 'off')
        with open(os.path.join(root, 'class/hwmon/hwmon0/pwm1')) as f:
            self.assertEqual(f.read().strip(), '0')

    def test_disabled_conf_noop(self):
        root = tempfile.mkdtemp()
        make_sysfs(root, 90000, pwm=255, enable=1)
        conf = os.path.join(root, 'fan.conf')
        with open(conf, 'w') as f:
            f.write('ENABLED=0\n')
        r = subprocess.run(['python3', os.path.join(HERE, 'fanctl.py'), '--once'],
                           capture_output=True, text=True,
                           env=dict(os.environ, FANCTL_SYSFS=root, FANCTL_CONF=conf))
        self.assertIn('disabled', r.stdout)


if __name__ == '__main__':
    unittest.main()
