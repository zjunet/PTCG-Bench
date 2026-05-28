# PTCG Backend API

FastAPI backend for Pokémon TCG game engine.

## Quick Start

```bash
# Install dependencies
uv sync

# Start server
uv run python backend/main.py
```

The API will be available at http://localhost:8000

## API Endpoints

### REST API

- `POST /api/game/create` - Create new game
- `GET /api/game/{game_id}/state` - Get game state
- `POST /api/game/{game_id}/action` - Execute action
- `DELETE /api/game/{game_id}` - Delete game

### WebSocket

- `WS /ws/game/{game_id}` - Real-time game updates

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Requirements

- Python 3.12+
- FastAPI
- Uvicorn
- See `pyproject.toml` for the full dependency list
