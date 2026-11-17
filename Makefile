.PHONY: up down logs test

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test:
	docker compose run --rm --build --no-deps api pytest -q
