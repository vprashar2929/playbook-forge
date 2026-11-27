# playbook-forge

Ansible playbooks and lab environments for designing, testing, and refining infrastructure automation.

The first pilot runs a real offline Redis RPM upgrade on a Rocky Linux 9 VM. Redis and a single-node Kafka KRaft broker run as systemd services. The Engineer launches the patch from the Mac. The playbook checks the host, installs the approved RPM, optionally reboots, and waits for both services to recover. The same patch entry point accepts a Dev/Test inventory.

## Start the lab on macOS

Install Lima 2.x and Python 3.12. With Homebrew, run `brew install lima python@3.12`. Run the following from the checkout.

```sh
make lab
make ready
make patch
make patch
make stop
```

- `make lab` creates a project-local Python environment and a Lima VM called `forge-lab` with two CPUs, 4 GiB RAM and a 25 GiB virtual disk. Ansible installs standalone Redis 6.2.22, Kafka 4.4.0 and Java 21. Setup downloads public artifacts, stages both Redis RPMs in the guest and verifies their checksums. Reserve this VM name for the lab.
- `make ready` checks identity, package and running versions, platform health, free space, approved RPM digests and offline transaction resolution. The default patch entry point runs this read-only assessment.
- `make patch` upgrades Redis to 6.2.24 from the staged RPM with all DNF repositories disabled. The lab inventory requests a guest reboot. Ansible verifies the exact package, the running Redis version and a Kafka metadata leader. The second run should report `changed=0`.
- `make stop` releases the VM's memory and preserves its disk. A later `make lab` starts it and preserves the installed Redis version. To reset a disposable lab to the original baseline, stop it, run `limactl delete forge-lab` to erase its disk, then run `make lab`. To inspect either service, use `limactl shell forge-lab` and run `systemctl status redis kafka`.

The lab uses Lima's generated SSH configuration. The Mac's home directory is unmounted and the guest services listen locally. The initial downloads require internet access. The patch and rollback transactions use guest-local RPMs. Each patch invocation writes a separate controller log under `.run/`, including failed and unreachable tasks.

## Exercise rollback

On a freshly provisioned lab **before the first successful patch**, run the drill.

```sh
make rollback-drill
```

The drill installs a temporary systemd start check which rejects only the target Redis version. It invokes the regular patch playbook, confirms the old version is serving again, verifies Kafka, and removes the temporary fault. The patch run returns failure by design and leaves a durable host hold. The drill succeeds only when it observes the expected recovery and hold. A subsequent patch attempt must stop at that hold.

Review the controller log and verify the guest before releasing the lab hold.

```sh
limactl shell forge-lab -- rpm -q redis
limactl shell forge-lab -- redis-cli ping
limactl shell forge-lab -- sudo rmdir /var/lib/playbook-forge-redis.hold
make patch
```

A failed or interrupted RPM install, failed reboot, unreachable host or unverified rollback requires Engineer review. On a held host, use its console and the controller log to reconcile the installed build and platform state before retrying. An approved package rollback restores the earlier binary. Data and configuration recovery require their own tested procedures.

## Use the patch playbook in Dev/Test

Run `make tools` on the control node (Python 3.12–3.14). The lab setup and rollback drill are specific to the marked disposable VM. To patch an existing host, pass its inventory to the patch entry point.

```sh
./scripts/run-patch -i /path/to/dev/hosts.yml --limit redis-dev-01
./scripts/run-patch -i /path/to/dev/hosts.yml --limit redis-dev-01 -e patch_apply=true
```

Create a `patch_targets` inventory group. Start with a single standalone EL9 Redis host using DNF, `needs-restarting`, systemd and a working Ansible SSH and privilege-escalation path through reboot. Set the following in your private inventory, using [the lab variables](inventories/lab/group_vars/all.yml) as an example.

| Variable | What to supply |
| --- | --- |
| `expected_hostname` | The short hostname reported by the guest. |
| `redis_stage`, `redis_from`, `redis_to` | Root-controlled staging directory and the approved starting and target RPM version-release strings. Prestage `redis-<version-release>.<architecture>.rpm` under its expected filename. Provision dependencies and trusted package-signing keys through your usual process. |
| `redis_checksums` | SHA-256 digests from the approved source, keyed by architecture and version-release. |
| `patch_reboot` | Whether this change calls for a host reboot. Default is a Redis service restart. An outstanding host reboot outside the change holds the run. |
| `patch_rollback_approved` | Defaults to false. Enable only after testing this exact downgrade against your persistence format, configuration and data, and staging the prior RPM. |
| `redis_cli_args`, `redis_password` | Optional host, port, TLS and ACL arguments for the local Redis CLI. Supply passwords separately through Ansible Vault or the environment's secrets mechanism. |
| `kafka_bootstrap`, `kafka_bin`, `kafka_command_config` | Configure the colocated KRaft broker's endpoint and CLI directory to enable Kafka verification. An optional guest-side client properties file supplies TLS or SASL settings. |

The pilot updates the Redis RPM. Kafka is a second platform health check. The Redis role check requires a standalone primary with zero replicas. A replication group, Redis Cluster, or Kafka binary upgrade needs its own topology checks, sequencing and recovery tests before onboarding. The lab versions are synthetic fixtures. Set Dev/Test builds and approvals independently.

Hosts run one at a time. A failure stops the selected group. An exclusive host hold prevents overlapping changes to that host and survives a lost connection. Schedule one change window per service group. Keep credentials, real inventories and run logs outside the public repository.

## Contribute

[Lab setup](lab/setup.yml) owns provisioning. [Patching](playbooks/patch.yml) owns the change transaction. [Health checks](playbooks/tasks/health.yml) are used before and after the change and after recovery. For a change to the transaction, exercise a clean patch, a second run and the [rollback drill](lab/rollback-drill.yml) and include their results in the pull request.
