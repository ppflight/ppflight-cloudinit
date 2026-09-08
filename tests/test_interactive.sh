#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../build-cloud-templates.sh"
TEMPLATE_ROWS=('9000|ubuntu-2204|image' '9001|ubuntu-2404|image')
choose_templates <<< 'ALL'
[[ "$ONLY_TEMPLATES" == all ]]
choose_templates <<< ''
[[ "$ONLY_TEMPLATES" == all ]]
confirm_install <<< ''
confirm_install <<< $'invalid\nYES'
if confirm_install <<< no; then exit 1; fi
choose_templates <<< $'bad\n9001,9000,9001'
[[ "$ONLY_TEMPLATES" == 9001,9000 ]]
if (choose_templates </dev/null); then exit 1; fi
STORAGE_DISCOVERY='{"state":"succeeded","storages":[
{"storageId":"offline","type":"dir","enabled":true,"active":false,"availableBytesKnown":true,"availableBytes":"100","roleEligibility":{"image":{"allowed":false},"template":{"allowed":false},"backup":{"allowed":false}}},
{"storageId":"downloads","type":"dir","enabled":true,"active":true,"availableBytesKnown":true,"availableBytes":"1024","roleEligibility":{"image":{"allowed":true},"template":{"allowed":false},"backup":{"allowed":false}}},
{"storageId":"vm-pool","type":"zfspool","enabled":true,"active":true,"availableBytesKnown":true,"availableBytes":"2048","roleEligibility":{"image":{"allowed":false},"template":{"allowed":true},"backup":{"allowed":false}}},
{"storageId":"backups","type":"pbs","enabled":true,"active":true,"availableBytesKnown":false,"availableBytes":"0","roleEligibility":{"image":{"allowed":false},"template":{"allowed":false},"backup":{"allowed":true}}}]}'
choose_storage image images FILE_STORAGE <<< $'999\n0\n1'
choose_storage template install IMAGE_STORAGE <<< ''
choose_storage backup backup BACKUP_STORAGE <<< 1
[[ "$FILE_STORAGE" == downloads && "$IMAGE_STORAGE" == vm-pool && "$BACKUP_STORAGE" == backups ]]
STORAGE_DISCOVERY='{"state":"succeeded","storages":[]}'
if (choose_storage image images FILE_STORAGE <<< 1); then exit 1; fi
printf 'Interactive menu tests passed.\n'
