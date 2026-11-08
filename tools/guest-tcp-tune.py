#!/usr/bin/env python3
"""First-instance TCP baseline; no control-panel input or network downloads."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

MIB = 1024 * 1024
REFERENCE_MBPS = 300
REFERENCE_RTT_MS = 200
CONFIG = Path('/etc/sysctl.d/zz-ppflight-tcp.conf')
REPORT = Path('/var/lib/ppflight-template/tcp-tuning.json')


def memory_bytes(text):
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == 'MemTotal:':
            if len(parts) != 3 or parts[2] != 'kB' or int(parts[1]) <= 0:
                raise ValueError('Invalid MemTotal')
            return int(parts[1]) * 1024
    raise ValueError('MemTotal unavailable; refusing guessed memory')


def calculate(memory):
    if memory < 64 * MIB:
        raise ValueError('Insufficient memory for this template')
    bdp = REFERENCE_MBPS * 1000000 // 8 * REFERENCE_RTT_MS // 1000
    # A buffer ceiling is not a reservation. Enforce the RAM cap AFTER the
    # 16 MiB reference floor, including on small-memory clones.
    ceiling = min(max(bdp * 18 // 10, 16 * MIB), memory * 4 // 100, 256 * MIB)
    return {
        'net.core.default_qdisc': 'fq',
        'net.ipv4.tcp_congestion_control': 'bbr',
        'net.core.rmem_max': str(ceiling),
        'net.core.wmem_max': str(ceiling),
        'net.ipv4.tcp_rmem': '4096 131072 ' + str(ceiling),
        'net.ipv4.tcp_wmem': '4096 16384 ' + str(ceiling),
        'net.ipv4.tcp_moderate_rcvbuf': '1',
    }


def render(values):
    return ('# PPFlight TCP baseline: detected guest RAM, 300 Mbps / 200 ms reference.\n'
            '# Reference bandwidth is NOT a rate limit. Global TCP memory stays kernel-managed.\n'
            + ''.join(key + '=' + value + '\n' for key, value in sorted(values.items())))


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=str(path.parent), delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(0o644)
            os.replace(str(temporary), str(path))
        finally:
            if temporary.exists():
                temporary.unlink()


def apply():
    if os.geteuid() != 0 or Path('/etc/ppflight-offline-build').exists():
        raise RuntimeError('Run only as root in the booted guest, not during offline preparation')
    memory = memory_bytes(Path('/proc/meminfo').read_text())
    values = calculate(memory)
    available = Path('/proc/sys/net/ipv4/tcp_available_congestion_control')
    if 'bbr' not in available.read_text().split():
        subprocess.run(['modprobe', 'tcp_bbr'], check=True, timeout=30)
    if 'bbr' not in available.read_text().split():
        raise RuntimeError('This kernel does not support native BBR')
    for key in values:
        if not (Path('/proc/sys') / key.replace('.', '/')).is_file():
            raise RuntimeError('Required kernel setting unavailable: ' + key)
    atomic_write(CONFIG, render(values))
    subprocess.run(['sysctl', '-p', str(CONFIG)], check=True, timeout=30)
    for key, expected in values.items():
        actual = (Path('/proc/sys') / key.replace('.', '/')).read_text()
        if actual.split() != expected.split():
            raise RuntimeError('Kernel did not apply ' + key)
    atomic_write(Path('/etc/modules-load.d/ppflight-tcp-bbr.conf'), 'tcp_bbr\n')
    report = {'version': 1, 'memoryBytes': memory, 'referenceMbps': REFERENCE_MBPS,
              'referenceRttMs': REFERENCE_RTT_MS, 'settings': values,
              'rateLimitChanged': False, 'swapChanged': False}
    atomic_write(REPORT, json.dumps(report, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.dry_run:
        print(render(calculate(memory_bytes(Path('/proc/meminfo').read_text()))), end='')
    else:
        apply()
