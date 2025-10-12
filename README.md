## MagicLists for Navidrome

AI-assisted playlists for your own music library.

MagicLists adds the kind of curated, evolving playlists you’d expect from Spotify or Apple Music—except it works entirely on your self-hosted Navidrome server. No subscriptions, no renting your music back. Just smart mixes generated from the library you already own.

# What it does
- 🎵 **This Is (Artist)** — Builds a definitive playlist for any artist in your library, combining hits, deep cuts, and featured appearances without duplicates.
- 🔄 **Re-Discover** — Rotates tracks you haven’t played in a while, helping you fall back in love with your collection.
- ⏰ **Auto-Refresh** — Keep playlists fresh with daily, weekly, or monthly updates.
- 🐳 **Quick Setup** — Simple Docker install; get started in minutes.

# Why it matters
Navidrome users already own their music. MagicLists brings modern curation tools into that world—so your playlists feel alive, not static, and your collection keeps surprising you.

# Who’s behind it
I’m Ricky, a product designer with 20+ years in tech. I’m building MagicLists feature by feature, from UI and CSS to playlist logic, because I’m passionate about open-source, privacy-friendly music tools. This isn’t vaporware or a throwaway experiment—it’s genuine, ongoing research into how AI can enrich personal music libraries.

# What’s next
Upcoming experiments include:
- Multi-artist “radio” blends
- Decade and discovery-focused lists
- Creative journeys like The Long Way Home (a track-to-track sonic path) and Genre Archaeology (tracing influences backwards through time).

MagicLists is just getting started, and I’d love your feedback as it grows.

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

## System Check

MagicLists automatically validates your configuration on startup. If any issues are detected, you'll be redirected to a system check page that shows:

- **Environment Variables**: Checks that required variables are set
- **Navidrome URL**: Verifies your server is reachable  
- **Navidrome Authentication**: Tests your credentials
- **Navidrome Artists API**: Confirms API access is working
- **OpenRouter API Key**: Checks if AI features are configured (optional)
- **Library Configuration**: Shows multiple library setup status

If checks fail, detailed suggestions are provided to help resolve issues. You can also access the system check at any time via `/system-check`.

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

| Variable | Description | Required | Settings UI |
|----------|-------------|----------|-------------|
| `NAVIDROME_URL` | Navidrome server URL | Yes | ✅ |
| `NAVIDROME_USERNAME` | Navidrome username | Yes | ✅ |
| `NAVIDROME_PASSWORD` | Navidrome password | Yes | ❌ |
| `NAVIDROME_LIBRARY_ID` | Specific library ID for multiple libraries | No | ✅ |
| `NAVIDROME_API_KEY` | Navidrome API key (future feature) | No | ❌ |
| `AI_API_KEY` | OpenRouter API key for AI curation | No | ❌ |
| `AI_MODEL` | AI model name (default: openai/gpt-3.5-turbo) | No | ✅ |
| `DATABASE_PATH` | SQLite database file path | No | ❌ |

**Note**: Variables marked with ✅ can be updated via the Settings page (`/settings`). Others require editing the `.env` file and restarting the application.

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
   - Verify Navidrome is running and accessible
   - Confirm username/password are valid in your `.env` file

2. **Docker Networking Issues**
   
   When running in Docker, connection issues are often related to networking:
   
   **Use container names instead of localhost:**
   ```bash
   # ❌ Won't work in Docker
   NAVIDROME_URL=http://localhost:4533
   
   # ✅ Use container name
   NAVIDROME_URL=http://navidrome:4533
   ```
   
   **Check if containers are on the same network:**
   ```bash
   # List Docker networks
   docker network ls
   
   # Inspect your network
   docker network inspect your_network_name
   
   # Verify both containers are on the same network
   docker ps --format "table {{.Names}}\t{{.Networks}}"
   ```
   
   **Alternative solutions:**
   - Use the Docker host IP: `NAVIDROME_URL=http://172.17.0.1:4533`
   - Use host networking mode (less secure)
   - Ensure both containers use the same Docker Compose network
   
   📖 **Learn more**: [Docker Networking Documentation](https://docs.docker.com/network/)

3. **Multiple Navidrome Libraries**
   
   If you have multiple music libraries in Navidrome:
   
   - **Automatic**: MagicLists will detect and work with all libraries by default
   - **Specific Library**: Set `NAVIDROME_LIBRARY_ID` to target a specific library:
     ```bash
     NAVIDROME_LIBRARY_ID=your-library-id-here
     ```
   - **Find Library IDs**: Check your Navidrome admin interface or API documentation
   - **System Check**: The health check will show library configuration status

4. **No artists found**
   - Ensure your music library is scanned in Navidrome
   - Check Navidrome logs for scanning issues
   - If using multiple libraries, verify the library ID is correct

5. **Database errors**
   - Ensure write permissions for database directory
   - Check disk space
   - Restart the application if database appears corrupted

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