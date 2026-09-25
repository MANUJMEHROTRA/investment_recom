.PHONY: up down logs ps run brief sweep cluster social-native backfill test backup psql dev-frontend

up:            ## build & start everything (db, analytics, backend, frontend)
	@test -f .env || cp .env.example .env
	docker compose up -d --build
	@echo "Dashboard: http://localhost:3000   API: http://localhost:8000/docs"

down:          ## stop everything (data is kept in the pgdata volume)
	docker compose down

logs:
	docker compose logs -f backend analytics agent clustering

ps:
	docker compose ps

run:           ## run today's analysis now
	curl -s -X POST http://localhost:8000/api/runs && echo

brief:         ## run the pre-market news agent now
	curl -s -X POST http://localhost:8000/api/briefs && echo

sweep:         ## collect news for every tracked stock, then re-cluster
	curl -s -X POST http://localhost:8000/api/news/sweep && echo

cluster:       ## re-run social-listening clustering on new articles only
	curl -s -X POST http://localhost:8000/api/social/run && echo

social-native: ## run the clustering service natively with PyTorch MPS embeddings (Apple GPU)
	@echo "Set CLUSTERING_URL=http://host.docker.internal:8003 in .env and run: docker compose up -d backend"
	docker compose stop clustering
	cd services/clustering && python3 -m venv .venv && .venv/bin/pip install -q -r requirements-mps.txt && \
	  SOCIAL_DATABASE_URL=postgresql+psycopg://social:social@localhost:5433/social BACKEND_URL=http://localhost:8000 \
	  OLLAMA_BASE_URL=http://localhost:11434 EMBED_BACKEND=sentence-transformers \
	  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8003

backfill:      ## rebuild history: make backfill DAYS=120
	curl -s -X POST "http://localhost:8000/api/runs/backfill?days=$${DAYS:-120}" && echo

test:
	cd services/analytics && python -m pytest -q
	cd services/backend && python -m pytest -q
	cd services/agent && python -m pytest -q
	cd services/clustering && python -m pytest -q

backup:        ## dump the database to backups/
	@mkdir -p backups
	docker compose exec -T db pg_dump -U invest invest | gzip > backups/invest-$$(date +%Y%m%d-%H%M).sql.gz
	@ls -lh backups | tail -1

psql:
	docker compose exec db psql -U invest invest

dev-frontend:  ## hot-reload dashboard on :5173 against the running backend
	cd frontend && npm install && npm run dev
