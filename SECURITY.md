# Security policy

## Reporting a vulnerability

Please report security issues privately to the repository owner. Do not open a
public issue containing credentials, API tokens, host addresses, private keys,
or exploitable details before a fix is available.

## Operational safety

- Run the builder only on a Proxmox VE node you administer.
- Review storage IDs, VMIDs and the bridge before execution.
- Existing non-template VMIDs are never deleted by the script.
- Existing templates are replaced only with `--replace` or
  `REPLACE_EXISTING=1`; linked clones can still prevent safe deletion.
- Never commit a configuration file containing passwords, API tokens or SSH
  private keys.
- Root password SSH is enabled by the example profile for VPS provisioning.
  Set `ALLOW_ROOT_PASSWORD_SSH=0` when password login is not required.
