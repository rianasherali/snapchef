.PHONY: snapchef stop

PG_BIN = /Applications/Postgres.app/Contents/Versions/latest/bin

snapchef:
	@echo "Starting SnapChef..."
	@open -a Postgres || true
	@sleep 3
	@$(PG_BIN)/pg_isready -q || (echo "Postgres isn't ready. Open Postgres.app and click Start, then run make snapchef again." && exit 1)
	@lsof -ti:8002 | xargs kill -9 2>/dev/null || true
	@trap 'kill 0' INT TERM EXIT; \
	(cd backend && . venv/bin/activate && python -m uvicorn main:app --reload --port 8002) & \
	(cd frontend && npm run dev) & \
	sleep 4 && open http://localhost:5173 ; \
	wait

stop:
	@lsof -ti:8002 | xargs kill -9 2>/dev/null || true
	@lsof -ti:5173 | xargs kill -9 2>/dev/null || true
	@echo "Stopped."