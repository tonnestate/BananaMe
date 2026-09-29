.PHONY: test install-dev

install-dev:
	python -m pip install -e '.[dev]'

test:
	pytest
