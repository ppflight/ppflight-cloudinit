#!/usr/bin/env python3
"""Build an updated, independent qcow2; never modify the pinned source image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def run(args, capture=False, timeout=7200):
    env = dict(os.environ, LIBGUESTFS_BACKEND='direct')
    result = subprocess.run(args, check=True, env=env, timeout=timeout,
                            stdout=subprocess.PIPE if capture else sys.stderr,
                            stderr=sys.stderr, text=True)
    return (result.stdout or '').strip()


def root_partition(output):
    roots = []
    for line in output.splitlines():
        if ': ' in line:
            device, mount = line.split(': ', 1)
            if mount == '/':
                roots.append(device)
    if len(roots) != 1 or not re.fullmatch(r'/dev/[sv]da[1-9][0-9]*', roots[0]):
        raise ValueError('Root layout is not a supported plain partition; original template preserved')
    return roots[0]


def size_bytes(size):
    m = re.fullmatch(r'([1-9][0-9]*)([KMGT])', size)
    if not m:
        raise ValueError('Invalid disk size')
    return int(m[1]) * 1024 ** ('KMGT'.index(m[2]) + 1)


def prepare(source, target, size, profile):
    source, target, profile = Path(source), Path(target), Path(profile)
    if not source.is_file() or source.is_symlink() or not profile.is_file():
        raise ValueError('Missing or unsafe build input')
    if target.exists() or source.resolve() == target.resolve():
        raise ValueError('Prepared image must be a new independent file')
    info = json.loads(run(['qemu-img', 'info', '--output=json', str(source)], True, 60))
    if info.get('format') != 'qcow2' or info.get('backing-filename'):
        raise ValueError('Official source must be a standalone qcow2')
    virtual_size = size_bytes(size)
    if virtual_size <= info['virtual-size']:
        raise ValueError('DISK_SIZE must be larger than the official source disk for offline preparation')
    if shutil.disk_usage(target.parent).free < virtual_size + 2 * 1024**3:
        raise ValueError('Insufficient preparation space; free DISK_SIZE plus 2 GiB before rebuilding')
    root = root_partition(run(['guestfish', '--ro', '--format=qcow2', '-a', str(source), '-i', 'mountpoints'], True))
    root_uuid = run(['guestfish', '--ro', '--format=qcow2', '-a', str(source), '-i', 'vfs-uuid', root], True)
    if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', root_uuid):
        raise ValueError('Cannot determine the guest root filesystem UUID')
    try:
        run(['qemu-img', 'create', '-f', 'qcow2', str(target), size], timeout=60)
        run(['virt-resize', '--format', 'qcow2', '--output-format', 'qcow2', '--expand', root, str(source), str(target)])
        run(['virt-customize', '--format', 'qcow2', '-a', str(target), '--network', '--memsize', '2048', '--smp', '2',
             '--write', '/etc/ppflight-offline-build:' + root_uuid,
             '--upload', str(profile.with_name('configure-qga.py')) + ':/var/tmp/ppflight-configure-qga.py',
             '--upload', str(profile) + ':/var/tmp/ppflight-prepare-guest.sh',
             '--run-command', 'bash /var/tmp/ppflight-prepare-guest.sh', '--delete', '/var/tmp/ppflight-prepare-guest.sh', '--delete', '/var/tmp/ppflight-configure-qga.py', '--no-selinux-relabel', '--no-logfile'])
        report = run(['guestfish', '--ro', '--format=qcow2', '-a', str(target), '-i', 'cat', '/var/lib/ppflight-template/build-info'], True)
        if 'automatic_upgrades=disabled' not in report or 'updated_at_utc=' not in report:
            raise ValueError('Guest preparation did not produce a complete report')
        packages = run(['guestfish', '--ro', '--format=qcow2', '-a', str(target), '-i', 'cat', '/var/lib/ppflight-template/packages.tsv'], True)
        if not packages or 'qemu-guest-agent' not in packages or 'cloud-init' not in packages:
            raise ValueError('Package inventory is incomplete')
        run(['qemu-img', 'check', '-f', 'qcow2', str(target)], timeout=300)
        digest = file_hash(target)
        target.with_suffix('.json').write_text(json.dumps({'preparedSha256': digest, 'guestReport': report, 'packages': packages.splitlines()}, indent=2) + '\n')
        print(digest)
    except BaseException:
        target.unlink(missing_ok=True)
        target.with_suffix('.json').unlink(missing_ok=True)
        raise


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--target', required=True)
    p.add_argument('--size', required=True)
    args = p.parse_args()
    prepare(args.source, args.target, args.size, Path(__file__).with_name('prepare-guest.sh'))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        print('Offline preparation failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
