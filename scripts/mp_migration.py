"""Prepare private Energy RAG migration evidence; never mutate cluster resources.

The operator performs the reviewed cutover commands separately. No LLM or
embedding/ingestion endpoint is called. PostgreSQL moves by logical dump across
ARM64/AMD64; old PVCs and Service identities remain untouched.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

API_IMAGE = "ghcr.io/4alvit/energy-data-rag-pipeline@sha256:432037c87980b1a468e8462686b946896f022863f6195632e89cade182b36559"
PG_IMAGE = (
    "pgvector/pgvector@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b"
)
CLAIMS = {
    "api": ("energy-rag-data", "energy-rag-data-nfs-v1"),
    "postgres": ("postgres-data", "postgres-data-mp-v1"),
}
ROOT = Path(__file__).resolve().parents[1]

INVENTORY_SQL = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT json_build_object('kind','database','version',current_setting('server_version'),
 'encoding',pg_encoding_to_char(encoding),'collate',datcollate,'ctype',datctype,
 'extensions',(SELECT json_agg(json_build_object('name',extname,'version',extversion) ORDER BY extname) FROM pg_extension),
 'other_sessions',(SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND backend_type='client backend'))
 FROM pg_database WHERE datname=current_database();
SELECT format('SELECT json_build_object(''kind'',''table'',''schema'',%L,''table'',%L,''owner'',%L,''rows'',count(*)) FROM %I.%I;', schemaname,tablename,tableowner,schemaname,tablename)
 FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname,tablename
\gexec
COMMIT;
"""

DATA_MANIFEST_CODE = r"""
import hashlib,json,os,stat,sys
root=sys.argv[1]; result={}
for parent,dirs,files in os.walk(root,followlinks=False):
 for name in dirs+files:
  path=os.path.join(parent,name); meta=os.lstat(path)
  if stat.S_ISLNK(meta.st_mode) or not (stat.S_ISDIR(meta.st_mode) or stat.S_ISREG(meta.st_mode)):
   raise SystemExit('Data contains an unsupported link or special file')
 for name in files:
  path=os.path.join(parent,name); digest=hashlib.sha256()
  with open(path,'rb') as source:
   while True:
    block=source.read(1024*1024)
    if not block: break
    digest.update(block)
  result[os.path.relpath(path,root)]={'sha256':digest.hexdigest(),'bytes':os.stat(path).st_size}
print(json.dumps(result,sort_keys=True))
"""


def private_directory(path: Path, create: bool = False) -> Path:
    path = path.absolute()
    if path.resolve().is_relative_to(ROOT) or path.is_symlink():
        raise ValueError("Evidence must be private and outside the repository")
    if create:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise ValueError("Evidence directory must exist and belong to this operator")
    path.chmod(0o700)
    return path


def save(directory: Path, name: str, value: object) -> None:
    data = (
        value if isinstance(value, bytes) else json.dumps(value, indent=2, sort_keys=True).encode()
    )
    descriptor = os.open(
        directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)


def load(directory: Path, name: str):
    return json.loads((directory / name).read_text())


def schema_hash(value: bytes) -> str:
    # pg_dump >=16.10 emits a random psql restrict token; SQL is otherwise retained.
    lines = [
        line
        for line in value.splitlines()
        if line.strip() and not line.startswith((b"--", b"\\restrict ", b"\\unrestrict "))
    ]
    return hashlib.sha256(b"\n".join(lines)).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_child(value: str, prefix: str) -> bool:
    path = PurePosixPath(value)
    return (
        value.startswith(prefix)
        and value != prefix
        and ".." not in path.parts
        and str(path) == value
    )


def validate_binding(claim: dict, volume: dict, postgres_target: bool = False) -> dict:
    spec = volume["spec"]
    if claim.get("status", {}).get("phase") != "Bound":
        raise ValueError("A migration claim is not Bound")
    if (
        claim["spec"]["volumeName"] != volume["metadata"]["name"]
        or spec["claimRef"]["uid"] != claim["metadata"]["uid"]
    ):
        raise ValueError("PVC/PV identity does not agree")
    if postgres_target:
        if spec.get("persistentVolumeReclaimPolicy") != "Retain":
            raise ValueError("PostgreSQL destination PV must retain data after a claim deletion")
        local_path = spec.get("local", spec.get("hostPath", {})).get("path", "")
        if not canonical_child(local_path, "/var/lib/rancher/k3s/storage/"):
            raise ValueError("PostgreSQL destination is outside the reviewed local-path directory")
        terms = spec.get("nodeAffinity", {}).get("required", {}).get("nodeSelectorTerms", [])
        if (
            not (spec.get("local") or spec.get("hostPath"))
            or not terms
            or any(
                not any(
                    e.get("key") == "kubernetes.io/hostname"
                    and e.get("operator") == "In"
                    and e.get("values") == ["mp"]
                    for e in t.get("matchExpressions", [])
                )
                for t in terms
            )
        ):
            raise ValueError("PostgreSQL destination must be local storage restricted to mp")
    elif claim["metadata"]["name"].endswith("-nfs-v1"):
        nfs = spec.get("nfs", {})
        if nfs.get("server") != "192.168.167.25" or not canonical_child(
            nfs.get("path", ""), "/volume1/k3s-nfs/"
        ):
            raise ValueError("NFS destination is outside the reviewed Synology export")
        options = set(spec.get("mountOptions", []))
        if not {"nfsvers=4.1", "hard"}.issubset(options) or options.intersection(
            {"soft", "softerr", "softreval"}
        ):
            raise ValueError("NFS destination requires the reviewed hard NFSv4.1 mount")
    return {
        "claim": claim["metadata"]["name"],
        "claim_uid": claim["metadata"]["uid"],
        "volume": volume["metadata"]["name"],
        "volume_uid": volume["metadata"]["uid"],
    }


def comparable_inventory(value: list[dict]) -> list[dict]:
    result = copy.deepcopy(value)
    for row in result:
        if row.get("kind") == "database":
            row.pop("other_sessions", None)
    return result


def check_inventory(before: list[dict], after: list[dict]) -> None:
    if comparable_inventory(before) != comparable_inventory(after):
        raise ValueError("Database versions, extensions, table ownership or row counts differ")


def assert_no_sessions(inventory: list[dict]) -> None:
    meta = [row for row in inventory if row.get("kind") == "database"]
    if len(meta) != 1 or meta[0].get("other_sessions") != 0:
        raise ValueError("Other database clients are still connected")


def cutover_patch(deployment: dict, name: str) -> list[dict]:
    if name not in CLAIMS or deployment["metadata"]["name"] != name:
        raise ValueError("Unexpected deployment")
    if deployment["spec"].get("replicas") != 0:
        raise ValueError("Both production deployments must be deliberately scaled to zero first")
    spec = copy.deepcopy(deployment["spec"]["template"]["spec"])
    container = next(c for c in spec["containers"] if c["name"] == name)
    data = next(v for v in spec["volumes"] if v["name"] == "data")
    if data.get("persistentVolumeClaim", {}).get("claimName") != CLAIMS[name][0]:
        raise ValueError("Source PVC differs from the reviewed migration")
    if spec.get("affinity"):
        raise ValueError("Unexpected affinity requires explicit review before migration")
    spec["nodeSelector"] = {"kubernetes.io/hostname": "mp", "kubernetes.io/arch": "amd64"}
    container["image"] = API_IMAGE if name == "api" else PG_IMAGE
    data["persistentVolumeClaim"]["claimName"] = CLAIMS[name][1]
    if name == "api":
        next(v for v in container["volumeMounts"] if v["name"] == "data")["subPath"] = "data"
        container["startupProbe"] = {
            "tcpSocket": {"port": 8000},
            "periodSeconds": 10,
            "timeoutSeconds": 5,
            "failureThreshold": 90,
        }
    else:
        for probe_name in ("readinessProbe", "livenessProbe"):
            probe = container.get(probe_name)
            if probe and probe.get("timeoutSeconds", 1) == 1:
                probe["timeoutSeconds"] = 5
        if any(e["name"] == "PGDATA" for e in container.get("env", [])):
            raise ValueError("Unexpected existing PGDATA requires explicit review")
        container.setdefault("env", []).append(
            {"name": "PGDATA", "value": "/var/lib/postgresql/data/pgdata"}
        )
    return [
        {"op": "test", "path": "/metadata/uid", "value": deployment["metadata"]["uid"]},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": deployment["metadata"]["resourceVersion"],
        },
        {"op": "test", "path": "/spec/replicas", "value": 0},
        {"op": "replace", "path": "/spec/template/spec", "value": spec},
        {"op": "add", "path": "/spec/strategy", "value": {"type": "Recreate"}},
        {"op": "replace", "path": "/spec/replicas", "value": 1},
    ]


def rollback_patch(current: dict, original: dict) -> list[dict]:
    if (
        current["metadata"]["uid"] != original["metadata"]["uid"]
        or current["spec"].get("replicas") != 0
    ):
        raise ValueError(
            "Rollback requires the same deployment, stopped before changing its source"
        )
    spec = copy.deepcopy(original["spec"]["template"]["spec"])
    name = original["metadata"]["name"]
    if name not in CLAIMS:
        raise ValueError("Unexpected rollback deployment")
    next(c for c in spec["containers"] if c["name"] == name)["image"] = (
        API_IMAGE if name == "api" else PG_IMAGE
    )
    return [
        {"op": "test", "path": "/metadata/uid", "value": current["metadata"]["uid"]},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": current["metadata"]["resourceVersion"],
        },
        {"op": "test", "path": "/spec/replicas", "value": 0},
        {
            "op": "replace",
            "path": "/spec/template/spec",
            "value": spec,
        },
        {"op": "add", "path": "/spec/strategy", "value": {"type": "Recreate"}},
        {"op": "replace", "path": "/spec/replicas", "value": original["spec"].get("replicas", 1)},
    ]


class Cluster:
    def __init__(self, context: str, directory: Path):
        self.prefix = ["kubectl", "--context", context, "-n", "energy-rag"]
        self.directory = directory

    def run(self, args: list[str], data: bytes | None = None) -> bytes:
        result = subprocess.run(
            self.prefix + args, input=data, capture_output=True, check=False, timeout=600
        )
        if result.returncode:
            with (self.directory / "commands-private.stderr").open("ab") as errors:
                os.chmod(errors.name, 0o600)
                errors.write(result.stderr)
            raise RuntimeError("Cluster command failed; inspect commands-private.stderr")
        return result.stdout

    def get(self, kind: str, name: str | None = None) -> dict:
        return json.loads(self.run(["get", kind, *([name] if name else []), "-o", "json"]))

    def pod(self, app: str) -> dict:
        pods = self.get("pods")["items"]
        matches = [
            p
            for p in pods
            if p["metadata"].get("labels", {}).get("app") == app
            and p["status"].get("phase") == "Running"
            and not p["metadata"].get("deletionTimestamp")
        ]
        if len(matches) != 1 or not all(
            c.get("ready") for c in matches[0]["status"].get("containerStatuses", [])
        ):
            raise ValueError("Expected exactly one ready source pod")
        return matches[0]

    def exec(self, pod: str, command: list[str], data: bytes | None = None) -> bytes:
        return self.run(["exec", "-i", pod, "--", *command], data)

    def exec_file(self, pod: str, command: list[str], filename: str) -> None:
        target = self.directory / filename
        partial = target.with_name(target.name + ".partial")
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            result = subprocess.run(
                self.prefix + ["exec", pod, "--", *command],
                stdout=output,
                stderr=subprocess.PIPE,
                check=False,
                timeout=600,
            )
            output.flush()
            os.fsync(output.fileno())
        if result.returncode:
            save(self.directory, filename + ".stderr", result.stderr)
            raise RuntimeError("Capture failed; partial output is not a valid backup")
        os.link(partial, target)
        partial.unlink()

    def bindings(self) -> list[dict]:
        result = []
        for name in [
            "energy-rag-data",
            "postgres-data",
            "energy-rag-data-nfs-v1",
            "postgres-data-mp-v1",
            "postgres-backups-nfs-v1",
        ]:
            claim = self.get("pvc", name)
            if name in ("energy-rag-data", "postgres-data"):
                original = load(self.directory, f"original-pvc-{name}.json")
                if (claim["metadata"]["uid"], claim["spec"]["volumeName"]) != (
                    original["metadata"]["uid"],
                    original["spec"]["volumeName"],
                ):
                    raise ValueError("Original rollback storage was replaced")
            volume = self.get("pv", claim["spec"]["volumeName"])
            result.append(validate_binding(claim, volume, name == "postgres-data-mp-v1"))
        return result

    def inventory(self, pod: str) -> list[dict]:
        data = self.exec(
            pod,
            [
                "sh",
                "-ceu",
                'exec psql -XqAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            ],
            INVENTORY_SQL.encode(),
        )
        return [json.loads(line) for line in data.splitlines() if line.strip()]

    def dump(self, pod: str, name: str, schema: bool = False) -> bytes:
        options = "--schema-only --no-owner --no-acl" if schema else "--format=custom"
        self.exec_file(
            pod,
            ["sh", "-ceu", f'exec pg_dump {options} -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
            name,
        )
        return (self.directory / name).read_bytes() if schema else b""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["plan", "capture", "verify", "patches", "rollback-patches", "wait-stopped"],
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--context", default="k3s-heaven")
    parser.add_argument(
        "--pg-pod",
        default="postgres-mp-restore",
        help="Target pod, or auto for the ready production PostgreSQL pod",
    )
    parser.add_argument("--app", choices=["api", "postgres"], default="api")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--no-post-cutover-writes", action="store_true")
    parser.add_argument("--verification-label", default="restored")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,48}", args.verification_label):
        raise ValueError("Invalid verification label")
    directory = private_directory(args.directory, create=args.command == "plan")
    cluster = Cluster(args.context, directory)
    if args.command == "plan":
        for name, expected in (("api", API_IMAGE), ("postgres", PG_IMAGE)):
            pod = cluster.pod(name)
            actual = next(
                c["imageID"] for c in pod["status"]["containerStatuses"] if c["name"] == name
            )
            if actual.split("@")[-1] != expected.split("@")[-1]:
                raise ValueError(
                    "Deployed image changed; resolve its matching architecture index again"
                )
        for kind, names in {
            "deployment": ["api", "postgres"],
            "service": ["api", "postgres"],
            "pvc": ["energy-rag-data", "postgres-data"],
            "secret": ["energy-rag-secrets"],
        }.items():
            for name in names:
                save(directory, f"original-{kind}-{name}.json", cluster.get(kind, name))
        save(
            directory,
            "plan.json",
            {"format_version": 1, "api_image": API_IMAGE, "postgres_image": PG_IMAGE},
        )
    elif args.command == "wait-stopped":
        deadline = time.monotonic() + args.timeout
        while True:
            deployment = cluster.get("deployment", args.app)
            original = load(directory, f"original-deployment-{args.app}.json")
            if (
                deployment["metadata"]["uid"] != original["metadata"]["uid"]
                or deployment["spec"].get("replicas") != 0
            ):
                raise ValueError(
                    "Wait requires the original deployment deliberately scaled to zero"
                )
            active = [
                p
                for p in cluster.get("pods")["items"]
                if p["metadata"].get("labels", {}).get("app") == args.app
                and p["status"].get("phase") not in ("Succeeded", "Failed")
            ]
            if not active and deployment.get("status", {}).get("replicas", 0) == 0:
                break
            if time.monotonic() >= deadline:
                raise ValueError("Deployment did not fully stop before the deadline")
            time.sleep(2)
    elif args.command == "capture":
        deployment = cluster.get("deployment", "api")
        if (
            deployment["spec"].get("replicas") != 0
            or deployment.get("status", {}).get("replicas", 0) != 0
        ):
            raise ValueError("Pause the API before the final migration capture")
        if any(
            p["metadata"].get("labels", {}).get("app") == "api"
            and p["status"].get("phase") not in ("Succeeded", "Failed")
            for p in cluster.get("pods")["items"]
        ):
            raise ValueError("An API pod is still terminating or running")
        pod = cluster.pod("postgres")
        save(directory, "volume-bindings.json", cluster.bindings())
        name = pod["metadata"]["name"]
        before = cluster.inventory(name)
        assert_no_sessions(before)
        source_data = cluster.exec(
            "energy-rag-data-migration", ["python", "-c", DATA_MANIFEST_CODE, "/source"]
        )
        save(directory, "api-data-manifest.json", source_data)
        cluster.exec_file(
            "energy-rag-data-migration",
            ["tar", "-C", "/source", "-czf", "-", "."],
            "api-data.tar.gz",
        )
        if source_data != cluster.exec(
            "energy-rag-data-migration", ["python", "-c", DATA_MANIFEST_CODE, "/source"]
        ):
            raise ValueError("API data changed during capture")
        cluster.dump(name, "database.dump")
        schema = cluster.dump(name, "database-schema.sql", schema=True)
        after = cluster.inventory(name)
        assert_no_sessions(after)
        check_inventory(before, after)
        if cluster.get("pod", name)["metadata"]["uid"] != pod["metadata"]["uid"]:
            raise ValueError("Source database pod changed during capture")
        save(directory, "database-inventory.json", before)
        save(
            directory,
            "capture.json",
            {
                "complete": True,
                "schema_sha256": schema_hash(schema),
                "dump_sha256": file_hash(directory / "database.dump"),
                "api_archive_sha256": file_hash(directory / "api-data.tar.gz"),
            },
        )
    elif args.command == "verify":
        receipt = load(directory, "capture.json")
        if receipt.get("complete") is not True:
            raise ValueError("Capture is incomplete")
        if (
            file_hash(directory / "database.dump") != receipt["dump_sha256"]
            or file_hash(directory / "api-data.tar.gz") != receipt["api_archive_sha256"]
        ):
            raise ValueError("Private backup bytes changed")
        if cluster.bindings() != load(directory, "volume-bindings.json"):
            raise ValueError("A source or destination PVC/PV was replaced")
        if args.pg_pod == "auto":
            args.pg_pod = cluster.pod("postgres")["metadata"]["name"]
        after = cluster.inventory(args.pg_pod)
        assert_no_sessions(after)
        check_inventory(load(directory, "database-inventory.json"), after)
        schema = cluster.dump(args.pg_pod, f"{args.verification_label}-schema.sql", schema=True)
        if schema_hash(schema) != receipt["schema_sha256"]:
            raise ValueError("Restored schema differs")
        target = json.loads(
            cluster.exec(
                "energy-rag-data-migration", ["python", "-c", DATA_MANIFEST_CODE, "/target/data"]
            )
        )
        if target != load(directory, "api-data-manifest.json"):
            raise ValueError("Restored API data differs")
        save(
            directory,
            "verified.json"
            if args.verification_label == "restored"
            else f"verified-{args.verification_label}.json",
            {
                "complete": True,
                "database_pod": args.pg_pod,
                "tables": sum(row.get("kind") == "table" for row in after),
                "api_files": len(target),
            },
        )
    else:
        if (
            args.command == "patches"
            and load(directory, "verified.json").get("complete") is not True
        ):
            raise ValueError("Verify both restored data sets before generating cutover patches")
        if args.command == "rollback-patches" and not args.no_post_cutover_writes:
            raise ValueError(
                "A rollback to old storage would lose newer writes; reverse-migrate them first"
            )
        if cluster.bindings() != load(directory, "volume-bindings.json"):
            raise ValueError("A source or destination PVC/PV was replaced")
        if any(
            p["metadata"]["name"] == "postgres-mp-restore"
            and p["status"].get("phase") not in ("Succeeded", "Failed")
            for p in cluster.get("pods")["items"]
        ):
            raise ValueError(
                "Stop the isolated restore database before starting production on its PVC"
            )
        for name in CLAIMS:
            current = cluster.get("deployment", name)
            original = load(directory, f"original-deployment-{name}.json")
            if current["metadata"]["uid"] != original["metadata"]["uid"]:
                raise ValueError("Production deployment was replaced")
            service = cluster.get("service", name)
            service_before = load(directory, f"original-service-{name}.json")
            if (service["metadata"]["uid"], service["spec"]["clusterIP"]) != (
                service_before["metadata"]["uid"],
                service_before["spec"]["clusterIP"],
            ):
                raise ValueError("Service identity changed; preserve fixed client addresses")
            patch = (
                cutover_patch(current, name)
                if args.command == "patches"
                else rollback_patch(current, original)
            )
            save(directory, f"{args.command}-{name}.json", patch)
    print(json.dumps({"completed": True, "operation": args.command, "cluster_mutations": False}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, KeyError, StopIteration):
        print(
            "Migration preparation failed; inspect the private evidence and cluster state.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
