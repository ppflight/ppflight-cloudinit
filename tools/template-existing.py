#!/usr/bin/env python3
"""Fail-closed, read-only checks before replacing a managed ZFS template."""
import argparse
import json
import re
import socket
import subprocess
import sys


def read(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


def locate(rows, vmid, node):
    if not isinstance(rows, list) or any(not isinstance(r, dict) or 'vmid' not in r for r in rows):
        raise ValueError('Cannot verify cluster VMID inventory')
    found = [r for r in rows if str(r['vmid']) == str(vmid)]
    if not found:
        return 'missing'
    if len(found) != 1 or found[0].get('node') != node or found[0].get('type') != 'qemu':
        raise ValueError(f'VMID {vmid} belongs to another node or a container')
    if found[0].get('template') not in (True, 1, '1'):
        raise ValueError(f'VMID {vmid} is a regular VM, not a template')
    return 'present'


def managed(config, expected_name, expected_digest=None):
    if not isinstance(config, dict) or config.get('template') not in (True, 1, '1'):
        raise ValueError('Not a template')
    if config.get('lock') or config.get('name') != expected_name:
        raise ValueError('Template is locked or its name does not match')
    if 'ppflight-cloudinit' not in re.split('[;,]', str(config.get('tags', ''))):
        raise ValueError('Template is not managed by ppflight-cloudinit')
    digest = config.get('digest', '')
    if not re.fullmatch('[0-9a-f]{40,64}', digest):
        raise ValueError('Missing PVE configuration digest')
    if expected_digest and expected_digest != digest:
        raise ValueError('Template changed after preflight; refusing replacement')
    return digest


def validate_clones(output):
    for line in output.splitlines():
        fields = line.split('\t')
        if len(fields) != 2 or fields[1] != '-':
            raise ValueError('Template has linked clones or unrecognized ZFS snapshot state')


def replace_check(vmid, name, node, expected_digest=None):
    config = json.loads(read(['pvesh', 'get', f'/nodes/{node}/qemu/{vmid}/config', '--output-format', 'json']))
    digest = managed(config, name, expected_digest)
    status = json.loads(read(['pvesh', 'get', f'/nodes/{node}/qemu/{vmid}/status/current', '--output-format', 'json']))
    if status.get('status') != 'stopped':
        raise ValueError('Template must be stopped')
    volumes = []
    for key, value in config.items():
        if re.fullmatch(r'(?:scsi|virtio|sata|ide|unused|efidisk|tpmstate)\d+', key):
            volume = str(value).split(',')[0]
            if volume != 'none':
                volumes.append(volume)
    if not volumes:
        raise ValueError('No template disks found')
    for volume in volumes:
        match = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9._-]*):((?:base|vm)-' + str(vmid) + r'-(?:disk-\d+|cloudinit))', volume)
        if not match:
            raise ValueError('Unrecognized template disk; automatic replacement is not safe')
        storage = json.loads(read(['pvesh', 'get', '/storage/' + match[1], '--output-format', 'json']))
        if storage.get('type') != 'zfspool' or storage.get('shared') not in (None, 0, False, '0'):
            raise ValueError('Automatic replacement currently requires local ZFS storage; preserve this template')
        pool = storage.get('pool', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]*', pool) or '..' in pool.split('/'):
            raise ValueError('Invalid ZFS dataset')
        dataset = pool + '/' + match[2]
        if read(['zfs', 'list', '-H', '-o', 'type', dataset]) != 'volume':
            raise ValueError('Template ZFS volume missing')
        validate_clones(read(['zfs', 'list', '-H', '-t', 'snapshot', '-o', 'name,clones', '-r', dataset]))
    # Detect direct references, including unused disks and snapshots, across the cluster.
    from pathlib import Path
    for path in Path('/etc/pve/nodes').glob('*/qemu-server/*.conf'):
        if path.parent.parent.name == node and path.stem == str(vmid):
            continue
        text = path.read_text()
        for volume in volumes:
            if re.search(r'(?<![\w:./-])' + re.escape(volume) + r'(?=[,\s]|$)', text):
                raise ValueError('Another VM references this template disk')
    return digest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['locate', 'replace-check'])
    p.add_argument('--vmid', type=int, required=True)
    p.add_argument('--name')
    p.add_argument('--expected-digest')
    args = p.parse_args()
    node = socket.gethostname().split('.')[0]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', node) or not 100 <= args.vmid < 1000000000:
        raise ValueError('Invalid node or VMID')
    if args.action == 'locate':
        print(locate(json.load(sys.stdin), args.vmid, node))
    else:
        print(replace_check(args.vmid, args.name, node, args.expected_digest))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError) as error:
        print('Template check failed: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
