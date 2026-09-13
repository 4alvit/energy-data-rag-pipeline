import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml

SPEC = importlib.util.spec_from_file_location(
    "pin_images", Path(__file__).resolve().parents[1] / "scripts/pin-deployment-images.py"
)
pin_images = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pin_images)


class PinDeploymentTests(unittest.TestCase):
    def test_every_application_image_uses_verified_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            images = {
                name: name + "@sha256:" + "a" * 64
                for name in (
                    "ghcr.io/4alvit/energy-data-rag-pipeline",
                    "ghcr.io/4alvit/free-claude-code",
                )
            }
            (path / "evidence.json").write_text(
                json.dumps(
                    {
                        "repository": "4alvit/energy-data-rag-pipeline",
                        "tag": "v1.2.3",
                        "images": images,
                    }
                )
            )
            (path / "kustomization.yaml").write_text("resources: [api.yaml, mcp.yaml, fcc.yaml]\n")
            pin_images.pin(path / "evidence.json", path / "kustomization.yaml", "1.2.3")
            config = yaml.safe_load((path / "kustomization.yaml").read_text())
            self.assertEqual(len(config["images"]), 2)
            self.assertTrue(
                all(image["digest"] == "sha256:" + "a" * 64 for image in config["images"])
            )

    def test_missing_digest_does_not_change_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "evidence.json").write_text(
                json.dumps(
                    {"repository": "4alvit/energy-data-rag-pipeline", "tag": "v1.2.3", "images": {}}
                )
            )
            (path / "kustomization.yaml").write_text("resources: [api.yaml]\n")
            with self.assertRaises(ValueError):
                pin_images.pin(path / "evidence.json", path / "kustomization.yaml", "1.2.3")
            self.assertEqual((path / "kustomization.yaml").read_text(), "resources: [api.yaml]\n")


if __name__ == "__main__":
    unittest.main()
