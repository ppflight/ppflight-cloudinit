#!/usr/bin/env python3
"""Boot a disposable overlay with no uplink; require QGA and cloud-init completion."""
import argparse
import base64
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import tempfile
import time


def agent(path, command, arguments=None, timeout=5):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(timeout)
        sock.connect(str(path))
        request = {'execute': command, 'id': 1}
        if arguments is not None:
            request['arguments'] = arguments
        sock.sendall(json.dumps(request).encode()+b'\n')
        stream = sock.makefile('rb')
        while True:
            line = stream.readline(1024*1024)
            if not line:
                raise OSError('QGA closed connection')
            result = json.loads(line)
            if 'error' in result:
                raise RuntimeError('QGA rejected '+command+': '+str(result['error'].get('desc', ''))[:500])
            if 'return' in result:
                return result['return']


def verify(image, vendor, timeout=360):
    image = Path(image).resolve()
    if not image.is_file() or not Path(vendor).is_file():
        raise ValueError('Missing prepared image or vendor profile')
    virtual_size=json.loads(subprocess.check_output(['qemu-img','info','--output=json',str(image)],text=True))['virtual-size']
    # Keep Unix socket paths short. All build files are private and ephemeral.
    with tempfile.TemporaryDirectory(prefix='pf-boot-') as directory:
        root = Path(directory)
        (root/'meta-data').write_text('instance-id: ppflight-offline-validation\nlocal-hostname: ppflight-validation\n')
        (root/'user-data').write_text('#cloud-config\nusers: []\ndisable_root: true\nssh_pwauth: false\n')
        (root/'vendor-data').write_bytes(Path(vendor).read_bytes())
        (root/'network-config').write_text('version: 1\nconfig:\n  - type: physical\n    name: eth0\n    mac_address: "52:54:00:12:34:56"\n    subnets:\n      - type: static\n        address: 10.0.2.15/24\n        gateway: 10.0.2.2\n  - type: nameserver\n    address: [10.0.2.3]\n')
        subprocess.run(['genisoimage','-quiet','-output',str(root/'seed.iso'),'-volid','cidata','-joliet','-rock',
                        'user-data','meta-data','vendor-data','network-config'],cwd=root,check=True,timeout=30)
        subprocess.run(['qemu-img','create','-q','-f','qcow2','-F','qcow2','-b',str(image),str(root/'overlay.qcow2')],check=True,timeout=30)
        args=['qemu-system-x86_64','-enable-kvm','-cpu','host','-m','2048','-smp','2',
              '-display','none','-monitor','none','-qmp','unix:'+str(root/'qmp.sock')+',server=on,wait=off','-serial','file:'+str(root/'serial.log'),
              '-device','virtio-scsi-pci,id=scsi0',
              '-drive','file='+str(root/'overlay.qcow2')+',if=none,id=osdisk,format=qcow2',
              '-device','scsi-hd,drive=osdisk,bus=scsi0.0',
              '-drive','file='+str(root/'seed.iso')+',media=cdrom,readonly=on',
              '-device','virtio-net-pci,netdev=private,mac=52:54:00:12:34:56',
              '-netdev','user,id=private,restrict=on',
              '-device','virtio-serial','-chardev','socket,path='+str(root/'qga.sock')+',server=on,wait=off,id=qga',
              '-device','virtserialport,chardev=qga,name=org.qemu.guest_agent.0','-no-reboot']
        with (root/'qemu.log').open('w') as log:
            process=subprocess.Popen(args,stdout=log,stderr=log)
            deadline=time.monotonic()+timeout
            try:
                while time.monotonic()<deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Validation VM stopped before QGA became ready')
                    try:
                        agent(root/'qga.sock','guest-ping')
                        break
                    except (OSError, ValueError, RuntimeError):
                        time.sleep(2)
                else:
                    raise TimeoutError('QGA did not become ready')
                info=agent(root/'qga.sock','guest-info')
                enabled={c['name'] for c in info.get('supported_commands',[]) if c.get('enabled')}
                required={'guest-exec','guest-exec-status','guest-set-user-password','guest-network-get-interfaces'}
                if not required.issubset(enabled):
                    raise RuntimeError('Required QGA operations are disabled: '+','.join(sorted(required-enabled)))
                # All first-boot modules must complete with no package mirror access.
                script='''set -eu
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
if ! cloud-init status --wait --long; then
 ip -brief address
 ip route
 cat /etc/netplan/*.yaml 2>/dev/null || true
 networkctl --no-pager 2>/dev/null || true
 systemctl cat systemd-networkd-wait-online.service 2>/dev/null || true
 exit 1
fi
command -v qemu-ga
command -v sshd
command -v chronyd
command -v growpart
command -v curl
cat /var/lib/ppflight-template/build-info
if command -v getenforce >/dev/null; then
 test "$(getenforce)" = Enforcing
fi
for unit in apt-daily.timer apt-daily-upgrade.timer dnf-automatic.timer dnf-automatic-install.timer snapd.service snapd.socket; do
 if [ -e /usr/lib/systemd/system/$unit ] || [ -e /lib/systemd/system/$unit ]; then
  test "$(systemctl is-enabled "$unit" 2>/dev/null || true)" = masked
 fi
done
'''
                script += '\nroot_bytes=$(df -B1 --output=size / | tail -1)\ntest "$root_bytes" -ge '+str(virtual_size * 7 // 10)+'\n'
                execution=agent(root/'qga.sock','guest-exec',{'path':'/bin/sh','arg':['-c',script],'capture-output':True})
                while time.monotonic()<deadline:
                    result=agent(root/'qga.sock','guest-exec-status',{'pid':execution['pid']})
                    if result.get('exited'):
                        output=base64.b64decode(result.get('out-data','')).decode(errors='replace')
                        if result.get('exitcode') != 0:
                            raise RuntimeError('First-boot verification failed (exit '+str(result.get('exitcode'))+'): '+output[-7000:]+'\n'+base64.b64decode(result.get('err-data','')).decode(errors='replace')[-4000:])
                        return {'qga':'ready','cloudInit':'done','network':'isolated-no-uplink','output':output,'rootFilesystemExpanded':True}
                    time.sleep(2)
                raise TimeoutError('Cloud-init verification timed out')
            except BaseException:
                # Keep only diagnostic text, not another copy of guest disks.
                diagnostic=image.with_suffix('.boot-error.log')
                diagnostic.write_text((root/'qemu.log').read_text() + '\n' + (root/'serial.log').read_text(errors='replace')[-16000:])
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=10)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--image',required=True)
    p.add_argument('--vendor',required=True)
    args=p.parse_args()
    result=verify(args.image,args.vendor)
    Path(args.image).with_suffix('.boot.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Isolated boot passed: QGA ready; cloud-init completed; automatic updates disabled')


if __name__ == '__main__':
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt('Boot verification interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    main()
