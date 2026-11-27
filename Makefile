PYTHON ?= python3.12
VENV := .venv
PLAY := $(VENV)/bin/ansible-playbook
LAB := -i inventories/lab/hosts.yml
INSTANCE := forge-lab

.PHONY: tools lab ready patch rollback-drill stop
tools: $(VENV)/.installed

$(VENV)/.installed: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -r requirements.txt
	touch $@

lab: tools
	@if limactl list --format '{{.Name}}' | grep -Fxq $(INSTANCE); then \
		limactl start -y $(INSTANCE); \
	else \
		limactl start -y --name=$(INSTANCE) ./lab/lima.yaml; \
	fi
	$(PLAY) $(LAB) lab/setup.yml

ready: tools
	./scripts/run-patch $(LAB)

patch: tools
	./scripts/run-patch $(LAB) -e patch_apply=true

rollback-drill: tools
	$(PLAY) $(LAB) lab/rollback-drill.yml

stop:
	limactl stop $(INSTANCE)
