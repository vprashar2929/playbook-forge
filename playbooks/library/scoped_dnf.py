#!/usr/bin/python
"""Resolve a DNF4 advisory transaction and apply only the reviewed exact builds."""
from ansible.module_utils.basic import AnsibleModule


def nevra(pkg):
    epoch = f"{pkg.epoch}:" if int(pkg.epoch) else ""
    return f"{pkg.name}-{epoch}{pkg.version}-{pkg.release}.{pkg.arch}"


def run(module):
    import dnf
    import dnf.rpm
    import dnf.transaction as txn

    args = module.params
    mode = "plan" if module.check_mode else args["mode"]
    if not all(args[key] for key in ("repositories", "advisories", "targets")):
        module.fail_json(msg="An approved repository, advisory list and exact target builds are required.")

    with dnf.Base() as base:
        base.conf.read()
        base.conf.substitutions["releasever"] = dnf.rpm.detect_releasever("/")
        base.conf.best = True
        base.conf.installonly_limit = 0  # Preserve the running kernel and its boot entry.
        base.conf.install_weak_deps = False
        base.conf.keepcache = True
        base.conf.cacheonly = mode == "apply"
        base.init_plugins()
        base.pre_configure_plugins()
        base.read_all_repos()
        for repo in base.repos.values():
            repo.disable()
        for name in args["repositories"]:
            repo = base.repos[name]
            if not repo.gpgcheck:
                module.fail_json(msg=f"{name} must enforce RPM signature verification.")
            if mode == "plan":
                repo.metadata_expire = 0
            repo.skip_if_unavailable = False
            repo.enable()
        base.configure_plugins()
        if {repo.id for repo in base.repos.iter_enabled()} != set(args["repositories"]):
            module.fail_json(msg="Enabled DNF repositories differ from the approved content view.")
        base.fill_sack()
        available = base.sack.query().available()
        for advisory in args["advisories"]:
            if not available.filter(advisory=advisory):
                module.fail_json(msg=f"Advisory {advisory} is absent from the approved content.")
        base.add_security_filters("gte", advisory=args["advisories"])
        base.upgrade_all()
        base.resolve(allow_erasing=False)
        approved = set(args["targets"])
        installed = {nevra(p) for p in base.sack.query().installed()}
        installs = list(base.transaction.install_set)
        additions = sorted(nevra(p) for p in installs)
        removals = sorted(nevra(p) for p in base.transaction.remove_set)
        plan = dict(install=additions, replace=removals)
        # PKG_UPGRADED is the outgoing side of a normal same-name upgrade.
        allowed = {txn.PKG_INSTALL, txn.PKG_UPGRADE, txn.PKG_UPGRADED}
        if any(item.action not in allowed for item in base.transaction):
            module.fail_json(msg="DNF proposed an erase, obsoletion or downgrade. Review the window.", plan=plan)
        if set(additions) != approved - installed:
            module.fail_json(msg="Resolved transaction differs from the approved missing builds.", plan=plan,
                             missing=sorted(approved - installed))
        if mode != "plan" and plan != args["reviewed"]:
            module.fail_json(msg="The transaction changed after preview.", plan=plan)
        result = dict(plan=plan, installed=sorted(approved & installed), transaction_id=None)
        if not installs or mode == "plan":
            return result
        if mode == "stage":
            base.download_packages(installs)
        for pkg in installs:
            if not pkg.verifyLocalPkg():
                module.fail_json(msg=f"Missing or invalid cached RPM for {nevra(pkg)}.")
            status, detail = base.package_signature_check(pkg)
            if status:
                module.fail_json(msg=detail)
        if mode == "apply":
            result["transaction_id"] = base.do_transaction()
        return result


def main():
    module = AnsibleModule(argument_spec=dict(
        repositories=dict(type="list", elements="str", required=True),
        advisories=dict(type="list", elements="str", required=True),
        targets=dict(type="list", elements="str", required=True),
        mode=dict(choices=["plan", "stage", "apply"], default="plan"),
        reviewed=dict(type="dict", default={}),
    ), supports_check_mode=True)
    try:
        result = run(module)
    except Exception as exc:
        module.fail_json(msg=f"DNF transaction: {exc}")
    module.exit_json(changed=result["transaction_id"] is not None, **result)


if __name__ == "__main__":
    main()
