# MagicLists - Navidrome MVP

A FastAPI web application that integrates with Navidrome to create AI-powered playlists from your music library.

## Features

- 🎵 Browse artists from your Navidrome library
- 📝 Create custom playlists for any artist
- 🤖 AI-powered playlist generation (optional)
- 💾 SQLite database for playlist storage
- 🐳 Docker support for easy deployment

## Project Structure

```
magiclists-navidrome-mvp/
├── backend/
│   ├── main.py              # FastAPI entrypoint
│   ├── navidrome_client.py  # Navidrome API client
│   ├── ai_client.py         # AI integration
│   ├── database.py          # SQLite database manager
│   └── schemas.py           # Pydantic models
├── frontend/
│   ├── templates/
│   │   └── index.html       # Main web interface
│   └── static/
│       └── style.css        # CSS styles
├── docker/
│   ├── Dockerfile           # Container configuration
│   └── docker-compose.yml   # Multi-service setup
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Quick Start

### Option 1: Docker Compose (Recommended)

1. **Clone and setup:**
   ```bash
   cd magiclists-navidrome-mvp
   cp .env.example .env
   ```

2. **Configure environment variables in `.env`:**
   ```bash
   NAVIDROME_TOKEN=your_navidrome_api_token
   MUSIC_PATH=/path/to/your/music/library
   AI_API_KEY=your_openai_api_key  # Optional
   AI_MODEL=gpt-3.5-turbo  # Optional
   ```

3. **Start services:**
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```

4. **Access the application:**
   - MagicLists: http://localhost:8000
   - Navidrome: http://localhost:4533

### Option 2: Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export NAVIDROME_URL=http://localhost:4533
   export NAVIDROME_TOKEN=your_navidrome_api_token
   export AI_API_KEY=your_openai_api_key  # Optional
   export AI_MODEL=gpt-3.5-turbo  # Optional
   ```

3. **Run the application:**
   ```bash
   cd magiclists-navidrome-mvp
   python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

## API Endpoints

- `GET /` - Web interface
- `GET /api/artists` - List all artists from Navidrome
- `POST /api/create_playlist` - Create a new playlist
  ```json
  {
    "artist_id": "artist_123",
    "playlist_name": "My Favorite Songs"
  }
  ```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `NAVIDROME_URL` | Navidrome server URL | Yes |
| `NAVIDROME_TOKEN` | Navidrome API token | Yes |
| `AI_API_KEY` | OpenAI API key for AI curation | No |
| `AI_MODEL` | AI model name (default: gpt-3.5-turbo) | No |
| `DATABASE_PATH` | SQLite database file path | No |

### Navidrome Setup

1. Install and configure Navidrome on your system
2. Point Navidrome to your music library
3. Create a user account
4. Use these credentials in the MagicLists configuration

## Development

### Project Dependencies

- **FastAPI**: Web framework and API
- **httpx**: HTTP client for Navidrome API
- **aiosqlite**: Async SQLite database
- **Pydantic**: Data validation and schemas
- **Jinja2**: HTML templating
- **uvicorn**: ASGI server

### Adding Features

1. **New API endpoints**: Add to `backend/main.py`
2. **Database changes**: Modify `backend/database.py`
3. **Frontend updates**: Edit `frontend/templates/index.html`
4. **Styling**: Update `frontend/static/style.css`

## Troubleshooting

### Common Issues

1. **Navidrome connection failed**
   - Check `NAVIDROME_URL` is correct
   - Verify Navidrome is running
   - Confirm username/password are valid

2. **No artists found**
   - Ensure your music library is scanned in Navidrome
   - Check Navidrome logs for scanning issues

3. **Database errors**
   - Ensure write permissions for database directory
   - Check disk space

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

For issues and questions:
- Check the troubleshooting section
- Review Navidrome documentation
- Create an issue in the repository