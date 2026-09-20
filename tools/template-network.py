#!/usr/bin/env python3
"""Read-only PVE network discovery and template bridge/VLAN validation."""
import argparse
import ipaddress
import json
import re
import socket
import subprocess
import sys

NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$')


def enabled(value):
    return value in (True, 1, '1')


def clean(value):
    return re.sub(r'[\x00-\x1f\x7f|]', ' ', str(value)).strip()


def vlan_ranges(value):
    if not value:
        return []
    ranges = []
    for part in re.split(r'[\s,]+', str(value).strip()):
        match = re.fullmatch(r'([0-9]{1,4})(?:-([0-9]{1,4}))?', part)
        if not match:
            raise ValueError('无法识别网桥 VLAN 范围，请检查 PVE 网络配置')
        first, last = int(match[1]), int(match[2] or match[1])
        if not 1 <= first <= last <= 4094:
            raise ValueError('网桥 VLAN 范围无效')
        ranges.append((first, last))
    return ranges


def inventory(network, routes):
    default_devices = {r.get('dev') for r in routes if r.get('dst') == 'default'}
    bridges = []
    for row in network:
        name = row.get('iface', '')
        if row.get('type') != 'bridge' or not NAME.fullmatch(name):
            continue
        addresses = []
        for field in ('cidr', 'cidr6', 'address', 'address6'):
            if row.get(field):
                try:
                    address = ipaddress.ip_interface(str(row[field]))
                    if address.ip.is_unspecified:
                        continue
                except ValueError:
                    raise ValueError('网桥地址无法识别，不能可靠判断管理网络') from None
                if not any(str(address.ip) == a.split('/')[0] for a in addresses):
                    addresses.append(str(row[field]))
        gateway = row.get('gateway') or row.get('gateway6')
        management = bool(addresses or gateway or name in default_devices)
        aware = enabled(row.get('bridge_vlan_aware'))
        # PVE/Linux defaults to 2-4094 when a VLAN-aware bridge omits bridge-vids.
        allowed = str(row.get('bridge_vids') or '2-4094') if aware else ''
        if aware:
            vlan_ranges(allowed)
        ports = row.get('bridge_ports') or ''
        if isinstance(ports, list):
            ports = ' '.join(ports)
        active = enabled(row.get('active'))
        bridges.append({'name': name, 'active': active, 'ports': clean(ports) or '无上联',
                        'addresses': addresses, 'management': management,
                        'default_route': bool(gateway or name in default_devices),
                        'vlan_aware': aware, 'allowed_vlans': allowed,
                        'candidate': active and not management and bool(ports) and ports != 'none'})
    bridges.sort(key=lambda x: x['name'])
    candidates = [b['name'] for b in bridges if b['candidate']]
    return {'bridges': bridges, 'recommended': candidates[0] if len(candidates) == 1 else None}


def discover():
    node = socket.gethostname().split('.')[0]
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', node):
        raise ValueError('节点名无效')
    def read(args):
        result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout)
    network = read(['pvesh', 'get', '/nodes/' + node + '/network', '--output-format', 'json'])
    routes = read(['ip', '-j', '-4', 'route', 'show', 'default'])
    routes += read(['ip', '-j', '-6', 'route', 'show', 'default'])
    return inventory(network, routes)


def validate(data, bridge, vlan):
    row = next((b for b in data['bridges'] if b['name'] == bridge), None)
    if not row or not row['active']:
        raise ValueError('所选网桥不存在或未运行，请重新选择')
    if vlan not in ('', '0'):
        if not re.fullmatch(r'[1-9][0-9]{0,3}', vlan) or not 1 <= int(vlan) <= 4094:
            raise ValueError('VLAN 必须为 1–4094，或填 0 不打标签')
        if not row['vlan_aware']:
            raise ValueError('所选网桥未启用 VLAN-aware，不能直接添加 VLAN 标签')
        if not any(a <= int(vlan) <= b for a, b in vlan_ranges(row['allowed_vlans'])):
            raise ValueError('该 VLAN 不在网桥允许范围内')
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['discover', 'menu', 'select', 'validate'])
    parser.add_argument('--bridge', default='')
    parser.add_argument('--vlan', default='')
    parser.add_argument('--index', default='')
    args = parser.parse_args()
    data = discover() if args.action in ('discover', 'validate') else json.load(sys.stdin)
    if args.action == 'discover':
        print(json.dumps(data, ensure_ascii=False))
    elif args.action == 'menu':
        if not any(row['active'] for row in data['bridges']):
            raise ValueError('没有已运行的 Linux 网桥，请先在 PVE 配置业务网桥')
        for i, row in enumerate(data['bridges'], 1):
            role = '管理网络风险：宿主地址或默认路由' if row['management'] else '业务候选（需核对接线）'
            if not row['candidate'] and not row['management']:
                role = '未识别用途，需人工核对'
            print(f"  {i}) {row['name']}{'（回车推荐）' if row['name'] == data['recommended'] else ''} [{'在线' if row['active'] else '离线，不可选'}] {role}")
            print(f"     上联：{row['ports']}；宿主地址：{', '.join(row['addresses']) or '无'}；VLAN：{row['allowed_vlans'] or '未开启 VLAN-aware'}")
    elif args.action == 'select':
        rows = data['bridges']
        if args.index == '' and data['recommended']:
            row = next(r for r in rows if r['name'] == data['recommended'])
        elif re.fullmatch(r'[1-9][0-9]{0,3}', args.index) and int(args.index) <= len(rows):
            row = rows[int(args.index)-1]
        else:
            raise ValueError('请输入有效网桥序号；存在多个候选时必须明确选择')
        validate(data, row['name'], '')
        ranges = vlan_ranges(row['allowed_vlans'])
        default_vlan = str(ranges[0][0]) if len(ranges) == 1 and ranges[0][0] == ranges[0][1] else '0'
        print('|'.join([row['name'], str(int(row['management'])), str(int(row['vlan_aware'])), row['allowed_vlans'] or '-', default_vlan]))
    else:
        validate(data, args.bridge, args.vlan)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print('网络检查失败：' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
