.PHONY: dev backend frontend lint test

# Run the full stack with Docker Compose (postgres + backend + frontend).
dev:
	docker compose up --build

# Run only the backend, natively, against .venv.
backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8010

# Run only the frontend, natively.
frontend:
	cd frontend && npm run dev -- --port 3010

# Lint both backend (ruff) and frontend (tsc --noEmit).
lint:
	cd backend && . .venv/bin/activate && ruff check .
	cd frontend && npx tsc --noEmit

# Run backend tests.
test:
	cd backend && . .venv/bin/activate && pytest
