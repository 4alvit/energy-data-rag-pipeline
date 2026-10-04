"""Bind real native image identity and current-attempt evidence before assembly."""

import copy
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import merge_oci_archives as oci
import native_containers as native

SPEC = importlib.util.spec_from_file_location(
    "oci_fixture", Path(__file__).with_name("test_merge_oci_archives.py")
)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)

EXPECTED = {
    "schema": 1,
    "version": "0.2.10",
    "channel": "beta",
    "revision": "a" * 40,
    "run_id": "1234",
    "run_attempt": "2",
}


class NativeContainersTest(unittest.TestCase):
    """Test archive safety and end-to-end offline assembly with tiny OCI inputs."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "native-inputs"
        self.inputs.mkdir()
        self.output = self.root / "release-dist"
        self.inputs_digest = native.fingerprint(self.root, [])

    def archive(self, arch, path, *, sbom=True, provenance=True, user="1000"):
        """Create content-addressed image + real bound attestation statements."""
        entries = {"oci-layout": b'{"imageLayoutVersion":"1.0.0"}'}
        blob = fixture.MergeTest.blob
        layer_data = fixture.MergeTest.layer_bytes()
        layer = blob(entries, layer_data, "application/vnd.oci.image.layer.v1.tar")
        config = blob(
            entries,
            {
                "os": "linux",
                "architecture": arch,
                "config": {
                    "User": user,
                    "Labels": {
                        "org.opencontainers.image.version": EXPECTED["version"],
                        "org.opencontainers.image.revision": EXPECTED["revision"],
                    },
                },
                "rootfs": {
                    "type": "layers",
                    "diff_ids": ["sha256:" + hashlib.sha256(layer_data).hexdigest()],
                },
            },
            oci.CONFIG,
        )
        image = blob(
            entries,
            {"schemaVersion": 2, "mediaType": oci.MANIFEST, "config": config, "layers": [layer]},
            oci.MANIFEST,
        )
        image["platform"] = {"os": "linux", "architecture": arch}
        predicates = (["https://slsa.dev/provenance/v1"] if provenance else []) + (
            [native.SBOM] if sbom else []
        )
        statements = [
            blob(
                entries,
                {
                    "_type": "https://in-toto.io/Statement/v1",
                    "subject": [{"name": "_", "digest": {"sha256": image["digest"][7:]}}],
                    "predicateType": kind,
                    "predicate": {},
                },
                oci.IN_TOTO,
            )
            for kind in predicates
        ]
        attestation = blob(
            entries,
            {
                "schemaVersion": 2,
                "mediaType": oci.MANIFEST,
                "config": blob(entries, {"os": "unknown", "architecture": "unknown"}, oci.CONFIG),
                "layers": statements,
            },
            oci.MANIFEST,
        )
        attestation["platform"] = {"os": "unknown", "architecture": "unknown"}
        attestation["annotations"] = {
            "vnd.docker.reference.type": "attestation-manifest",
            "vnd.docker.reference.digest": image["digest"],
        }
        entries["index.json"] = oci.canonical(
            {"schemaVersion": 2, "mediaType": oci.INDEX, "manifests": [image, attestation]}
        )
        with tarfile.open(path, "w") as stream:
            for name, value in entries.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(value)
                stream.addfile(entry, io.BytesIO(value))
        return native.inspect_archive(path, arch, EXPECTED)

    def receipt(self, product="rag", arch="amd64", **options):
        cell = self.inputs / f"{product}-{arch}"
        cell.mkdir()
        checked = self.archive(arch, cell / "image.oci.tar", **options)
        machine, runner_arch = native.ARCHITECTURES[arch]
        receipt = {
            **EXPECTED,
            "product": product,
            "architecture": arch,
            "platform": f"linux/{arch}",
            "inputs_sha256": self.inputs_digest,
            **checked,
            "runner": {"os": "Linux", "machine": machine, "arch": runner_arch},
            "smoke": {
                "product": product,
                "architecture": arch,
                "uid": 1000,
                "scope": native.SMOKE_SCOPE[product],
                "status": "passed",
            },
            "tools": {
                "docker": "fixture-docker",
                "buildx": "fixture-buildx",
                "skopeo": "fixture-skopeo",
            },
        }
        (cell / "receipt.json").write_text(json.dumps(receipt))
        return receipt, checked

    def test_each_attestation_is_mandatory(self):
        for options, message in (({"sbom": False}, "SBOM"), ({"provenance": False}, "provenance")):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                self.archive("amd64", self.root / "fixture.tar", **options)

    def test_root_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-root"):
            self.archive("amd64", self.root / "fixture.tar", user="root")

    def test_receipt_rejects_stale_attempt_source_product_and_inputs(self):
        receipt, checked = self.receipt()
        native.validate_receipt(receipt, EXPECTED, "rag", "amd64", self.inputs_digest, checked)
        for key, value in {
            "run_attempt": "1",
            "run_id": "999",
            "revision": "b" * 40,
            "version": "0.2.9",
            "channel": "rc",
            "product": "fcc",
            "architecture": "arm64",
            "inputs_sha256": "0" * 64,
            "archive": {"sha256": "0" * 64, "size": 1},
        }.items():
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "binding"):
                native.validate_receipt(
                    {**receipt, key: value}, EXPECTED, "rag", "amd64", self.inputs_digest, checked
                )

    def test_receipt_requires_native_runner_smoke_and_toolchain(self):
        receipt, checked = self.receipt()
        for key, value in (
            ("runner", {"os": "Linux", "machine": "x86_64", "arch": "ARM64"}),
            ("smoke", {**receipt["smoke"], "status": "skipped"}),
            ("tools", {}),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                native.validate_receipt(
                    {**receipt, key: value}, EXPECTED, "rag", "amd64", self.inputs_digest, checked
                )

    def test_loaded_image_binds_config_platform_and_filesystem(self):
        _, checked = self.receipt()
        loaded = {
            "Id": checked["config_digest"],
            "Os": "linux",
            "Architecture": "amd64",
            "RootFS": {"Type": "layers", "Layers": checked["diff_ids"]},
        }
        native.validate_loaded(loaded, checked, "amd64")
        for key, value in (
            ("Id", checked["manifest_digest"]),
            ("Architecture", "arm64"),
            ("Os", "windows"),
            ("RootFS", {"Type": "layers", "Layers": ["sha256:" + "0" * 64]}),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                native.validate_loaded({**loaded, key: value}, checked, "amd64")

    def test_binding_rejects_checkout_mismatch_and_dirty_inputs(self):
        (self.root / ".release-policy.json").write_text(json.dumps({"version_file": "version"}))
        (self.root / "version").write_text(EXPECTED["version"] + "\n")
        environment = {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "1234", "GITHUB_RUN_ATTEMPT": "2"}
        with mock.patch.dict("os.environ", environment, clear=True):
            for values, message in (
                (["b" * 40], "Checkout"),
                (["a" * 40, " M Dockerfile"], "Tracked inputs"),
            ):
                with (
                    self.subTest(message=message),
                    mock.patch.object(native, "command", side_effect=values),
                    self.assertRaisesRegex(ValueError, message),
                ):
                    native.binding(self.root, EXPECTED["version"], "beta")
            with mock.patch.object(native, "command", side_effect=["a" * 40, ""]):
                self.assertEqual(native.binding(self.root, EXPECTED["version"], "beta"), EXPECTED)

    def test_wrong_host_architecture_stops_before_docker(self):
        with (
            mock.patch.object(native, "binding", return_value=EXPECTED),
            mock.patch.object(native.platform, "system", return_value="Linux"),
            mock.patch.object(native.platform, "machine", return_value="x86_64"),
            mock.patch.object(native, "command") as command,
        ):
            with self.assertRaisesRegex(ValueError, "native Linux architecture"):
                native.build(ROOT, self.output, "rag", "arm64", "0.2.10", "beta")
            command.assert_not_called()

    def prepare_assembly(self):
        for product in native.PRODUCTS:
            for arch in native.ARCHITECTURES:
                self.receipt(product, arch)
        config = json.loads((ROOT / ".release-package.json").read_text())
        (self.root / ".release-package.json").write_text(json.dumps(config))
        (self.root / ".release-policy.json").write_text((ROOT / ".release-policy.json").read_text())

        def package_stub(root, version, channel, output, **kwargs):
            self.assertFalse(kwargs["containers"])
            output.mkdir()
            (output / "source.tar.gz").write_bytes(b"tracked source archive")

        self.addCleanup(mock.patch.stopall)
        mock.patch.object(native, "binding", return_value=copy.deepcopy(EXPECTED)).start()
        mock.patch.object(native.package, "snapshot", return_value=[]).start()
        self.package = mock.patch.object(
            native.package, "build_candidate", side_effect=package_stub
        ).start()

    def assemble(self):
        native.assemble(self.root, self.inputs, self.output, EXPECTED["version"], "beta")

    def test_assembly_preserves_two_assets_platforms_attestations_and_checksums(self):
        self.prepare_assembly()
        self.assemble()
        evidence = json.loads((self.output / "native-build-evidence.json").read_text())
        self.assertEqual(
            set(evidence["cells"]), {"rag-amd64", "rag-arm64", "fcc-amd64", "fcc-arm64"}
        )
        for product, asset in native.PRODUCTS.items():
            self.assertTrue((self.output / asset).is_file())
            self.assertEqual(
                set(evidence["assembly"][product]["images"]), {"linux/amd64", "linux/arm64"}
            )
            for item in evidence["assembly"][product]["inputs"]:
                kinds = {kind for att in item["attestations"] for kind in att["predicate_types"]}
                self.assertIn(native.SBOM, kinds)
                self.assertTrue(kinds & oci.PROVENANCE_TYPES)
        for line in (self.output / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ")
            self.assertEqual(digest, native.file_identity(self.output / name)["sha256"])

    def test_missing_or_extra_cell_rejected_before_output(self):
        self.prepare_assembly()
        (self.inputs / "rag-amd64").rename(self.inputs / "unexpected")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.assemble()
        self.package.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_symlink_cell_rejected(self):
        self.prepare_assembly()
        original = self.inputs / "rag-amd64"
        original.rename(self.root / "elsewhere")
        original.symlink_to(self.root / "elsewhere", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "regular directory"):
            self.assemble()

    def test_symlink_receipt_rejected(self):
        self.prepare_assembly()
        receipt = self.inputs / "rag-amd64/receipt.json"
        receipt.rename(self.root / "receipt.json")
        receipt.symlink_to(self.root / "receipt.json")
        with self.assertRaisesRegex(ValueError, "Unsafe native receipt"):
            self.assemble()

    def test_tampered_archive_rejected_before_output(self):
        self.prepare_assembly()
        path = self.inputs / "rag-amd64/image.oci.tar"
        with path.open("r+b") as stream:
            stream.seek(512)
            stream.write(b"X")
        with self.assertRaises(ValueError):
            self.assemble()
        self.package.assert_not_called()

    def test_swapped_native_archive_rejected(self):
        self.prepare_assembly()
        path = self.inputs / "rag-amd64/image.oci.tar"
        path.write_bytes((self.inputs / "rag-arm64/image.oci.tar").read_bytes())
        with self.assertRaisesRegex(ValueError, "platform"):
            self.assemble()

    def test_modified_receipt_attempt_rejected_before_output(self):
        self.prepare_assembly()
        path = self.inputs / "rag-amd64/receipt.json"
        receipt = json.loads(path.read_text())
        receipt["run_attempt"] = "1"
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "binding"):
            self.assemble()
        self.package.assert_not_called()


if __name__ == "__main__":
    unittest.main()
