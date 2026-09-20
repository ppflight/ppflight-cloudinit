#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=build-cloud-templates.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../build-cloud-templates.sh"
fixture_dir="$(mktemp -d)"
trap 'rm -rf -- "$fixture_dir"' EXIT
mkdir "$fixture_dir/bin"
export PPFLIGHT_NETWORK_FIXTURE="$fixture_dir/network.json"
cat > "$PPFLIGHT_NETWORK_FIXTURE" <<'JSON'
[{"iface":"vmbr0","type":"bridge","active":1,"address":"10.0.0.33","gateway":"10.0.0.1","bridge_ports":"nic0"},{"iface":"vmbr1","type":"bridge","active":1,"bridge_ports":"bond0","bridge_vlan_aware":1,"bridge_vids":"2100"}]
JSON
cat > "$fixture_dir/bin/pvesh" <<'EOF'
#!/bin/bash
cat "$PPFLIGHT_NETWORK_FIXTURE"
EOF
cat > "$fixture_dir/bin/ip" <<'EOF'
#!/bin/bash
printf '[{"dst":"default","dev":"vmbr0"}]\n'
EOF
chmod +x "$fixture_dir/bin/"*
export PATH="$fixture_dir/bin:$PATH"
choose_network <<< $'\n'
[[ "$BRIDGE" == vmbr1 && "$VLAN_TAG" == 2100 ]]
[[ "$(template_net0)" == 'virtio,bridge=vmbr1,firewall=1,tag=2100' ]]
choose_network <<< $'99\n2\n2102\n2100'
[[ "$BRIDGE" == vmbr1 && "$VLAN_TAG" == 2100 ]]
choose_network <<< $'1\nno\n2\n0'
[[ "$BRIDGE" == vmbr1 && -z "$VLAN_TAG" ]]
[[ "$(template_net0)" == 'virtio,bridge=vmbr1,firewall=1' ]]
choose_network <<< $'1\nUSE'
[[ "$BRIDGE" == vmbr0 && -z "$VLAN_TAG" ]]
if (choose_network </dev/null); then printf 'EOF was accepted\n';exit 1;fi
printf '[]' > "$PPFLIGHT_NETWORK_FIXTURE"
if (choose_network <<< ''); then printf 'No bridges accepted\n';exit 1;fi
BRIDGE=vmbr1
VLAN_TAG=2100
verify_template_network 'net0: virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr1,firewall=1,tag=2100'
if (verify_template_network 'net0: virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr0,firewall=1,tag=2100'); then exit 1;fi
if (verify_template_network 'net0: virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr1,firewall=1,tag=2102'); then exit 1;fi
VLAN_TAG=''
verify_template_network 'net0: virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr1,firewall=1'
if (verify_template_network 'net0: virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr1,firewall=1,tag=2100'); then exit 1;fi
printf 'Business bridge/VLAN interactive tests passed.\n' 
