import copy
import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fcc_cache", ROOT / "scripts/fcc_runner_cache_patch.py"
)
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)


def original():
    return {
        "metadata": {
            "name": "gha-runner-fcc",
            "namespace": "energy-rag",
            "uid": "same",
            "resourceVersion": "10",
        },
        "spec": {
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "template": {
                "spec": {
                    "nodeSelector": {"kubernetes.io/hostname": "mp"},
                    "containers": [
                        {
                            "name": "runner",
                            "image": "unchanged",
                            "resources": {"limits": {"cpu": "2"}},
                            "env": [
                                {
                                    "name": "ACCESS_TOKEN",
                                    "valueFrom": {
                                        "secretKeyRef": {"name": "private", "key": "token"}
                                    },
                                }
                            ],
                            "volumeMounts": [{"name": "work", "mountPath": "/runner/_work"}],
                        }
                    ],
                    "volumes": [{"name": "work", "emptyDir": {}}],
                }
            },
        },
    }


def apply(document, patch):
    result = copy.deepcopy(document)
    for item in patch:
        keys = item["path"].lstrip("/").split("/")
        parent = result
        for key in keys[:-1]:
            parent = parent[int(key)] if isinstance(parent, list) else parent[key]
        key = keys[-1]
        if item["op"] == "test":
            assert parent[key] == item["value"]
        elif isinstance(parent, list):
            if key == "-":
                parent.append(copy.deepcopy(item["value"]))
            else:
                parent[int(key)] = copy.deepcopy(item["value"])
        else:
            parent[key] = copy.deepcopy(item["value"])
    return result


class RunnerCacheTests(unittest.TestCase):
    def test_live_root_runner_keeps_every_unrelated_field(self):
        before = original()
        saved = copy.deepcopy(before)
        patch = cache.cache_patch(before)
        after = apply(before, patch)
        self.assertEqual(before, saved)
        old = before["spec"]["template"]["spec"]["containers"][0]
        new = after["spec"]["template"]["spec"]["containers"][0]
        for key in ("name", "image", "resources"):
            self.assertEqual(old[key], new[key])
        self.assertEqual(new["env"][0], old["env"][0])
        self.assertEqual(new["volumeMounts"][0], old["volumeMounts"][0])
        self.assertNotIn("securityContext", new)
        self.assertEqual(cache.cache_patch(after), [])
        self.assertNotIn("ACCESS_TOKEN", str(patch))

    def test_canonical_manifest_matches_generator(self):
        deployment = yaml.safe_load((ROOT / "deploy/k3s/gha-runner-fcc.yaml").read_text())
        self.assertEqual(cache.cache_patch(deployment), [])

    def test_foreign_mount_or_volume_and_wrong_target_fail_closed(self):
        for kind in ("mount", "volume", "replicas", "strategy", "node"):
            item = original()
            pod = item["spec"]["template"]["spec"]
            if kind == "mount":
                pod["containers"][0]["volumeMounts"].append(
                    {"name": "foreign", "mountPath": "/runner-cache"}
                )
            elif kind == "volume":
                pod["volumes"].append({"name": "toolcache", "hostPath": {"path": "/"}})
            elif kind == "replicas":
                item["spec"]["replicas"] = 2
            elif kind == "strategy":
                item["spec"]["strategy"]["type"] = "RollingUpdate"
            else:
                pod["nodeSelector"]["kubernetes.io/hostname"] = "h7"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                cache.cache_patch(item)

    def test_updates_existing_cache_env_without_dropping_credentials(self):
        item = original()
        item["spec"]["template"]["spec"]["containers"][0]["env"].append(
            {"name": "PIP_CACHE_DIR", "value": "/root/.cache/pip"}
        )
        result = apply(item, cache.cache_patch(item))
        self.assertEqual(cache.cache_patch(result), [])

    def test_cache_volume_aliases_are_rejected_without_changing_input(self):
        for volume in cache.MOUNTS:
            for location in ("runner", "sidecar", "init"):
                item = original()
                pod = item["spec"]["template"]["spec"]
                mount = {"name": volume, "mountPath": "/unrelated-data"}
                pod["volumes"].append({"name": volume, "emptyDir": {}})
                if location == "runner":
                    pod["containers"][0]["volumeMounts"].append(mount)
                else:
                    container = {"name": location, "volumeMounts": [mount]}
                    key = "initContainers" if location == "init" else "containers"
                    pod.setdefault(key, []).append(container)
                saved = copy.deepcopy(item)
                with self.subTest(volume=volume, location=location):
                    with self.assertRaisesRegex(ValueError, "mounted outside"):
                        cache.cache_patch(item)
                    self.assertEqual(item, saved)


if __name__ == "__main__":
    unittest.main()
