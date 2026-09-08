import argparse
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "ppflight-template-bootstrap.py"
SPEC = importlib.util.spec_from_file_location("ppflight_template_bootstrap", HELPER)
assert SPEC and SPEC.loader
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class FakeRunner:
    def __init__(
        self,
        configs=None,
        statuses=None,
        resources=None,
        bridge_ok=True,
        unsupported_path_content=None,
        template_volumes=None,
    ):
        self.configs = configs or []
        self.statuses = statuses or []
        self.resources = resources or []
        self.bridge_ok = bridge_ok
        self.unsupported_path_content = unsupported_path_content
        self.template_volumes = template_volumes or {}
        self.calls = []

    def json(self, argv, timeout=120):
        self.calls.append(tuple(argv))
        if tuple(argv[:3]) == ("pvesh", "get", "/storage"):
            return copy.deepcopy(self.configs)
        if tuple(argv[:2]) == ("pvesh", "get") and argv[2].startswith("/nodes/") and argv[2].endswith("/storage"):
            return copy.deepcopy(self.statuses)
        if tuple(argv[:3]) == ("pvesh", "get", "/cluster/resources"):
            return copy.deepcopy(self.resources)
        raise AssertionError(f"unexpected JSON command: {argv}")

    def run(self, argv, check=True, timeout=120):
        self.calls.append(tuple(argv))
        if tuple(argv[:2]) == ("pvesm", "path"):
            content_type, probe_name = argv[2].split(":", 1)[1].split("/", 1)
            if content_type == self.unsupported_path_content:
                return SimpleNamespace(returncode=1, stdout="", stderr="unsupported")
            return SimpleNamespace(
                returncode=0,
                stdout=f"/var/lib/vz/template/{content_type}/{probe_name}\n",
                stderr="",
            )
        if tuple(argv[:4]) == ("ip", "link", "show", "dev"):
            return SimpleNamespace(returncode=0 if self.bridge_ok else 1, stdout="", stderr="")
        if tuple(argv[:2]) == ("qm", "config"):
            vmid = int(argv[2])
            volume = self.template_volumes.get(vmid)
            if volume is None:
                return SimpleNamespace(returncode=1, stdout="", stderr="missing")
            return SimpleNamespace(
                returncode=0,
                stdout=f"template: 1\ntags: ppflight-cloudinit\nscsi0: {volume},discard=on\n",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {argv}")


def good_inventory():
    configs = [
        {"storage": "download-local", "type": "dir", "content": "iso,snippets", "shared": 0},
        {"storage": "raid-zfs", "type": "zfspool", "content": "images,rootdir", "shared": 0},
        {"storage": "pbs-backup", "type": "pbs", "content": "backup", "shared": 1},
    ]
    statuses = [
        {"storage": "download-local", "status": "active", "avail": 50_000_000_000},
        {"storage": "raid-zfs", "status": "active", "avail": 50_000_000_000},
        {"storage": "pbs-backup", "status": "active", "avail": 50_000_000_000, "shared": 1},
    ]
    return configs, statuses


def plan_args(**overrides):
    values = {
        "image_storage": "download-local",
        "template_storage": "raid-zfs",
        "backup_policy": "required",
        "backup_storage": "pbs-backup",
        "items": "all",
        "bridge": "vmbr0",
        "request_id": "11111111-1111-4111-8111-111111111111",
        "operation_id": "22222222-2222-4222-8222-222222222222",
        "expected_catalog_revision": None,
        "expected_catalog_sha256": None,
        "execute": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class CatalogTests(unittest.TestCase):
    def test_bundled_catalog_is_strict_and_complete(self):
        catalog = bootstrap.load_catalog()
        self.assertEqual(catalog["schemaVersion"], bootstrap.CATALOG_SCHEMA)
        self.assertEqual(catalog["websitePath"], "/vps/proxmox-templates")
        self.assertEqual(len(catalog["items"]), 7)
        self.assertEqual(len(catalog["_catalogSha256"]), 64)
        for item in catalog["items"]:
            self.assertEqual(item["architecture"], "amd64")
            self.assertEqual(item["guestType"], "qemu")
            self.assertEqual(len(item["source"]["sha256"]), 64)

    def test_unknown_url_key_is_rejected(self):
        catalog = bootstrap.catalog_without_internal_fields(bootstrap.load_catalog())
        catalog["items"][0]["source"]["urlKey"] = "attacker-controlled"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaises(bootstrap.ContractError) as caught:
                bootstrap.load_catalog(path)
        self.assertEqual(caught.exception.code, "CATALOG_URL_KEY_UNKNOWN")

    def test_alias_cannot_collide_with_a_vmid_selector(self):
        catalog = bootstrap.catalog_without_internal_fields(bootstrap.load_catalog())
        catalog["items"][0]["aliases"].append("9000")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaises(bootstrap.ContractError) as caught:
                bootstrap.load_catalog(path)
        self.assertEqual(caught.exception.code, "CATALOG_SELECTOR_DUPLICATE")

    def test_catalog_version_must_match_the_schema(self):
        catalog = bootstrap.catalog_without_internal_fields(bootstrap.load_catalog())
        catalog["items"][0]["version"] = "not a version"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog), encoding="utf-8")
            with self.assertRaises(bootstrap.ContractError) as caught:
                bootstrap.load_catalog(path)
        self.assertEqual(caught.exception.code, "CATALOG_VERSION_INVALID")

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text('{"schemaVersion":"a","schemaVersion":"b"}', encoding="utf-8")
            with self.assertRaises(bootstrap.ContractError) as caught:
                bootstrap.load_catalog(path)
        self.assertEqual(caught.exception.code, "CATALOG_DUPLICATE_KEY")

    def test_catalog_rows_resolve_only_builtin_https_sources(self):
        rows = bootstrap.catalog_rows(bootstrap.load_catalog())
        self.assertEqual(len(rows), 7)
        for row in rows:
            fields = row.split("|")
            self.assertEqual(len(fields), 14)
            self.assertTrue(fields[3].startswith("https://"))
            self.assertTrue(fields[4].startswith("https://"))

    def test_all_bundled_json_contracts_are_valid_json(self):
        paths = list((ROOT / "catalog").glob("*.json")) + list((ROOT / "contracts").glob("*.json"))
        self.assertGreaterEqual(len(paths), 5)
        for path in paths:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_agent_vendor_manifest_hashes_every_declared_file(self):
        manifest = json.loads((ROOT / "agent-vendor-manifest.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["catalogSha256"], bootstrap.load_catalog()["_catalogSha256"])
        self.assertEqual(manifest["networkRedirectPolicy"]["schemes"], ["https"])
        self.assertEqual(manifest["networkRedirectPolicy"]["addressFamily"], "ipv4-only")
        self.assertEqual(
            manifest["networkRedirectPolicy"]["integrityPolicy"],
            "catalog-sha256-and-official-checksum",
        )
        declared_paths = [entry["path"] for entry in manifest["files"]]
        self.assertEqual(len(declared_paths), len(set(declared_paths)))
        self.assertEqual(
            set(declared_paths),
            {
                "build-cloud-templates.sh",
                "tools/ppflight-template-bootstrap.py",
                "tools/build-template-engine.sh",
                "catalog/template-catalog.v1.json",
                "catalog/template-catalog.schema.json",
                "contracts/template-bootstrap-request.schema.json",
                "contracts/template-bootstrap-result.schema.json",
                "contracts/template-storage-discovery.schema.json",
                "contracts/agent-vendor-manifest.schema.json",
            },
        )
        self.assertIn(manifest["entrypoint"], declared_paths)
        for entry in manifest["files"]:
            with self.subTest(path=entry["path"]):
                candidate = (ROOT / entry["path"]).resolve()
                self.assertTrue(candidate.is_relative_to(ROOT.resolve()))
                digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                self.assertEqual(digest, entry["sha256"])

    def test_builder_disables_curl_config_and_non_https_protocols(self):
        builder = (ROOT / "tools/build-template-engine.sh").read_text(encoding="utf-8")
        self.assertEqual(
            builder.count("curl --disable --ipv4 --fail --location --max-redirs 5 --proto '=https' --proto-redir '=https'"),
            2,
        )
        curl_commands = [line.strip() for line in builder.splitlines() if line.lstrip().startswith("curl ")]
        self.assertEqual(len(curl_commands), 2)
        self.assertTrue(all("--ipv4" in command for command in curl_commands))
        self.assertIn('($data->{format} // "") eq "qcow2"', builder)
        self.assertEqual(builder.count('/usr/bin/python3 -I "$CATALOG_HELPER"'), 3)


class DiscoveryAndPlanTests(unittest.TestCase):
    def test_pve8_storage_discovery_uses_node_json_api(self):
        configs, statuses = good_inventory()
        statuses[0].update(active=1, enabled=0)
        runner = FakeRunner(configs, statuses)
        with mock.patch.object(bootstrap.socket, "gethostname", return_value="pve.example.com"):
            storages = bootstrap.discover_storages(runner)
        self.assertIn(("pvesh", "get", "/nodes/pve/storage", "--output-format", "json"), runner.calls)
        self.assertFalse(any(call[:2] == ("pvesm", "status") for call in runner.calls))
        download = next(row for row in storages if row["storageId"] == "download-local")
        self.assertFalse(download["roleEligibility"]["image"]["allowed"])

    def test_backup_inventory_uses_node_json_api(self):
        runner = mock.Mock()
        runner.json.return_value = [{"volid": "local:backup/vzdump-qemu-9000.vma.zst"}]
        with mock.patch.object(bootstrap.socket, "gethostname", return_value="pve.example.com"):
            volumes = bootstrap._backup_volumes(runner, "local", 9000)
        runner.json.assert_called_once_with(("pvesh", "get", "/nodes/pve/storage/local/content", "--content", "backup", "--vmid", "9000", "--output-format", "json"))
        self.assertEqual(volumes, ["local:backup/vzdump-qemu-9000.vma.zst"])

    def test_discovery_has_decimal_bytes_and_role_reasons(self):
        configs, statuses = good_inventory()
        configs.append({"storage": "disabled", "type": "dir", "content": "iso", "disable": 1})
        runner = FakeRunner(configs, statuses)
        storages = bootstrap.discover_storages(runner)
        download = next(row for row in storages if row["storageId"] == "download-local")
        backup = next(row for row in storages if row["storageId"] == "pbs-backup")
        disabled = next(row for row in storages if row["storageId"] == "disabled")
        self.assertEqual(download["availableBytes"], "50000000000")
        self.assertTrue(download["roleEligibility"]["image"]["allowed"])
        self.assertTrue(backup["shared"])
        self.assertFalse(disabled["roleEligibility"]["image"]["allowed"])
        self.assertIn("STORAGE_DISABLED", disabled["roleEligibility"]["image"]["reasons"])
        self.assertIn("MISSING_CONTENT_SNIPPETS", disabled["roleEligibility"]["image"]["reasons"])

    def test_discovery_rejects_unresolvable_snippets_path(self):
        configs, statuses = good_inventory()
        runner = FakeRunner(configs, statuses, unsupported_path_content="snippets")
        storages = bootstrap.discover_storages(runner)
        download = next(row for row in storages if row["storageId"] == "download-local")
        self.assertFalse(download["roleEligibility"]["image"]["allowed"])
        self.assertEqual(
            download["roleEligibility"]["image"]["reasons"],
            ["IMAGE_STORAGE_SNIPPETS_PATH_UNSUPPORTED"],
        )

    def test_discovery_suggests_explicit_content_remediation_without_executing_it(self):
        configs = [{"storage": "local", "type": "dir", "content": "iso,vztmpl,backup"}]
        statuses = [{"storage": "local", "status": "active", "avail": 50_000_000_000}]
        runner = FakeRunner(configs, statuses)
        storage = bootstrap.discover_storages(runner)[0]
        self.assertFalse(storage["roleEligibility"]["image"]["allowed"])
        remediation = storage["remediations"][0]
        self.assertEqual(remediation["storageId"], "local")
        self.assertEqual(remediation["currentContent"], "backup,iso,vztmpl")
        self.assertEqual(remediation["requiredContent"], "snippets")
        self.assertEqual(remediation["proposedContent"], "backup,iso,snippets,vztmpl")
        self.assertEqual(
            remediation["command"]["argv"],
            ["pvesm", "set", "local", "--content", "backup,iso,snippets,vztmpl"],
        )
        self.assertFalse(remediation["automatic"])
        self.assertNotIn(("pvesm", "set", "local", "--content", "backup,iso,snippets,vztmpl"), runner.calls)

    def test_discovery_rejects_unsafe_pve_storage_id(self):
        runner = FakeRunner(
            [{"storage": "local;touch-pwned", "type": "dir", "content": "iso,snippets"}],
            [{"storage": "local;touch-pwned", "status": "active", "avail": 1_000_000_000}],
        )
        with self.assertRaises(bootstrap.ContractError) as caught:
            bootstrap.discover_storages(runner)
        self.assertEqual(caught.exception.code, "PVE_STORAGE_RESPONSE_INVALID")

    def test_plan_contract_and_builder_argv(self):
        configs, statuses = good_inventory()
        runner = FakeRunner(configs, statuses)
        catalog = bootstrap.load_catalog()
        plan = bootstrap.prepare_plan(plan_args(), catalog, runner)
        self.assertEqual(plan["state"], "ready")
        self.assertTrue(plan["executable"])
        self.assertIsInstance(plan["requiredBytes"], str)
        self.assertEqual(plan["request"]["backupPolicy"], "required")
        self.assertEqual(plan["request"]["backupStorage"], "pbs-backup")
        self.assertEqual(len(plan["items"]), 7)
        required_item_fields = {
            "phase",
            "state",
            "errorCode",
            "sourceVolume",
            "templateVolume",
            "backupVolume",
            "upid",
        }
        self.assertTrue(required_item_fields.issubset(plan["items"][0]))
        argv = plan["command"]["argv"]
        self.assertNotIn("--replace", argv)
        self.assertIn("--expected-catalog-revision", argv)
        self.assertIn("--expected-catalog-sha256", argv)
        self.assertNotIn("http", " ".join(argv))

    def test_disabled_backup_is_explicit_and_omits_storage(self):
        catalog = bootstrap.load_catalog()
        request = bootstrap.build_request(
            plan_args(backup_policy="disabled", backup_storage=None), catalog, catalog["items"][:1]
        )
        self.assertEqual(request["backupPolicy"], "disabled")
        self.assertNotIn("backupStorage", request)
        with self.assertRaises(bootstrap.ContractError) as caught:
            bootstrap.build_request(
                plan_args(backup_policy="disabled", backup_storage=""), catalog, catalog["items"][:1]
            )
        self.assertEqual(caught.exception.code, "BACKUP_STORAGE_FORBIDDEN")

    def test_vmid_conflict_has_typed_item_error(self):
        configs, statuses = good_inventory()
        runner = FakeRunner(configs, statuses, resources=[{"vmid": 9000, "name": "important", "type": "qemu"}])
        plan = bootstrap.prepare_plan(plan_args(items="ubuntu-2204"), bootstrap.load_catalog(), runner)
        self.assertEqual(plan["state"], "blocked")
        self.assertEqual(plan["items"][0]["errorCode"], "VMID_CONFLICT")
        self.assertIn("VMID_CONFLICT", {error["errorCode"] for error in plan["errors"]})

    def test_execute_requires_exact_confirmed_catalog(self):
        catalog = bootstrap.load_catalog()
        with self.assertRaises(bootstrap.ContractError) as missing:
            bootstrap.build_request(plan_args(execute=True), catalog, catalog["items"][:1])
        self.assertEqual(missing.exception.code, "CATALOG_CONFIRMATION_REQUIRED")
        with self.assertRaises(bootstrap.ContractError) as drift:
            bootstrap.build_request(
                plan_args(
                    execute=True,
                    expected_catalog_revision=catalog["catalogRevision"],
                    expected_catalog_sha256="0" * 64,
                ),
                catalog,
                catalog["items"][:1],
            )
        self.assertEqual(drift.exception.code, "CATALOG_DRIFT")

    def test_storage_id_cannot_be_shell_syntax(self):
        with self.assertRaises(bootstrap.ContractError) as caught:
            bootstrap.validate_storage_id("local;touch-pwned", "imageStorage")
        self.assertEqual(caught.exception.code, "STORAGE_ID_INVALID")

    def test_cli_has_no_url_or_replace_option(self):
        parser = bootstrap.make_parser()
        bootstrap_parser = next(
            action.choices["bootstrap"]
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        option_strings = {option for action in bootstrap_parser._actions for option in action.option_strings}
        self.assertTrue(
            {"--url", "--catalog", "--catalog-path", "--cache-dir", "--replace", "--no-qos"}.isdisjoint(
                option_strings
            )
        )
        with self.assertRaises(bootstrap.ContractError) as caught:
            parser.parse_args(
                [
                    "bootstrap",
                    "--image-storage",
                    "local",
                    "--template-storage",
                    "raid",
                    "--backup-policy",
                    "disabled",
                    "--url",
                    "https://attacker.invalid/image",
                    "--replace",
                ]
            )
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENT")

    def test_builder_environment_cannot_enable_replace_or_config(self):
        hostile = {
            "REPLACE_EXISTING": "1",
            "CONFIG_FILE": "/tmp/attacker",
            "BASH_FUNC_curl%%": "() { echo attacker; }",
            "LD_AUDIT": "/tmp/attacker.so",
            "SSLKEYLOGFILE": "/tmp/tls-keys",
        }
        previous = {name: os.environ.get(name) for name in hostile}
        try:
            os.environ.update(hostile)
            environment = bootstrap.safe_process_environment(for_builder=True)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        for name in hostile:
            self.assertNotIn(name, environment)
        self.assertEqual(environment["PATH"], "/usr/sbin:/usr/bin:/sbin:/bin")
        self.assertEqual(environment["LC_ALL"], "C")

    def test_builder_failure_preserves_per_item_template_state(self):
        configs, statuses = good_inventory()
        runner = FakeRunner(configs, statuses, template_volumes={9000: "raid-zfs:vm-9000-disk-0"})
        catalog = bootstrap.load_catalog()
        args = plan_args(
            items="ubuntu-2204,ubuntu-2404",
            execute=True,
            expected_catalog_revision=catalog["catalogRevision"],
            expected_catalog_sha256=catalog["_catalogSha256"],
        )
        plan = bootstrap.prepare_plan(args, catalog, runner)
        with mock.patch.object(bootstrap.os, "geteuid", return_value=0, create=True), mock.patch.object(
            bootstrap, "_stream_process", return_value=1
        ):
            result, return_code = bootstrap.execute_plan(plan, runner)
        self.assertEqual(return_code, 1)
        self.assertEqual(result["items"][0]["state"], "template-ready")
        self.assertEqual(result["items"][0]["templateVolume"], "raid-zfs:vm-9000-disk-0")
        self.assertEqual(result["items"][1]["state"], "failed")
        self.assertEqual(result["items"][1]["errorCode"], "BUILDER_FAILED")

    def test_proxmox_upid_accepts_realm_but_not_shell_syntax(self):
        upid = "UPID:pve:0000009D:00002A1C:66D00000:vzdump:9000:root@pam:"
        self.assertEqual(bootstrap._extract_upid(upid), upid)
        with self.assertRaises(bootstrap.ContractError) as caught:
            bootstrap._extract_upid("UPID:pve:task:root@pam:;touch-pwned")
        self.assertEqual(caught.exception.code, "PVE_BACKUP_UPID_INVALID")


class CLITests(unittest.TestCase):
    def test_catalog_command_is_json_and_needs_no_pve(self):
        result = subprocess.run(
            [sys.executable, str(HELPER), "catalog"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        value = json.loads(result.stdout)
        self.assertEqual(value["state"], "succeeded")
        self.assertEqual(value["catalog"]["catalogRevision"], "2026-08-30.1")


if __name__ == "__main__":
    unittest.main()
