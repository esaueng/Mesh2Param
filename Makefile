.PHONY: install build typecheck lint test samples verify

install:
	pnpm install
	uv sync --extra dev

build:
	pnpm build

typecheck:
	pnpm typecheck

lint:
	pnpm lint

test:
	pnpm test

samples:
	pnpm samples:generate

verify:
	pnpm verify
