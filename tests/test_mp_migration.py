"""Offline guards for the operator-driven Energy RAG storage migration."""

import copy
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("migration", ROOT / "scripts/mp_migration.py")
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def deployment(name="api"):
    return {
        "metadata": {"name": name, "uid": "same-deployment", "resourceVersion": "123"},
        "spec": {
            "replicas": 0,
            "template": {
                "spec": {
                    "nodeSelector": {"kubernetes.io/hostname": "h7"},
                    "securityContext": {"fsGroup": 999},
                    "containers": [
                        {
                            "name": name,
                            "image": "old:latest",
                            "env": [
                                {
                                    "name": "SECRET",
                                    "valueFrom": {
                                        "secretKeyRef": {"name": "existing", "key": "credential"}
                                    },
                                }
                            ],
                            "volumeMounts": [{"name": "data", "mountPath": "/data"}],
                            "livenessProbe": {"httpGet": {"path": "/health", "port": 8000}},
                        }
                    ],
                    "volumes": [
                        {
                            "name": "data",
                            "persistentVolumeClaim": {"claimName": migration.CLAIMS[name][0]},
                        },
                        {"name": "cache", "emptyDir": {}},
                    ],
                }
            },
        },
    }


def nfs_binding():
    claim = {
        "metadata": {"name": "energy-rag-data-nfs-v1", "uid": "claim-1"},
        "spec": {"volumeName": "pv-1"},
        "status": {"phase": "Bound"},
    }
    volume = {
        "metadata": {"name": "pv-1", "uid": "volume-1"},
        "spec": {
            "claimRef": {"uid": "claim-1"},
            "nfs": {"server": "192.168.167.25", "path": "/volume1/k3s-nfs/new-pvc"},
            "mountOptions": ["nfsvers=4.1", "hard"],
        },
    }
    return claim, volume


class MigrationTests(unittest.TestCase):
    def test_minimal_patch_keeps_live_credentials_probes_and_unrelated_volumes(self):
        original = deployment()
        untouched = copy.deepcopy(original)
        patch = migration.cutover_patch(original, "api")
        spec = next(op["value"] for op in patch if op["path"] == "/spec/template/spec")
        before = original["spec"]["template"]["spec"]
        self.assertEqual(original, untouched)
        self.assertEqual(spec["securityContext"], before["securityContext"])
        self.assertEqual(spec["containers"][0]["env"], before["containers"][0]["env"])
        self.assertEqual(
            spec["containers"][0]["livenessProbe"], before["containers"][0]["livenessProbe"]
        )
        self.assertEqual(spec["volumes"][1], before["volumes"][1])
        self.assertEqual(spec["containers"][0]["image"], migration.API_IMAGE)
        self.assertEqual(spec["containers"][0]["volumeMounts"][0]["subPath"], "data")
        self.assertEqual(
            [op["path"] for op in patch[:3]],
            ["/metadata/uid", "/metadata/resourceVersion", "/spec/replicas"],
        )

    def test_running_or_unreviewed_source_cannot_generate_patch(self):
        for change in ("running", "wrong-claim", "affinity"):
            item = deployment()
            if change == "running":
                item["spec"]["replicas"] = 1
            elif change == "wrong-claim":
                item["spec"]["template"]["spec"]["volumes"][0]["persistentVolumeClaim"][
                    "claimName"
                ] = "different"
            else:
                item["spec"]["template"]["spec"]["affinity"] = {"nodeAffinity": {"something": True}}
            with self.subTest(change=change), self.assertRaises(ValueError):
                migration.cutover_patch(item, "api")

    def test_postgres_targets_new_child_directory_and_rollback_requires_identity(self):
        item = deployment("postgres")
        original_probe = {
            "exec": {"command": ["pg_isready", "-U", "rag"]},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
            "failureThreshold": 3,
        }
        item["spec"]["template"]["spec"]["containers"][0]["readinessProbe"] = copy.deepcopy(
            original_probe
        )
        patch = migration.cutover_patch(item, "postgres")
        spec = next(op["value"] for op in patch if op["path"] == "/spec/template/spec")
        self.assertEqual(
            spec["containers"][0]["env"][-1],
            {"name": "PGDATA", "value": "/var/lib/postgresql/data/pgdata"},
        )
        self.assertEqual(
            spec["containers"][0]["readinessProbe"], {**original_probe, "timeoutSeconds": 5}
        )
        self.assertEqual(
            spec["containers"][0]["livenessProbe"],
            {
                **item["spec"]["template"]["spec"]["containers"][0]["livenessProbe"],
                "timeoutSeconds": 5,
            },
        )
        original = copy.deepcopy(item)
        original["spec"]["replicas"] = 1
        rollback = migration.rollback_patch(item, original)
        self.assertEqual(rollback[-1]["value"], 1)
        rollback_spec = next(op["value"] for op in rollback if op["path"] == "/spec/template/spec")
        self.assertEqual(rollback_spec["containers"][0]["image"], migration.PG_IMAGE)
        item["metadata"]["uid"] = "replacement"
        with self.assertRaises(ValueError):
            migration.rollback_patch(item, original)

    def test_schema_ignores_random_tokens_but_detects_sql_change(self):
        first = (
            b"-- generated\n\\restrict random1\nCREATE TABLE x (id int);\n\\unrestrict random1\n"
        )
        second = b"-- another date\n\\restrict random2\n\nCREATE TABLE x (id int);\n\\unrestrict random2\n"
        self.assertEqual(migration.schema_hash(first), migration.schema_hash(second))
        self.assertNotEqual(
            migration.schema_hash(first), migration.schema_hash(second.replace(b"int", b"text"))
        )

    def test_counts_extensions_ownership_and_idle_sessions_are_gates(self):
        before = [
            {
                "kind": "database",
                "version": "16.15",
                "extensions": [{"name": "vector", "version": "0.8.6"}],
                "other_sessions": 0,
            },
            {"kind": "table", "table": "documents", "owner": "rag", "rows": 123},
        ]
        migration.assert_no_sessions(before)
        for key, value in (("rows", 124), ("owner", "different")):
            after = copy.deepcopy(before)
            after[1][key] = value
            with self.assertRaises(ValueError):
                migration.check_inventory(before, after)
        after = copy.deepcopy(before)
        after[0]["extensions"][0]["version"] = "0.8.5"
        with self.assertRaises(ValueError):
            migration.check_inventory(before, after)
        after[0]["other_sessions"] = 1
        with self.assertRaises(ValueError):
            migration.assert_no_sessions(after)

    def test_volume_identity_nfs_options_and_local_node_affinity_fail_closed(self):
        claim, volume = nfs_binding()
        self.assertEqual(migration.validate_binding(claim, volume)["volume_uid"], "volume-1")
        for field, value in (
            ("mountOptions", ["hard"]),
            ("nfs", {"server": "192.168.167.25", "path": "/volume1/k3s-nfs/../other-export"}),
            ("mountOptions", ["nfsvers=4.1", "hard", "soft"]),
            ("claimRef", {"uid": "replaced"}),
            ("nfs", {"server": "other", "path": "/volume1/k3s-nfs/new-pvc"}),
        ):
            bad = copy.deepcopy(volume)
            bad["spec"][field] = value
            with self.assertRaises(ValueError):
                migration.validate_binding(claim, bad)
        claim["metadata"]["name"] = "postgres-data-mp-v1"
        volume["spec"]["persistentVolumeReclaimPolicy"] = "Retain"
        volume["spec"]["hostPath"] = {"path": "/var/lib/rancher/k3s/storage/new"}
        term = {
            "matchExpressions": [
                {"key": "kubernetes.io/hostname", "operator": "In", "values": ["mp"]}
            ]
        }
        volume["spec"]["nodeAffinity"] = {"required": {"nodeSelectorTerms": [term]}}
        migration.validate_binding(claim, volume, postgres_target=True)
        term["matchExpressions"][0]["values"] = ["h7"]
        with self.assertRaises(ValueError):
            migration.validate_binding(claim, volume, postgres_target=True)

    def test_private_evidence_refuses_symlinks_overwrite_and_repo_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = migration.private_directory(root / "evidence", create=True)
            migration.save(evidence, "secret.json", {"test": "private"})
            self.assertEqual((evidence / "secret.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual(evidence.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(FileExistsError):
                migration.save(evidence, "secret.json", {})
            (root / "link").symlink_to(evidence)
            with self.assertRaises(ValueError):
                migration.private_directory(root / "link")
            with (
                mock.patch.object(migration, "ROOT", root.resolve()),
                self.assertRaises(ValueError),
            ):
                migration.private_directory(evidence)

    def test_backup_publish_only_after_dump_validation(self):
        config = next(yaml.safe_load_all((ROOT / "deploy/k3s/postgres-backup.yaml").read_text()))
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                backups = root / "backups"
                backups.mkdir()
                binary = root / "bin"
                binary.mkdir()
                commands = {
                    "pg_dump": '#!/bin/sh\nfor arg; do case "$arg" in --file=*) printf "test dump" > "${arg#--file=}";; esac; done\n',
                    "pg_restore": "#!/bin/sh\nexit " + ("1" if fail else "0") + "\n",
                    "sync": "#!/bin/sh\nexit 0\n",
                }
                for name, body in commands.items():
                    path = binary / name
                    path.write_text(body)
                    path.chmod(0o700)
                script = config["data"]["backup.sh"].replace("/backups", str(backups))
                result = subprocess.run(
                    ["sh", "-c", script],
                    env={**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]},
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode == 0, not fail, result.stderr.decode())
                self.assertEqual(len(list(backups.rglob("*.dump"))), 0 if fail else 1)
                self.assertEqual(len(list(backups.rglob("*.sha256"))), 0 if fail else 1)
                self.assertEqual(list(backups.rglob("*.partial")), [])


if __name__ == "__main__":
    unittest.main()
