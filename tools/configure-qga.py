#!/usr/bin/env python3
"""Preserve distribution RPC restrictions while enabling PPFlight's required calls."""
from pathlib import Path
import re

REQUIRED = ('guest-exec', 'guest-exec-status', 'guest-set-user-password', 'guest-network-get-interfaces')


def rpc_list(value, allow):
    commands = [v for v in value.split(',') if v]
    if any(not re.fullmatch(r'guest-[a-z0-9-]+', c) for c in commands):
        raise ValueError('Unrecognized QGA RPC list')
    if allow:
        return ','.join(dict.fromkeys(commands + list(REQUIRED)))
    return ','.join(c for c in commands if c not in REQUIRED)


def environment(text):
    def update(match):
        key, quote, value = match[1], match[2], match[3]
        if key == 'BLACKLIST_RPC':
            value = rpc_list(value, False)
        else:
            value, count = re.subn(r'--(allow-rpcs|block-rpcs|blacklist)=([a-z0-9,-]*)',
                lambda m: '--'+m[1]+'='+rpc_list(m[2], m[1]=='allow-rpcs'), value)
            if value.strip() and count == 0:
                raise ValueError('Unrecognized QGA filter arguments')
        return key+'='+quote+value+quote
    return re.sub(r'^(FILTER_RPC_ARGS|BLACKLIST_RPC)=([\'"]?)([^\n]*?)\2[ \t]*$', update, text, flags=re.M)


def configuration(text):
    return re.sub(r'^([ \t]*)(allow-rpcs|block-rpcs|blacklist)[ \t]*=[ \t]*([a-z0-9,-]*)[ \t]*$',
        lambda m: m[1]+m[2]+' = '+rpc_list(m[3], m[2]=='allow-rpcs'), text, flags=re.M)


def main():
    for path, edit in ((Path('/etc/sysconfig/qemu-ga'), environment), (Path('/etc/qemu/qemu-ga.conf'), configuration)):
        if path.exists():
            original=path.read_text()
            changed=edit(original)
            if changed != original:
                path.write_text(changed)


if __name__ == '__main__':
    main()
