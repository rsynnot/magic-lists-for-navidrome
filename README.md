## MagicLists for Navidrome

Free your music. Own your experience.

MagicLists is an open-source experiment in AI-assisted music discovery for people who run their own Navidrome server. Instead of "renting" playlists from Apple or Spotify, you keep full control of your library and still enjoy smart, personalised mixes.

It's an ongoing research project led by a product designer with 20+ years in tech, built with and for the Navidrome community. Together we're proving that AI-powered curation can be free, transparent and privacy-respecting.

## Features
- 🎵 **This Is (Artist)** - A definitive, single-artist mix with primary and featured appearances, de-duplicated versions, and balanced hits and deep cuts
- 🔄 **Re-Discover** - Surfaces tracks you haven't played recently so you can re-find forgotten favourites
- ⏰ **Auto-Refresh** - Schedule playlists to refresh automatically (daily, weekly, monthly) to keep lists current
- 🐳 **Easy Docker Setup** - Get running in minutes with Docker - no complex setup required

### More to come:
Song Radio, Multi-artist Radio, AI prompted lists, fresh discovery tools, and other experiments in open music curation.

## Screenshots
![Artist Radio UI](assets/images/artist-playlist.png)

_Caption: Creating a 'This is (Artist)' playlist _ 

## Project Structure

```
magiclists-navidrome/
├── backend/
│   ├── main.py              # FastAPI entrypoint
│   ├── navidrome_client.py  # Navidrome API client
│   ├── ai_client.py         # AI integration
│   ├── database.py          # SQLite database manager
│   ├── recipe_manager.py    # Playlist recipe system
│   ├── rediscover.py        # Re-discover logic
│   └── schemas.py           # Pydantic models
├── frontend/
│   ├── templates/
│   │   └── index.html       # Main web interface
│   └── static/
│       └── assets/
│           └── ml-logo.svg  # Magic Lists logo
├── recipes/
│   ├── registry.json        # Recipe registry
│   ├── this_is_v1_002.json  # This Is recipe v1.2
│   └── re_discover_v1_004.json # Re-Discover recipe v1.4
├── assets/
│   └── images/
│       └── artist-radio.png # Screenshot
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container configuration
├── docker-compose.yml       # Docker Compose setup
└── README.md               # This file
```

## Quick Start

### Option 1: Running with Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/rsynnot/magic-lists-for-navidrome.git
   cd magiclists-navidrome-mvp
   ```

2. **Create your environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Configure your `.env` file with your Navidrome details:**
   ```bash
   # Required - Your Navidrome server details
   NAVIDROME_URL=https://your-navidrome-server.com
   NAVIDROME_USERNAME=your_username
   NAVIDROME_PASSWORD=your_password
   
   # Optional - AI features (see AI Configuration section below)
   AI_API_KEY=your_api_key_here
   AI_MODEL=openai/gpt-3.5-turbo
   ```

4. **Start the application:**
   ```bash
   docker-compose up --build
   ```

5. **Access the application:**
   - Open http://localhost:4545 in your browser
   - The app will connect to your Navidrome server using the credentials in `.env`

**That's it!** The application will be running in a Docker container with all dependencies included.

### Option 2: Local Development (Advanced)

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
- `POST /api/create_playlist` - Create a new "This Is" playlist
- `POST /api/create_playlist_with_reasoning` - Create playlist with detailed reasoning
- `GET /api/rediscover-weekly` - Generate Re-Discover Weekly recommendations
- `POST /api/create-rediscover-playlist` - Create Re-Discover Weekly playlist in Navidrome
- `GET /api/playlists` - List all managed playlists
- `DELETE /api/playlists/{playlist_id}` - Delete a managed playlist
- `GET /api/recipes` - List available recipe versions
- `GET /api/recipes/validate` - Validate recipe configurations
- `GET /api/scheduler/status` - Check auto-refresh scheduler status
- `POST /api/scheduler/trigger` - Manually trigger scheduled refreshes
- `POST /api/scheduler/start` - Start the auto-refresh scheduler

## Configuration

### AI Configuration (Optional)

The AI features enhance playlist curation with intelligent track selection. You can choose from free, low-cost, or premium models:

**Getting an API Key:**
- **[OpenRouter](https://openrouter.ai)** - Provides access to many models with free tiers

**Model Options:**
- **Free/Low-cost**: `deepseek/deepseek-chat`, `google/gemini-flash-1.5`, `meta-llama/llama-3.1-8b-instruct:free`
- **Paid**: `openai/gpt-3.5-turbo`, `openai/gpt-4o-mini`, `anthropic/claude-3-haiku`

**Example `.env` setup:**
```bash
# For OpenRouter (free tier available)
AI_API_KEY=sk-or-v1-your-key-here
AI_MODEL=deepseek/deepseek-chat

# For OpenAI direct
AI_API_KEY=sk-your-openai-key
AI_MODEL=openai/gpt-3.5-turbo
```

**Note:** Without AI configuration, the app falls back to play-count based playlist generation.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `NAVIDROME_URL` | Navidrome server URL | Yes |
| `NAVIDROME_USERNAME` | Navidrome username | Yes |
| `NAVIDROME_PASSWORD` | Navidrome password | Yes |
| `NAVIDROME_API_KEY` | Navidrome API key (future feature) | No |
| `AI_API_KEY` | OpenRouter API key for AI curation | No |
| `AI_MODEL` | AI model name (default: openai/gpt-3.5-turbo) | No |
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
4. **Styling**: Styles are handled with Tailwind CSS in the HTML template

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

## 📈 Usage Analytics

This project uses [Umami Analytics](https://umami.is/) to anonymously measure feature usage (no cookies, no personal data are stored).

You can view the **public dashboard here:** [magic-lists analytics](https://umami.itsricky.com/share/kg0XvYPeMM3UsqhO/magic-lists.local)

## Support

For issues and questions:
- Check the troubleshooting section
- Review Navidrome documentation
- Create an issue in the repository

---

© 2025 Synnot Studio — Licensed under the MIT License.

Made with ❤️ by [Synnot Studio](https://synnotstudio.com).