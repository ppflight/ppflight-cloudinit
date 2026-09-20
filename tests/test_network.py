import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('network', ROOT / 'tools/template-network.py')
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)


class NetworkTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {'iface': 'vmbr0', 'type': 'bridge', 'active': 1, 'cidr': '10.0.0.33/24', 'address': '10.0.0.33', 'bridge_ports': 'nic0'},
            {'iface': 'vmbr1', 'type': 'bridge', 'active': 1, 'bridge_ports': 'bond0', 'bridge_vlan_aware': 1, 'bridge_vids': '2100'},
            {'iface': 'vmbr2', 'type': 'bridge', 'active': 0, 'bridge_ports': 'nic3'},
            {'iface': 'nic0', 'type': 'eth', 'active': 1},
        ]
        self.routes = [{'dst': 'default', 'dev': 'vmbr0'}]
        self.data = network.inventory(self.rows, self.routes)

    def test_recommends_business_bridge_without_treating_bond_as_bridge(self):
        self.assertEqual(self.data['recommended'], 'vmbr1')
        self.assertEqual(len(self.data['bridges']), 3)
        self.assertTrue(self.data['bridges'][0]['management'])
        self.assertEqual(self.data['bridges'][0]['addresses'], ['10.0.0.33/24'])
        self.assertEqual(network.validate(self.data, 'vmbr1', '2100')['ports'], 'bond0')

    def test_rejects_wrong_vlan_inactive_non_bridge_and_injection(self):
        for bridge, vlan in [('vmbr1', '2102'), ('vmbr0', '2100'), ('vmbr2', ''), ('nic0', ''),
                             ('vmbr1', '4095'), ('vmbr1', '-1'), ('vmbr1', '2,firewall=0'), ('vmbr1', '02100')]:
            with self.subTest(bridge=bridge, vlan=vlan), self.assertRaises(ValueError):
                network.validate(self.data, bridge, vlan)
        network.validate(self.data, 'vmbr0', '0')
        network.validate(self.data, 'vmbr1', '')

    def test_multiple_business_bridges_have_no_automatic_default(self):
        self.rows[2]['active'] = 1
        self.assertIsNone(network.inventory(self.rows, self.routes)['recommended'])

    def test_ipv6_address_or_default_route_marks_management_risk(self):
        for extra in [{'address6': '2001:db8::1'}, {'gateway6': 'fe80::1'}]:
            self.rows[1].update(extra)
            data = network.inventory(self.rows, [])
            self.assertIsNone(data['recommended'])
            self.assertTrue(data['bridges'][1]['management'])
        self.rows[1].pop('gateway6');self.rows[1].pop('address6')
        self.assertIsNone(network.inventory(self.rows, [{'dst': 'default', 'dev': 'vmbr1'}])['recommended'])

    def test_vlan_ranges_and_safe_terminal_output(self):
        self.rows[1]['bridge_vids'] = '100-200 2100,3000-3100'
        self.rows[1]['bridge_ports'] = 'bond0\x1b[31m|unsafe'
        data = network.inventory(self.rows, self.routes)
        network.validate(data, 'vmbr1', '2100')
        network.validate(data, 'vmbr1', '150')
        with self.assertRaises(ValueError):network.validate(data, 'vmbr1', '201')
        self.assertNotIn('\x1b', data['bridges'][1]['ports'])
        self.assertNotIn('|', data['bridges'][1]['ports'])
        for value in ['4095', '200-100', 'all', '2100;echo']:
            with self.assertRaises(ValueError):network.vlan_ranges(value)

    def test_absent_vlan_range_has_pve_default(self):
        self.rows[1].pop('bridge_vids')
        data = network.inventory(self.rows, self.routes)
        network.validate(data, 'vmbr1', '2100')
        with self.assertRaises(ValueError):network.validate(data, 'vmbr1', '1')
