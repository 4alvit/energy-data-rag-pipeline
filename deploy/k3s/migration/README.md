# Energy RAG: h7 → mp, preserving application and database versions

This is a maintenance migration of **API and PostgreSQL only**. It does not apply
the entire kustomization: the live installation predates other hardening changes
in Git. Minimal JSON patches preserve all unrelated live container settings.
MCP, FCC, the runner, Secrets, and Services are not changed by this procedure.

## Storage and consistency

- API `/data` moves to `energy-rag-data-nfs-v1`, subdirectory `data`, on Synology.
- PostgreSQL moves by **logical `pg_dump`/`pg_restore`**, from ARM64 to AMD64, into
  `postgres-data-mp-v1` on local `mp` storage. Never copy the old PGDATA directory
  across architectures. The initial source is PostgreSQL 16.15 / vector 0.8.6.
- Both deployed multi-architecture image indexes are pinned in the manifests.
- PostgreSQL probes receive a bounded 5-second timeout where the old default was
  1 second; commands, delays, periods, and failure thresholds stay unchanged.
  The rehearsal observed exec startup timeouts under mp CPU load while the
  database stayed healthy. Confirm stable readiness and real query latency after
  migration, rather than treating a wider timeout as database acceptance.
- A new daily 10:20 UTC logical backup CronJob writes to `postgres-backups-nfs-v1`.
  It parses the entire dump, verifies a SHA-256 readback, and publishes the
  `.sha256` completion receipt last. It
  retains at least 14 days. Dumps without that receipt are incomplete. A successful dump is not a booted restore test.
- Existing h7 `energy-rag-data` and `postgres-data` claims remain intact. Do not
  delete them or prune the base resources during the migration/observation window.
- New NFS claims use `nfs-synology-v4` with explicit `nfsvers=4.1,hard` mount
  options. The dedicated mp client export is `sync`; older client exports retain
  their existing `async` setting. PostgreSQL documentation requires a
  `hard` client mount and recommends durable server `sync` exports for live PGDATA;
  local PGDATA avoids treating the existing NFS export as a transactional disk.
  Backup readback/checksums do not establish persistence across NAS power loss.

References: [PostgreSQL logical dumps](https://www.postgresql.org/docs/16/backup-dump.html),
[PostgreSQL and NFS](https://www.postgresql.org/docs/16/creating-cluster.html#CREATING-CLUSTER-NFS).

## Before maintenance

Use a private evidence directory **outside this checkout**, with sufficient free
space for two data copies. All captured credentials/dumps stay 0700/0600 and must
never enter Git or console logs. Commands below require an operator coordinating
the approved cutover, not an unattended full-stack deploy.

Confirm `mp` is Ready/amd64 and its storage has capacity; confirm NFS mounting from
**mp and h7**, correct server/export/UID permissions, and required cluster/DNS/API
paths. Confirm there is no ingestion in progress and pause outside ingestion
clients. The helper refuses a final capture until the API is fully stopped and
PostgreSQL has no other client sessions. Retry with a fresh evidence directory
when a capture fails; partial files are not valid backups.

The PostgreSQL PDB prevents the observed five-minute voluntary descheduler
restarts. It does not prevent the intentional scale operations below.

```bash
set -euo pipefail
export RAG_MIGRATION_DIR=/absolute/private/path/energy-rag-migration
python3 scripts/mp_migration.py plan --directory "$RAG_MIGRATION_DIR"
kubectl --context k3s-heaven apply -f deploy/k3s/postgres-pdb.yaml
kubectl --context k3s-heaven get storageclass nfs-synology-v4
kubectl --context k3s-heaven apply -f deploy/k3s/mp-storage.yaml
kubectl --context k3s-heaven apply -f deploy/k3s/migration/helpers.yaml
kubectl --context k3s-heaven -n energy-rag wait --for=condition=Ready pod/energy-rag-data-migration pod/postgres-mp-restore pod/energy-rag-api-preflight --timeout=1200s
```

The restore pod has `app=postgres-migration`, never the production Service label.
Its new database initializes without `postgres-init`; the logical dump provides
the actual source schema. The data helper mounts the old API claim read-only and
runs with the observed source UID 1000/GID 999. It does not change source ownership.
Check the new claims are Bound to the intended PVs before pausing the API; the
capture/verify helpers also pin their PVC/PV UIDs and reject replacement. Set
the new local PostgreSQL PV reclaim policy to `Retain` using a patch guarded by
its captured UID/resourceVersion before any final capture; the helper requires
this policy. Capture historical Failed/Succeeded API/PostgreSQL pods before
removing only those terminal pods with matching ReplicaSet ownership and
UID/resourceVersion deletion preconditions. The wait helper ignores terminal
pods, while production pod discovery requires one Running, Ready, nonterminating
pod; neither operation sweeps unrelated workloads.

## Capture and restore to isolated storage

```bash
set -euo pipefail
kubectl --context k3s-heaven -n energy-rag scale deployment/api --replicas=0
python3 scripts/mp_migration.py wait-stopped --directory "$RAG_MIGRATION_DIR" --app api
python3 scripts/mp_migration.py capture --directory "$RAG_MIGRATION_DIR"
# Both source tar and source file hashes were captured while the API was stopped.
kubectl --context k3s-heaven -n energy-rag exec energy-rag-data-migration -- mkdir -m 700 /target/data
kubectl --context k3s-heaven -n energy-rag exec -i energy-rag-data-migration -- tar --no-same-owner -C /target/data -xzf - < "$RAG_MIGRATION_DIR/api-data.tar.gz"
kubectl --context k3s-heaven -n energy-rag exec -i postgres-mp-restore -- sh -ceu 'exec pg_restore --exit-on-error --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$RAG_MIGRATION_DIR/database.dump"
python3 scripts/mp_migration.py verify --directory "$RAG_MIGRATION_DIR"
```

Verification compares PostgreSQL version/encoding/collation, extensions,
all non-system table owners and row counts, normalized schema SHA-256, and every
API data file's bytes/SHA-256. No query/embedding/ingestion endpoint is invoked.

Copy the private evidence to a new directory on the dedicated NAS backup PVC
before stopping the old PostgreSQL. `migration-evidence` must not already exist:

```bash
set -euo pipefail
kubectl --context k3s-heaven -n energy-rag exec energy-rag-data-migration -- mkdir -m 700 /backups/migration-evidence
# pipefail makes either half fail the command; this archive contains credentials.
tar -C "$RAG_MIGRATION_DIR" -cf - . | kubectl --context k3s-heaven -n energy-rag exec -i energy-rag-data-migration -- tar --no-same-owner -C /backups/migration-evidence -xf -
# Read back the two large backup files and compare checksums without printing data.
for file in database.dump api-data.tar.gz; do
  kubectl --context k3s-heaven -n energy-rag exec energy-rag-data-migration -- cat "/backups/migration-evidence/$file" | shasum -a 256 > "$RAG_MIGRATION_DIR/$file.nas-sha256"
  test "$(cut -d ' ' -f 1 "$RAG_MIGRATION_DIR/$file.nas-sha256")" = "$(shasum -a 256 "$RAG_MIGRATION_DIR/$file" | cut -d ' ' -f 1)"
done
```

## Cutover

Stop the isolated restored PostgreSQL and the original PostgreSQL. Never run two
PostgreSQL processes against the new PVC. Generate patches only after both
production Deployments have desired replicas zero. Patch files include UID and
resourceVersion tests; regenerate/review if anything changes before application.
Neither patch modifies a Service, including the existing database ClusterIP used
by the API's credential. The PDB remains to protect the replacement pod.

```bash
set -euo pipefail
kubectl --context k3s-heaven -n energy-rag delete pod/postgres-mp-restore --wait=true --timeout=180s
kubectl --context k3s-heaven -n energy-rag scale deployment/postgres --replicas=0
python3 scripts/mp_migration.py wait-stopped --directory "$RAG_MIGRATION_DIR" --app postgres
python3 scripts/mp_migration.py patches --directory "$RAG_MIGRATION_DIR"
kubectl --context k3s-heaven -n energy-rag patch deployment/postgres --type=json --patch-file "$RAG_MIGRATION_DIR/patches-postgres.json"
kubectl --context k3s-heaven -n energy-rag rollout status deployment/postgres --timeout=300s
# PostgreSQL must pass the same complete checks before starting API writes.
python3 scripts/mp_migration.py verify --directory "$RAG_MIGRATION_DIR" --pg-pod auto --verification-label production-before-api
kubectl --context k3s-heaven -n energy-rag patch deployment/api --type=json --patch-file "$RAG_MIGRATION_DIR/patches-api.json"
kubectl --context k3s-heaven -n energy-rag rollout status deployment/api --timeout=600s
kubectl --context k3s-heaven -n energy-rag apply -f deploy/k3s/postgres-backup.yaml
kubectl --context k3s-heaven -n energy-rag create job --from=cronjob/postgres-logical-backup postgres-logical-backup-migration-check
kubectl --context k3s-heaven -n energy-rag wait --for=condition=complete job/postgres-logical-backup-migration-check --timeout=1800s
```

Check `/health` and `/health/ready` using a read-only GET through the established
API Service. Confirm unchanged Service UID/IP, expected new PV UIDs, pod node and
pinned imageIDs. Check the real backup Job succeeded and its dump is present on
NAS. Save this evidence privately. Remove only the three named temporary helper
pods after observation; retain old PVCs and the migration evidence.

## Rollback boundary

Before the replacement API is allowed to write, stop both new Deployments, wait
for their pods to disappear, and generate UID/resourceVersion-tested rollback
patches. They restore the saved live PodSpecs and original replica counts while
keeping `Recreate` and the protective PDB. Services and all PVCs stay unchanged.

```bash
set -euo pipefail
kubectl --context k3s-heaven -n energy-rag scale deployment/api deployment/postgres --replicas=0
python3 scripts/mp_migration.py wait-stopped --directory "$RAG_MIGRATION_DIR" --app api
python3 scripts/mp_migration.py wait-stopped --directory "$RAG_MIGRATION_DIR" --app postgres
python3 scripts/mp_migration.py rollback-patches --directory "$RAG_MIGRATION_DIR" --no-post-cutover-writes
kubectl --context k3s-heaven -n energy-rag patch deployment/postgres --type=json --patch-file "$RAG_MIGRATION_DIR/rollback-patches-postgres.json"
kubectl --context k3s-heaven -n energy-rag rollout status deployment/postgres --timeout=300s
kubectl --context k3s-heaven -n energy-rag patch deployment/api --type=json --patch-file "$RAG_MIGRATION_DIR/rollback-patches-api.json"
```

**After any new writes, old storage is stale.** Do not use that flag. Pause the
API, take a new consistent logical dump and API-data backup from the replacement,
and reverse-migrate/verify those writes before switching back. An automatic
rollback to the old data would silently lose them, so this tooling refuses to
assume it is safe.
