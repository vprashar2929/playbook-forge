PYTHON ?= python3.12
VENV := .venv
PLAY := $(VENV)/bin/ansible-playbook
LAB := -i inventories/lab/hosts.yml
INSTANCES := forge-redis forge-kafka

.PHONY: tools lab ready patch rollback-drill stop
tools: $(VENV)/.installed

$(VENV)/.installed: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -r requirements.txt
	touch $@

lab: tools
	@set -e; for vm in $(INSTANCES); do \
		if limactl list --format '{{.Name}}' | grep -Fxq "$$vm"; then limactl start -y "$$vm"; \
		else limactl start -y --name="$$vm" ./lab/lima.yaml; fi; \
	done
	$(PLAY) $(LAB) lab/setup.yml

ready: tools
	./scripts/run-patch $(LAB)

patch: tools
	./scripts/run-patch $(LAB) -e patch_apply=true

rollback-drill: tools
	$(PLAY) $(LAB) lab/rollback-drill.yml

stop:
	@set -e; for vm in $(INSTANCES); do limactl stop "$$vm"; done
