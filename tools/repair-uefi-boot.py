#!/usr/bin/env python3
"""Repair project template Cloud-Init boot order; dry-run unless --apply."""
import argparse
import json
from pathlib import Path
import re
import socket
import subprocess

BOOT = 'order=scsi0;ide2'

def validate(config, status, name):
    if config.get('template') != 1 or config.get('name') != name:
        raise ValueError('Not the expected project template')
    if 'ppflight-cloudinit' not in re.split('[;,]', config.get('tags', '')):
        raise ValueError('Project ownership tag missing')
    if config.get('bios') != 'ovmf' or config.get('lock') or status.get('status') != 'stopped':
        raise ValueError('Template must be unlocked, stopped and OVMF')
    if config.get('boot') not in ('order=scsi0', BOOT):
        raise ValueError('Custom boot order requires manual review')
    if not re.fullmatch(r'[\w.-]+:vm-\d+-cloudinit,media=cdrom(?:,size=\w+)?', config.get('ide2', '')):
        raise ValueError('Expected IDE Cloud-Init volume missing')
    if not re.fullmatch('[a-fA-F0-9]{40,64}', config.get('digest', '')):
        raise ValueError('PVE configuration digest missing')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    node = socket.gethostname().split('.')[0]
    catalog = json.loads((Path(__file__).resolve().parents[1] / 'catalog/template-catalog.v1.json').read_text())
    def get(path):
        return json.loads(subprocess.check_output(['pvesh', 'get', path, '--output-format', 'json'], text=True))
    pending = []
    for item in catalog['items']:
        target = item['target']
        if target['firmware'] != 'ovmf':
            continue
        vmid = target['vmid']
        path = f'/nodes/{node}/qemu/{vmid}'
        config = get(path + '/config')
        validate(config, get(path + '/status/current'), item['templateRef'])
        pending.append((vmid, path, config, item['templateRef']))
    for vmid, path, before, name in pending:
        changed = before['boot'] != BOOT
        if args.apply and changed:
            current = get(path + '/config')
            validate(current, get(path + '/status/current'), name)
            if current['digest'] != before['digest']:
                raise RuntimeError('Configuration changed after preflight')
            subprocess.run(['pvesh', 'set', path + '/config', '--boot', BOOT, '--digest', before['digest']], check=True, capture_output=True, text=True)
            after = get(path + '/config')
            expected = {k: v for k, v in before.items() if k not in ('digest', 'boot')}
            actual = {k: v for k, v in after.items() if k not in ('digest', 'boot')}
            if after.get('boot') != BOOT or expected != actual:
                raise RuntimeError('Template configuration read-back mismatch')
        print(json.dumps({'vmid': vmid, 'boot': BOOT, 'applied': args.apply, 'changed': changed}), flush=True)

if __name__ == '__main__':
    main()
