# Official Image Review: 2026-11-08

Reviewed at 15:57 UTC. Keep the existing distribution branches and firmware
options; select the latest dated, released GenericCloud image visible in each
official index. Daily/development builds and LVM/EC2 variants are not substituted.
The builder uses these reviewed pins, not a moving alias during execution.

| Branch | Selected release | Official index |
| --- | --- | --- |
| Ubuntu 22.04 | 20261106 | https://cloud-images.ubuntu.com/releases/jammy/ |
| Ubuntu 24.04, including Legacy | 20261017 | https://cloud-images.ubuntu.com/releases/noble/ |
| Ubuntu 26.04 | 20261016 | https://cloud-images.ubuntu.com/releases/resolute/ |
| Debian 12, including Legacy | 20261026-2643 | https://cloud.debian.org/images/cloud/bookworm/ |
| Debian 13 | 20261103-2651 | https://cloud.debian.org/images/cloud/trixie/ |
| AlmaLinux 8 | 8.10-20261026 | https://repo.almalinux.org/almalinux/8/cloud/x86_64/images/ |
| AlmaLinux 9 | 9.8-20261102 | https://repo.almalinux.org/almalinux/9/cloud/x86_64/images/ |
| Rocky Linux 9 | 9.8-20260525.0 | https://download.rockylinux.org/pub/rocky/9/images/x86_64/ |
| CentOS Stream 9 | 20261103.0 | https://cloud.centos.org/centos/9-stream/x86_64/images/ |
| CentOS Stream 10 | 20261103.0 | https://cloud.centos.org/centos/10-stream/x86_64/images/ |

The Rocky GenericCloud-Base latest alias checksum matches the selected dated
image. An older date is not replaced with an unrelated image variant merely to
obtain a newer filename.

All ten distinct sources have QCOW2 headers with virtual capacity at or below
10 GiB. Official checksums, actual image byte lengths and source URLs are
recorded in `catalog/template-catalog.v1.json` and `URL_SPECS` in
`tools/ppflight-template-bootstrap.py`. Debian sources were streamed in full,
verified against official SHA512SUMS, and independently hashed with SHA256.
The builder revalidates the complete downloads on every node before preparing
images, then installs current updates from the distribution's official repos.

This review establishes source selection and integrity, not a claim that a
particular PVE deployment has completed. Actual package inventories, prepared
image hashes and both boot reports are produced during the build.
