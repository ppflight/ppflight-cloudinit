#!/usr/bin/env python3
"""Publish a customer-backup destination in PVE node notes; never run a backup."""
import argparse
import json
import re
import socket
import subprocess
import sys

MARKER = 'PPFLIGHT_CUSTOMER_BACKUP_V1='
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')


def parse(notes):
    if not isinstance(notes, str):
        return {'state': 'invalid', 'storage_id': None}
    lines = [line for line in notes.splitlines() if line.startswith(MARKER)]
    if not lines:
        return {'state': 'absent', 'storage_id': None}
    if len(lines) != 1:
        return {'state': 'invalid', 'storage_id': None}
    value = lines[0][len(MARKER):]
    if value == '-':
        return {'state': 'unset', 'storage_id': None}
    if ID.fullmatch(value):
        return {'state': 'configured', 'storage_id': value}
    return {'state': 'invalid', 'storage_id': None}


def merge(notes, storage):
    if parse(notes)['state'] == 'invalid':
        raise ValueError('Node backup marker is malformed or duplicated; repair node notes first')
    if storage != '-' and not ID.fullmatch(storage):
        raise ValueError('Invalid customer backup storage ID')
    line = MARKER + storage
    if parse(notes)['state'] != 'absent':
        return ''.join(line + ('\n' if old.endswith('\n') else '') if old.rstrip('\r\n').startswith(MARKER) else old
                       for old in notes.splitlines(keepends=True))
    return notes + ('\n' if notes and not notes.endswith('\n') else '') + line + '\n'


def read(args):
    return json.loads(subprocess.run(['pvesh', 'get', *args, '--output-format', 'json'],
                                    check=True, capture_output=True, text=True, timeout=30).stdout)


def save(node, storage):
    # Validate fresh node-local storage evidence, not stale menu data.
    if storage != '-':
        if not ID.fullmatch(storage):
            raise ValueError('Invalid customer backup storage ID')
        rows = read([f'/nodes/{node}/storage'])
        found = [s for s in rows if s.get('storage') == storage] if isinstance(rows, list) else []
        if len(found) != 1 or found[0].get('active') not in (True, 1, '1') or found[0].get('enabled') not in (True, 1, '1') or 'backup' not in found[0].get('content', '').split(','):
            raise ValueError('Customer backup storage must be active, enabled and support backup on this node')
    path = f'/nodes/{node}/config'
    config = read([path])
    digest = config.get('digest', '')
    if not re.fullmatch(r'[0-9a-f]{40,64}', digest):
        raise ValueError('PVE configuration digest missing; no settings changed')
    description = merge(config.get('description', ''), storage)
    subprocess.run(['pvesh', 'set', path, '--description', description, '--digest', digest],
                   check=True, capture_output=True, text=True, timeout=30)
    result = parse(read([path]).get('description', ''))
    expected = {'state': 'unset', 'storage_id': None} if storage == '-' else {'state': 'configured', 'storage_id': storage}
    if result != expected:
        raise ValueError('Customer backup setting readback did not match')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['show', 'set'])
    parser.add_argument('--storage', default='-')
    args = parser.parse_args()
    node = socket.gethostname().split('.')[0]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', node):
        raise ValueError('Invalid node name')
    result = parse(read([f'/nodes/{node}/config']).get('description', '')) if args.action == 'show' else save(node, args.storage)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print('Customer backup configuration failed: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
