# Security policy

## Reporting a vulnerability

Please report security issues privately to the repository owner. Do not open a
public issue containing credentials, API tokens, host addresses, private keys,
or exploitable details before a fix is available.

## Operational safety

- Run the builder only on a Proxmox VE node you administer.
- Review storage IDs, VMIDs and the bridge before execution.
- Existing non-template VMIDs are never deleted by the script.
- The interactive entrypoint never replaces existing templates. The internal
  engine supports explicit `--replace` or `REPLACE_EXISTING=1`; linked clones
  can still prevent safe deletion.
- The Agent helper never accepts or forwards replacement flags. Any occupied
  catalog VMID is a typed `VMID_CONFLICT` and stops bootstrap.
- The Agent helper accepts only bundled catalog `urlKey` values. It has no
  arbitrary URL or catalog-path option and pins both SHA-256 and the upstream
  checksum entry.
- `--execute` requires the UUIDs and catalog revision/SHA-256 returned by the
  confirmed plan.
- Never commit a configuration file containing passwords, API tokens or SSH
  private keys.
- Treat an internal engine `--config` file as executable shell. The interactive
  entrypoint does not load it, and Agent integration must not use that option.
- Root password SSH is enabled by the example profile for VPS provisioning.
  Set `ALLOW_ROOT_PASSWORD_SSH=0` when password login is not required.
