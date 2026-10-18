import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPAN = os.path.join(HERE, 'spanfs.py')


def run(args, env_extra=None):
    return subprocess.run(['python3', SPAN] + args, capture_output=True, text=True,
                          env=dict(os.environ, **(env_extra or {})))


class TestSpanfs(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.d1 = os.path.join(self.root, 'd1'); os.makedirs(self.d1)
        self.d2 = os.path.join(self.root, 'd2'); os.makedirs(self.d2)
        self.src = os.path.join(self.root, 'big.bin')
        self.body = os.urandom(2 * 1024 ** 2 + 12345)
        with open(self.src, 'wb') as f:
            f.write(self.body)

    def test_roundtrip_across_two_drives(self):
        env = {'SPANFS_FREE_0': str(16 * 1024 ** 3), 'SPANFS_FREE_1': str(16 * 1024 ** 3)}
        r = run(['store', self.src, self.d1, self.d2], env)
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        man = json.load(open(os.path.join(self.d1, 'big.bin.span', 'manifest.json')))
        self.assertEqual(sum(c['bytes'] for c in man['chunks']), len(self.body))
        self.assertTrue(os.path.exists(os.path.join(self.d1, 'big.bin.span', 'reassemble.sh')))
        out = os.path.join(self.root, 'out.bin')
        r = run(['fetch', os.path.join(self.d1, 'big.bin.span'), out, self.d1, self.d2])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(out, 'rb').read(), self.body)

    def test_refuses_when_pool_too_small(self):
        env = {'SPANFS_FREE_0': '1000', 'SPANFS_FREE_1': '1000'}
        r = run(['store', self.src, self.d1, self.d2], env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('pool too small', r.stderr)

    def test_spans_when_one_drive_alone_cannot_fit(self):
        # the owner's case: file 2M, each drive 1.5M free - only spanning works.
        headroom = 100 * 1024 ** 2
        per = int(1.4 * 1024 ** 2)   # usable per drive < file, sum > file
        env = {'SPANFS_FREE_0': str(headroom + per), 'SPANFS_FREE_1': str(headroom + per)}
        r = run(['store', self.src, self.d1, self.d2], env)
        self.assertEqual(r.returncode, 0, r.stderr)
        import json
        man = json.load(open(os.path.join(self.d1, 'big.bin.span', 'manifest.json')))
        drives_used = {c['drive'] for c in man['chunks']}
        self.assertEqual(drives_used, {0, 1})          # truly spans both

    def test_missing_chunk_fails(self):
        env = {'SPANFS_FREE_0': str(16 * 1024 ** 3), 'SPANFS_FREE_1': str(16 * 1024 ** 3)}
        run(['store', self.src, self.d1, self.d2], env)
        import json, glob
        man = json.load(open(os.path.join(self.d1, 'big.bin.span', 'manifest.json')))
        if len(man['chunks']) > 1:
            d2span = os.path.join(self.d2, 'big.bin.span')
            if os.path.isdir(d2span):
                for p in glob.glob(os.path.join(d2span, '*.part')):
                    os.unlink(p)
                    break
        out = os.path.join(self.root, 'out2.bin')
        r = run(['fetch', os.path.join(self.d1, 'big.bin.span'), out, self.d1, self.d2])
        # either it found everything on d1 (single-chunk) or it must fail cleanly
        if len(man['chunks']) > 1 and any(c['drive'] == 1 for c in man['chunks']):
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(out))


if __name__ == '__main__':
    unittest.main()
