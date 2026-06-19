# CEP demo — convenience targets. See docs/QUICKSTART.md for details.
SHELL := /bin/bash
S ?= dist_blackhole          # default scenario for `make sim`

.PHONY: gen sidecar sim test report up down clab clab-down nautobot zabbix clean

gen:                ## regenerate topology.json + cep-demo.clab.yml
	python3 topology/generate_topology.py
	python3 topology/emit_containerlab.py

sidecar:            ## run the CEP sidecar locally (FastAPI :8080)
	cd sidecar && TOPOLOGY_FILE=../topology/topology.json \
		uvicorn app:app --host 0.0.0.0 --port 8080

sim:                ## fire a scenario: make sim S=ring_protected
	python3 simulator/simulate.py --scenario $(S)

test:               ## run the correlation test suite
	python3 -m pytest tests/ -q

report: test        ## render the rich HTML test report
	python3 reporting/render_report.py
	@echo "open reporting/report.html"

up:                 ## bring up sidecar + webui + prometheus + grafana
	docker compose up -d --build

up-full-lab:        ## CEP stack on digital-twin (needs Nautobot + Zabbix running)
	docker compose -f docker-compose.yml -f docker-compose.full-lab.yml up -d --build

down:               ## tear the compose stack down
	docker compose down

post-deploy:        ## discover clab IPs + auto-seed Nautobot and Zabbix
	python3 topology/post_deploy.py

clab:               ## deploy the 32-node FRR lab (needs containerlab + sudo)
	sudo containerlab deploy -t topology/cep-demo.clab.yml

clab-down:          ## destroy the lab
	sudo containerlab destroy -t topology/cep-demo.clab.yml

faultlab-gen:       ## generate the FRR thin-slice (real fault injection)
	python3 faultlab/generate_faultlab.py

faultlab-up:        ## deploy the thin slice (needs containerlab + sudo)
	cd faultlab && sudo containerlab deploy -t faultlab.clab.yml

faultlab-mon:       ## run the detection agent (posts real faults to the sidecar)
	python3 faultlab/monitor.py

faultlab-inject:    ## inject a real fault: make faultlab-inject S=spur_cascade
	python3 faultlab/inject.py scenario $(S)

faultlab-down:      ## destroy the thin slice
	cd faultlab && sudo containerlab destroy -t faultlab.clab.yml --cleanup

trapd:              ## run the SNMP trap receiver (path B), :1162 unprivileged
	python3 trapsim/trapd.py --port 1162

trap:               ## send a trap: make trap T=linkDown D=acc-a1 I=2
	python3 trapsim/send_trap.py $(T) --device $(D) --ifindex $(I) --target 127.0.0.1:1162

nautobot:           ## seed Nautobot (needs NAUTOBOT_URL + NAUTOBOT_TOKEN)
	python3 nautobot/populate_nautobot.py

zabbix:             ## seed Zabbix (needs ZBX_URL + ZBX_TOKEN)
	python3 zabbix/populate_zabbix.py

clean:              ## remove generated artifacts
	rm -rf **/__pycache__ .pytest_cache reporting/results.json reporting/report.html
