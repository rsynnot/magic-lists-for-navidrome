# MagicLists Agent Guidelines

## Build/Lint/Test Commands

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Docker development
docker-compose up --build
```

### Testing
No formal test suite exists. Run manual API tests:
```bash
# Test API endpoints
curl "http://localhost:8000/api/artists"
curl -X POST "http://localhost:8000/api/create_playlist" \
  -H "Content-Type: application/json" \
  -d '{"artist_ids": ["test_id"], "playlist_length": 25}'
```

### Linting/Type Checking
No linting tools configured. Use Python's built-in tools:
```bash
# Basic syntax check
python -m py_compile backend/*.py

# Type checking (if mypy installed)
mypy backend/ --ignore-missing-imports
```

## Code Style Guidelines

### Imports
- Standard library imports first
- Third-party imports second
- Local imports last (with relative imports using `.`)
- Group imports by type with blank lines between groups

```python
import os
import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException
import uvicorn

from .database import DatabaseManager
from .schemas import Playlist
```

### Naming Conventions
- **Functions/Methods/Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Modules**: `snake_case`

### Type Hints
- Use type hints for all function parameters and return values
- Use `Optional` for nullable types
- Use `List`, `Dict` from `typing` (not `list`, `dict`)

```python
from typing import List, Optional, Dict

def get_playlist(id: int) -> Optional[Dict[str, str]]:
    pass
```

### Error Handling
- Use specific exception types
- Provide meaningful error messages
- Use HTTPException for API errors with appropriate status codes
- Log errors with context

```python
try:
    result = await client.get_artists()
except Exception as e:
    logger.error(f"Failed to fetch artists: {e}")
    raise HTTPException(status_code=500, detail=f"API error: {str(e)}")
```

### Async/Await
- Use async/await for I/O operations
- Prefer async database operations with aiosqlite
- Use asyncio for concurrent operations

### Database Operations
- Use aiosqlite for async database operations
- Use parameterized queries to prevent SQL injection
- Handle database migrations gracefully

### Logging
- Use Python's logging module
- Set appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- Include context in log messages
- Use structured logging for important events

```python
import logging
logger = logging.getLogger(__name__)

logger.info(f"Created playlist: {playlist_name}")
logger.error(f"Failed to connect to Navidrome: {error}")
```

### API Design
- Use Pydantic models for request/response schemas
- Include docstrings for all endpoints
- Handle validation errors gracefully
- Return consistent response formats

### Security
- Never log sensitive information (API keys, passwords)
- Use environment variables for configuration
- Validate all user inputs
- Use HTTPS in production

### File Structure
- Keep related functionality in separate modules
- Use clear, descriptive filenames
- Group services in a `services/` subdirectory
- Separate concerns (database, API, business logic)