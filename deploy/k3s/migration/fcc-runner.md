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
