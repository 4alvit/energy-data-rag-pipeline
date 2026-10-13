# FCC Actions listener on mp

The repository-scoped listener for `4alvit/iot-project-builder-profile` runs on
mp as `mp-fcc-k3s`, with `self-hosted,fcc,mp` custom labels and Linux/X64 system
labels. Its existing scheduled profile workflow matches `self-hosted,fcc`.
The work directory is disposable `emptyDir`; this listener needs no NFS PVC.
The existing ACCESS_TOKEN Secret reference is preserved and never exported to Git.

## Guarded migration

Pre-pull the exact reviewed multi-architecture image index on mp before stopping
any listener. Verify that index matches the original running image and has an
amd64 manifest; a mutable tag is not a reliable rollback reference. Keep the
original index pinned during both migration and rollback.

Capture the Deployment and current runner metadata privately. Confirm the one
original listener is online and idle; remove its `fcc` label to prevent new jobs
matching, then repeat the idle check before the Recreate rollout. If the idle
check fails, restore that label and stop the migration. Capture any historical
terminal pods belonging to this Deployment and remove only those exact terminal
UIDs/resourceVersions if they prevent a Recreate rollout.

Use a UID/resourceVersion/full-spec guarded JSON patch changing only the hostname
selector, runner name/labels and pinned image reference. The live deployment
predates the recovery manifest's hardening: do not apply the full manifest as a
placement change. Preserve current environment/Secret references, volumes,
resource limits, replica count and all other pod settings. Wait for the new pod
to be Ready and require the intended node, image identity, zero restarts and an
online GitHub runner with Linux/X64/fcc/mp labels. Pod readiness alone does not
prove GitHub registration.

Run the repository's manual **Validate FCC runner** workflow after the new
listener is online. It performs scratch-file, FCC TCP readiness and GitHub HTTPS
checks without generating a profile or invoking the LLM. Record the job's actual
runner name and successful conclusion. Verify the old listener is stopped and
its old registration is gone or lacks the routing label.

For rollback, first drain the new listener using the same label/idle gate.
Restore the captured h7 placement/name/labels while keeping the original image
index pinned; wait for the original listener to register and pass checks. If an
image pull exceeds the maintenance budget, inspect the resulting pod and
registration before retrying: an uncertain rollout result is not proof that no
listener started. Do not delete active jobs or change their limits to accelerate
the migration.

## Cache placement and runtime scan costs

Package caches use `/runner-cache` (`XDG_CACHE_HOME`, `PIP_CACHE_DIR`, and
`UV_CACHE_DIR`); action tool installations use `/opt/hostedtoolcache`
(`RUNNER_TOOL_CACHE` and `AGENT_TOOLSDIRECTORY`). Each path is a separate
disk-backed `emptyDir` with a 16 GiB size limit, not memory-backed storage. These
caches survive jobs and container restarts within a pod, but are disposable when
the pod is replaced, just like the old writable-layer caches. The next job may
download dependencies again. Kubernetes checks these size limits asynchronously;
they are eviction thresholds rather than instantaneous filesystem quotas.

This removes large cache trees from containerd's frequent writable-snapshot walks.
Kubelet still measures volume usage, normally at a one-minute interval; the change
reduces repeated scans rather than eliminating all disk accounting. The companion
host configuration sets the remaining containerd snapshot scans to 60 seconds.

The live runner can predate the recovery manifest's non-root hardening. To add
only caches, capture a fresh Deployment JSON in a private operator directory and
run `python3 scripts/fcc_runner_cache_patch.py deployment.json cache.patch.json`.
The generated patch tests UID/resourceVersion, preserves the current image,
security settings, resources, work volume, and credentials, and changes only the
two cache volumes/mounts and five cache environment variables. No API calls or
rollout are performed by the generator. The generator rejects cache volumes
mounted at unrelated paths, including in sidecars and init containers. Do not
apply the full recovery manifest as a cache-only update.

Inspect all workflows targeting this listener, including dynamic labels from
repository variables. Remove enough custom routing labels to prevent new jobs
matching and confirm on GitHub that the listener remains online and idle before
applying the patch with `kubectl patch --type=json --patch-file`. Removing only
`fcc` is sufficient only when every matching job requires that label. A busy
listener must finish first. Keep `Recreate` and one replica
to avoid duplicate runner registration. After rollout, require Ready, online,
zero restarts, writable cache paths, and `pip cache dir`/`uv cache dir` resolving
inside `/runner-cache`. Restore the intended routing labels, then run **Validate
FCC runner** and verify its actual runner name; that workflow itself requires
the `fcc` and `mp` labels. Do not copy or delete files from an active
runner's writable layer. Rollback uses the captured original cache-related fields
after the same idle gate; never replay an old resourceVersion blindly.
