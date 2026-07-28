SHELL := /bin/bash

REL26_SCRIPT := docs/cdo08/week3/mandate20/scripts/postgres/rel26-accounting-controlled-delete-restore.sh
REL25_MSK_DEMO_SCRIPT := docs/cdo08/week3/mandate20/scripts/msk/rel25-msk-orders-replay-demo.sh
REL26_AWS_PROFILE ?= default
REL26_AWS_ACCOUNT_ID ?= 511825856493
REL26_DRILL_ID ?= rel26-$(shell date -u +"%Y%m%d")
REL26_SOURCE_RESTORE_TIMESTAMP ?= $(shell date -u -v-30M +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d "-30 minutes" +"%Y-%m-%dT%H:%M:%SZ")
REL25_MSK_AWS_PROFILE ?= default
REL25_MSK_AWS_ACCOUNT_ID ?= 511825856493
REL25_MSK_KUBE_CONTEXT ?= arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
REL25_MSK_ARCHIVE_BUCKET ?= tf4-msk-orders-archive-511825856493-us-east-1
REL25_MSK_START_TIME ?= 2026-07-27T05:00:00Z
REL25_MSK_END_TIME ?= 2026-07-27T06:00:00Z
REL25_MSK_DRILL_ID ?= rel25-$(shell date -u +"%Y%m%d")-msk-demo
REL25_MSK_TARGET_TOPIC ?= orders-replay-drill-$(REL25_MSK_DRILL_ID)
REL33_SCRIPT := docs/cdo08/week3/mandate21/scripts/rel33-az-loss-observer.sh
REL33_AWS_PROFILE ?= default
REL33_AWS_ACCOUNT_ID ?= 511825856493
REL33_KUBE_CONTEXT ?= arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
REL33_INTERVAL ?= 30
REL33_DURATION ?= 0
REL33_OUTPUT ?= artifacts/rel33/observer-$(shell date -u +"%Y%m%dT%H%M%SZ").log

.PHONY: rel25-msk-replay-demo rel26-preflight rel26-drill rel33-preflight rel33-observe

rel25-msk-replay-demo:
	AWS_PROFILE="$(REL25_MSK_AWS_PROFILE)" \
	EXPECTED_AWS_ACCOUNT_ID="$(REL25_MSK_AWS_ACCOUNT_ID)" \
	EXPECTED_KUBE_CONTEXT="$(REL25_MSK_KUBE_CONTEXT)" \
	ARCHIVE_BUCKET="$(REL25_MSK_ARCHIVE_BUCKET)" \
	START_TIME="$(REL25_MSK_START_TIME)" \
	END_TIME="$(REL25_MSK_END_TIME)" \
	RESTORE_DRILL_ID="$(REL25_MSK_DRILL_ID)" \
	TARGET_TOPIC="$(REL25_MSK_TARGET_TOPIC)" \
	bash "$(REL25_MSK_DEMO_SCRIPT)"

rel26-preflight:
	PREFLIGHT_ONLY=true \
	AWS_PROFILE="$(REL26_AWS_PROFILE)" \
	EXPECTED_AWS_ACCOUNT_ID="$(REL26_AWS_ACCOUNT_ID)" \
	REL26_DRILL_ID="$(REL26_DRILL_ID)" \
	SOURCE_RESTORE_TIMESTAMP="$(REL26_SOURCE_RESTORE_TIMESTAMP)" \
	"$(REL26_SCRIPT)"

rel26-drill:
	CONFIRM_REL26_DRILL=YES \
	AWS_PROFILE="$(REL26_AWS_PROFILE)" \
	EXPECTED_AWS_ACCOUNT_ID="$(REL26_AWS_ACCOUNT_ID)" \
	REL26_DRILL_ID="$(REL26_DRILL_ID)" \
	SOURCE_RESTORE_TIMESTAMP="$(REL26_SOURCE_RESTORE_TIMESTAMP)" \
	"$(REL26_SCRIPT)"

rel33-preflight:
	AWS_PROFILE="$(REL33_AWS_PROFILE)" \
	EXPECTED_AWS_ACCOUNT_ID="$(REL33_AWS_ACCOUNT_ID)" \
	EXPECTED_KUBE_CONTEXT="$(REL33_KUBE_CONTEXT)" \
	bash "$(REL33_SCRIPT)" preflight --output "$(REL33_OUTPUT)"

rel33-observe:
	AWS_PROFILE="$(REL33_AWS_PROFILE)" \
	EXPECTED_AWS_ACCOUNT_ID="$(REL33_AWS_ACCOUNT_ID)" \
	EXPECTED_KUBE_CONTEXT="$(REL33_KUBE_CONTEXT)" \
	bash "$(REL33_SCRIPT)" observe \
	  --interval "$(REL33_INTERVAL)" \
	  --duration "$(REL33_DURATION)" \
	  --output "$(REL33_OUTPUT)"
