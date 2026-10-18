#!/usr/bin/env python3
"""Build the update metadata for the Greenisus1/homepi repo: system-version.json
+ manifest-<version>.json + payload files, from the Buildroot overlay.
Run before publishing the repo so installed Home Pis can self-update."""
import hashlib, json, os, sys

OVERLAY = 'buildroot-external/board/homepi/rootfs-overlay'
UPDATABLE_PREFIXES = ('usr/bin/',)
SKIP = {'usr/bin/homepi-login'}   # shell wrapper is static; skip list stays tiny


def main(version):
    files = []
    for dirpath, _, fns in os.walk(OVERLAY):
        for fn in fns:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, OVERLAY)
            if not rel.startswith(UPDATABLE_PREFIXES) or rel in SKIP:
                continue
            body = open(full, 'rb').read()
            files.append({'path': rel,
                          'source': OVERLAY + '/' + rel,
                          'sha256': hashlib.sha256(body).hexdigest(),
                          'mode': 0o755})
    mname = 'manifest-%s.json' % version
    with open(mname, 'w') as f:
        json.dump({'files': files}, f, indent=1)
    with open('system-version.json', 'w') as f:
        json.dump({'version': version, 'manifest': mname}, f, indent=1)
    print('release metadata for version %s: %d updatable files' % (version, len(files)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '1.0.0'))
