# playbook-forge

This pilot rehearses an approved Enterprise Linux 9 **OS patch window**. The Mac runs Ansible over SSH to two dedicated Rocky Linux VMs. One hosts Redis and the other hosts a Kafka broker/controller. The playbook patches the operating system on one host at a time, verifies the running kernel and waits for that host's platform to recover.

## Run the lab

Install Lima 2.x and Python 3.12 on macOS (`brew install lima python@3.12`). Run the following from the checkout.

```sh
make lab
make ready
make patch
make patch
make stop
```

`make lab` creates `forge-redis` and `forge-kafka` (two CPUs and 3 GiB default memory each). It builds a local DNF repository on each guest from vendor-signed kernel RPMs and gives the package set a **synthetic lab advisory**. The lab uses the distribution's Redis package and pins Kafka 3.9.1. It uses a loopback plaintext Kafka listener; the private inventory supplies client-side TLS/SASL settings where required. Initial setup uses the internet. The window uses only this guest-local repository. Lima provides SSH, and the services listen on guest loopback. Earlier one-VM checkouts used `forge-lab`; the new targets are independent of it.

`make ready` runs the same prechecks and DNF solver used for patching. `make patch` applies the approved transaction. The repeat run should report both hosts already current and healthy. `make stop` preserves the VM disks. To reset a disposable lab, stop the VMs, delete each with `limactl delete NAME`, then run `make lab`.

## What the Engineer's patch run does

| Manual step | Playbook behavior |
| --- | --- |
| Confirm host, role and scope | Match hostname, EL9, service role and topology. Match the inventory IP when supplied (required in cluster mode). Require a change ID, recovery reference, advisory list, approved repositories and exact target package builds. |
| Establish a baseline | Capture running/default kernel, boot ID, RPM inventory, failed units, free space and role health. Redis checks liveness, replication, persistence and key count. Kafka checks the expected KRaft voters, leader, follower lag, unavailable partitions, under-replicated partitions and partitions below minimum ISR. |
| Preview, review and stage | Resolve the advisory-filtered DNF4 upgrade against the approved content. Compare every incoming build with the approved missing builds. Reject unexpected package operations, keep old kernels and stage and signature-check RPMs before stopping a service. A separate readiness run exposes the proposed transaction for change review. |
| Prepare and patch | Acquire a persistent host hold. Archive and compare the inventory-listed configuration files. Run topology-specific maintenance preparation where applicable. Stop only the assigned service and require a clean stop. Kafka exit 143 additionally requires a graceful completion message in this stop’s journal and no fatal error or timeout. Recheck the cached transaction, install and record its DNF history ID. |
| Reboot and verify | Check old and new boot entries, select the approved kernel, reboot and reconnect when required. A package-only change that needs no reboot restarts the stopped service. Set `patch_force_reboot` if an active change window explicitly calls for reboot. Verify `uname -r`, installed targets, zero remaining scoped work, automatic service startup, failed units and reboot status. Sample role health twice across the observation interval before advancing. |
| Close out | Save per-host before/after evidence and a controller summary. An unreachable or unvisited host stays unverified. A failed or interrupted change holds the rollout for the Engineer. Authenticated rescanning is a separate verification step. |

The lab intentionally permits an outage of each single instance. Host separation demonstrates that maintenance on Redis can stop before Kafka changes. Zero-downtime failover requires peers.

## Rehearse recovery

On a baseline Redis guest, run `make rollback-drill` **before** the first successful patch. The drill prevents Redis from starting under the target kernel, invokes the real two-host patch run and verifies that Kafka retained both its boot ID and installed kernel list. It runs the single-host recovery playbook and removes the test fault. The recovered host stays held.

The recovery play requires a reachable, explicitly approved single-node host, a matching held change, the target kernel currently running and a distinct retained previous boot entry. It boots the previous kernel and repeats platform checks. Installed RPMs, service data and configuration have separate recovery procedures. An uncertain transaction, inaccessible host or cluster recovery requires reconciliation over the management console.

After reviewing the lab evidence, check the running kernel and Redis, then archive the hold before retrying.

```sh
limactl shell forge-redis -- uname -r
limactl shell forge-redis -- redis-cli ping
limactl shell forge-redis -- sudo mv -T /var/lib/playbook-forge-os.hold "/var/backups/playbook-forge/reviewed-$(date +%s)"
make patch
```

## Run against an existing Dev/Test inventory

Keep client inventory, credentials, topology procedures and real advisory manifests outside this public repository. Use `make tools` to install the pinned controller environment (Python 3.12–3.14). On a disconnected control node, install the pinned Python dependency from your internal package mirror or wheelhouse. Only lab creation uses Lima. The existing Dev/Test hosts need system Python with DNF4/RPM bindings, grubby, needs-restarting, platform CLIs, persistent SSH access through reboot and approved privilege escalation.

```sh
./scripts/run-patch -i /path/to/dev/hosts.yml --limit approved_group
./scripts/run-patch -i /path/to/dev/hosts.yml --limit approved_group -e patch_apply=true
./scripts/run-patch --recover -i /path/to/dev/hosts.yml --limit one_held_host
```

Define `patch_targets` with role groups `redis` and `kafka`. Use [the synthetic lab inputs](inventories/lab/group_vars/all.yml) as the inventory contract. Set `patch_repos` to the approved, published content-view repository IDs, `patch_advisories` to that host's findings, and `patch_targets_nevra` and `patch_kernel` to the reviewed builds. Nonzero epochs use `name-epoch:version-release.arch`. Supply a frozen repository view and pre-enrolled signing keys. The package resolver rejects any dependency outside the approved builds; review and add a legitimate dependency to the manifest before proceeding. A private snapshot/restore record belongs in `recovery_reference`. The playbook makes a configuration archive on the host; arrange an independent backup and console through the site's existing process.

Set `patch_role`, `expected_hostname`, `config_paths`, `patch_change_id` and `patch_topology` per host or group. Use `redis_cli_args` for the local Redis listener/TLS/ACL and a vaulted `redis_password` if required. Set `kafka_bin`, `kafka_bootstrap`, `kafka_voters` and optional persistent guest-side `kafka_command_config` for the actual listener and credentials. Set `allowed_failed_units` only for reviewed exceptions. One designated control node and one window per service group are required; the runner serializes windows within the checkout.

### Clustered Dev/Test

A hostname list establishes service placement. It cannot establish a Redis primary/replica relationship, Kafka voting membership, or acceptable write interruption. Set `patch_topology: cluster` for a real Redis Cluster or multi-voter KRaft deployment. Supply the site's reviewed Ansible tasks under `maintenance/<role>/` beside the private inventory. Readiness runs the peer precheck. Apply requires all four files before maintenance. These are site integration points; validation in this repository exercises the single-node branches.

| Phase file | Redis Cluster | Kafka KRaft |
| --- | --- | --- |
| `precheck.yml` | Query the actual primary and replicas. Check slot coverage, offsets, links, persistence and minimum replicas for writes. Select replicas first. | Verify broker membership, voter majority, replica availability and the impact of single-replica or at-minimum-ISR topics. |
| `prepare.yml` | For an approved primary change, perform planned failover on the synchronized replica. Verify the exact role exchange and accepted write impact before stopping the target. | Confirm other brokers can serve and that controller majority survives this specific stop. |
| `peers_offline.yml` | Check the surviving primary and write availability from a peer while the target is down. | From a surviving endpoint, verify controller election and the expected in-service replicas. |
| `returned.yml` | Verify the expected role and upstream, synchronization, minimum healthy replicas, all slots and stable peer membership. | Verify the specific broker rejoined, replicas caught up and the expected quorum and ISR recovered. |

The two-VM lab does not authorize a client change. A separate client-side readiness run must establish the real access path, topology and approved contents. Independent service groups can be selected with `--limit`; the first failure stops the selected window.

## Evidence and contributions

Each invocation prints its private `.run/window-…` directory. It contains the selected host list, Ansible log, per-host outcome, RPM inventories, consolidated `summary.json` and a `SHA256SUMS` manifest. Keep this evidence on storage accessible to the Engineer independently of the patched hosts.

[Lab provisioning](lab/setup.yml), [OS patching](playbooks/patch.yml), [kernel recovery](playbooks/recover.yml) and [the failure drill](lab/rollback-drill.yml) are separate entry points. Exercise the lab readiness, failure, recovery, normal patch and repeat-run paths when changing the patch transaction.
