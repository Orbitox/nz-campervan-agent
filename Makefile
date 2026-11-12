.PHONY: install lint test eval run-web deploy infra

install:
	uv sync --all-extras

lint:
	agents-cli lint --mypy

test:
	pytest tests/unit -v

eval:
	python3 tests/eval/run_evaluation_suite.py

run-web:
	python3 -m app.web_server --port 8080

deploy:
	agents-cli deploy --deployment-target agent_runtime --region us-central1

infra:
	cd deployment/terraform && terraform init && terraform validate
