#!/usr/bin/env python3
"""Home Pi combined drives (spanfs): pool drives so a file bigger than any
one drive's free space can still be stored - split into chunks spread across
the pool, with a manifest and a reassemble script next to the chunks.
Honest tradeoff (README): spanned files die if ANY drive in the pool dies.
Not RAID, no redundancy. Chunked on purpose: plain mergerfs-style pooling
keeps files whole, which cannot fit a 22G file into 16G free - chunking can.
Tests override free space with SPANFS_FREE_<i>=<bytes> per pool drive."""
import hashlib, json, os, shutil, sys

VERSION = '1.0.0'
CHUNK_MAX = 4 * 1024 ** 3          # 4G cap per chunk
HEADROOM = 100 * 1024 ** 2         # keep 100M free on each drive
SPAN_SUFFIX = '.span'


def free_bytes(path, index=None):
    if index is not None:
        fake = os.environ.get('SPANFS_FREE_%d' % index)
        if fake is not None:
            return int(fake)
    return shutil.disk_usage(path).free


def alloc(total, frees):
    """Greedy chunk plan: fill the emptiest drives proportionally-ish.
    Returns list of (drive_index, bytes) or None when the pool is too small."""
    avail = [max(0, f - HEADROOM) for f in frees]
    if sum(avail) < total:
        return None
    plan = []
    left = total
    while left > 0:
        i = max(range(len(avail)), key=lambda j: avail[j])
        take = min(avail[i], left, CHUNK_MAX)
        plan.append((i, take))
        avail[i] -= take
        left -= take
    return plan


def store(file_path, drives):
    size = os.path.getsize(file_path)
    frees = [free_bytes(d, i) for i, d in enumerate(drives)]
    plan = alloc(size, frees)
    if plan is None:
        raise SystemExit('spanfs: pool too small: need %d, have %d usable'
                         % (size, sum(max(0, f - HEADROOM) for f in frees)))
    name = os.path.basename(file_path.rstrip('/'))
    span_dir = os.path.join(drives[plan[0][0]], name + SPAN_SUFFIX)
    os.makedirs(span_dir, exist_ok=True)
    manifest = {'version': 1, 'name': name, 'size': size, 'chunks': [],
                'sha256': None}
    h = hashlib.sha256()
    with open(file_path, 'rb') as src:
        for n, (di, take) in enumerate(plan):
            part = '%04d.part' % (n + 1)
            dest = os.path.join(drives[di], name + SPAN_SUFFIX) \
                if di != plan[0][0] else span_dir
            os.makedirs(dest, exist_ok=True)
            ppath = os.path.join(dest, part)
            remaining = take
            with open(ppath, 'wb') as out:
                while remaining > 0:
                    block = src.read(min(1024 ** 2, remaining))
                    if not block:
                        raise SystemExit('spanfs: source shrank during store')
                    out.write(block)
                    h.update(block)
                    remaining -= len(block)
            manifest['chunks'].append({'drive': di, 'part': part, 'bytes': take})
    manifest['sha256'] = h.hexdigest()
    with open(os.path.join(span_dir, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=1)
    script = os.path.join(span_dir, 'reassemble.sh')
    with open(script, 'w') as f:
        f.write('#!/bin/sh\n# Reassemble %s from its span chunks.\n'
                'exec spanfs.py fetch "%s" "${1:-%s.restored}"\n'
                % (name, name + SPAN_SUFFIX, name))
    os.chmod(script, 0o755)
    return span_dir


def fetch(span_dir, out_path, drives=None):
    with open(os.path.join(span_dir, 'manifest.json')) as f:
        manifest = json.load(f)
    h = hashlib.sha256()
    base = os.path.dirname(span_dir.rstrip('/'))
    with open(out_path, 'wb') as out:
        for chunk in manifest['chunks']:
            candidates = []
            if drives and chunk['drive'] < len(drives):
                candidates.append(os.path.join(drives[chunk['drive']],
                                               manifest['name'] + SPAN_SUFFIX,
                                               chunk['part']))
            candidates.append(os.path.join(base, manifest['name'] + SPAN_SUFFIX,
                                           chunk['part']))
            ppath = next((c for c in candidates if os.path.exists(c)), None)
            if not ppath:
                raise SystemExit('spanfs: missing chunk %s' % chunk['part'])
            with open(ppath, 'rb') as src:
                while True:
                    block = src.read(1024 ** 2)
                    if not block:
                        break
                    out.write(block)
                    h.update(block)
    if h.hexdigest() != manifest['sha256']:
        os.unlink(out_path)
        raise SystemExit('spanfs: checksum mismatch - a chunk is damaged')
    return out_path


def main():
    if '--version' in sys.argv:
        print(VERSION)
        return 0
    if len(sys.argv) >= 4 and sys.argv[1] == 'store':
        print('span dir:', store(sys.argv[2], sys.argv[3:]))
        return 0
    if len(sys.argv) >= 4 and sys.argv[1] == 'fetch':
        print('restored:', fetch(sys.argv[2], sys.argv[3], sys.argv[4:] or None))
        return 0
    print('usage: spanfs.py store <file> <drive>... | fetch <span-dir> <out> [drive...]')
    return 2


if __name__ == '__main__':
    sys.exit(main())
