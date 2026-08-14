.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := $(COMPOSE) exec backend
FRONTEND := $(COMPOSE) exec frontend

.PHONY: help up down ps logs migrate makemigrations test test-backend test-frontend \
        lint lint-backend lint-frontend format shell bash seed check-deploy build clean

help: ## Lista os comandos disponíveis
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Sobe todos os serviços
	$(COMPOSE) up -d

down: ## Derruba os serviços (mantém os volumes)
	$(COMPOSE) down

ps: ## Status dos serviços
	$(COMPOSE) ps

logs: ## Logs de todos os serviços
	$(COMPOSE) logs -f

build: ## Reconstrói as imagens
	$(COMPOSE) build

migrate: ## Aplica as migrations
	$(BACKEND) python manage.py migrate

makemigrations: ## Gera migrations
	$(BACKEND) python manage.py makemigrations

test: test-backend test-frontend ## Roda todos os testes

test-backend: ## pytest
	# --ds explícito: o container exporta DJANGO_SETTINGS_MODULE=config.settings.development,
	# e no pytest-django a variável de ambiente vence o pyproject.toml. Sem isto o teste roda
	# com as settings erradas — falha o que deveria passar e esconde o que deveria falhar.
	$(BACKEND) pytest --ds=config.settings.test

test-frontend: ## vitest
	$(FRONTEND) npm run test

lint: lint-backend lint-frontend ## Lint + typecheck de tudo

lint-backend: ## ruff + black --check + mypy
	$(BACKEND) ruff check .
	$(BACKEND) black --check .
	$(BACKEND) mypy .

lint-frontend: ## eslint + tsc
	$(FRONTEND) npm run lint
	$(FRONTEND) npx tsc --noEmit

format: ## Formata backend e frontend
	$(BACKEND) ruff check --fix .
	$(BACKEND) black .
	$(FRONTEND) npx prettier --write .

shell: ## Shell do Django
	$(BACKEND) python manage.py shell

bash: ## Shell do container backend
	$(BACKEND) bash

seed: ## Dados fictícios de desenvolvimento
	$(BACKEND) python manage.py seed_dev_data

check-deploy: ## Checagem de segurança com settings de produção
	$(BACKEND) python manage.py check --deploy --settings=config.settings.production

clean: ## Derruba e REMOVE os volumes (apaga o banco)
	$(COMPOSE) down -v
