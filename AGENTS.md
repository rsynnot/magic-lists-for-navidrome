# Agent Development Guide

## Build/Lint/Test Commands

### Development Server
```bash
# With virtual environment (recommended)
source venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 4545 --reload

# Without virtual environment
python -m uvicorn backend.main:app --host 0.0.0.0 --port 4545 --reload
```

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose up --build

# Build only
docker build .

# Run only
docker-compose up -d
```

### Testing
```bash
# Run the genre API test
python test_genre_api.py

# Quick API test
curl "http://localhost:4545/api/artists"
```

### Production Deployment
```bash
# Docker Compose (recommended)
docker-compose up -d

# Manual Docker run
docker run -d --name magiclists -p 4545:8000 -e NAVIDROME_URL=... -e NAVIDROME_USERNAME=... -e NAVIDROME_PASSWORD=... -e DATABASE_PATH=/app/data/magiclists.db -v ./magiclists-data:/app/data rickysynnot/magic-lists-for-navidrome:latest
```

## Code Style Guidelines

### Imports
- Standard library imports first
- Third-party imports second
- Local imports last with relative imports
- Use `from .module import Class` for relative imports
- Group imports with blank lines between groups

### Formatting
- 4-space indentation
- Line length: reasonable (no strict limit enforced)
- Consistent spacing around operators and commas
- Blank lines between functions and classes

### Types
- Use type hints extensively from `typing` module
- Common types: `List`, `Optional`, `Dict`, `Union`
- Return type annotations for all functions

### Naming Conventions
- **Variables/Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_CASE`
- **Modules**: `snake_case`
- **Private methods**: `_leading_underscore`

### Error Handling
- Use try/except blocks for expected errors
- Raise `HTTPException` for API errors with appropriate status codes
- Log errors using Python's logging module
- Use specific exception types when possible

### Async/Await
- Use `async def` for I/O operations
- Use `await` for async calls
- Return appropriate types from async functions

### Documentation
- Use docstrings for all public functions
- Describe what the function does, not how
- Include parameter descriptions when complex

### Logging
- Use `logging.getLogger(__name__)` for module-specific loggers
- Log levels: DEBUG, INFO, WARNING, ERROR
- Include relevant context in log messages
- Use emojis sparingly for visual distinction in logs

### Database
- Use async SQLite operations with `aiosqlite`
- Handle database migrations gracefully
- Store JSON data in TEXT columns when needed
- Use parameterized queries to prevent SQL injection

### Security
- Never log sensitive information (API keys, passwords)
- Validate environment variables
- Use secure defaults for file permissions
- Handle authentication errors appropriately