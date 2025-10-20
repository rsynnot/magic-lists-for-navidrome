# MagicLists Setup Guide

## Prerequisites

1. **Navidrome Server**: Running instance with music library scanned
2. **Navidrome Account**: Username and password for your Navidrome server
3. **AI API Key**: Optional, for AI-powered curation

## Environment Setup

### 1. Copy Environment Template
```bash
cp .env.example .env
```

### 2. Configure Required Variables
```bash
# Required - Navidrome connection
NAVIDROME_URL=http://localhost:4533
NAVIDROME_USERNAME=your_navidrome_username
NAVIDROME_PASSWORD=your_navidrome_password

# Required - Database location (will be auto-created)
DATABASE_PATH=./magiclists.db        # For standalone: ./magiclists.db
                                     # For Docker: /app/data/magiclists.db

# Optional - AI curation (without this, uses fallback algorithm)
AI_PROVIDER=openrouter              # Options: openrouter, groq, google, ollama
AI_API_KEY=sk-or-v1-your-key-here   # For OpenRouter/Groq/Google (not needed for Ollama)
AI_MODEL=deepseek/deepseek-chat     # Optional, uses provider defaults

# Optional - Ollama timeout (only for ollama provider)
OLLAMA_TIMEOUT=180                   # Seconds, increase for slower CPUs
```

### 3. For Docker Deployment
```bash
# Additional for Docker
MUSIC_PATH=/path/to/your/music/library
```

> **Note**: MagicLists automatically handles authentication with Navidrome using your username/password. No manual API token setup required!

## Quick Start Options

### Option A: Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export NAVIDROME_URL=http://localhost:4533
export NAVIDROME_USERNAME=your_username
export NAVIDROME_PASSWORD=your_password

# Run the application
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Option B: Docker Compose
```bash
# Configure .env file first, then:
docker-compose up -d
```

## Testing Your Setup

### 1. Check Navidrome Connection
```bash
# MagicLists will automatically authenticate - just test the app endpoint
curl "http://localhost:8000/api/artists"
```

### 2. Test MagicLists API
```bash
# Get artists
curl "http://localhost:8000/api/artists"

# Create test "This Is" playlist
curl -X POST "http://localhost:8000/api/create_playlist" \
  -H "Content-Type: application/json" \
  -d '{"artist_ids": ["some_artist_id"], "playlist_length": 25}'

# Get managed playlists
curl "http://localhost:8000/api/playlists"

# Check scheduler status
curl "http://localhost:8000/api/scheduler/status"
```

### 3. Access Web Interface
- **Development**: http://localhost:8000
- **Docker**: http://localhost:4545

## Troubleshooting

### "No artists found"
- Ensure Navidrome has scanned your music library
- Check that `NAVIDROME_USERNAME` and `NAVIDROME_PASSWORD` are correct
- Verify `NAVIDROME_URL` is correct and accessible

### "Failed to create playlist"
- Ensure artist has tracks available in your library
- Check that your Navidrome user account has playlist creation permissions
- Verify network connectivity between MagicLists and Navidrome

### Database Write Errors
If you get 500 server errors when creating playlists (even though system checks pass):
- **Check**: `DATABASE_PATH` environment variable is set
- **Docker**: Should be `/app/data/magiclists.db` with volume mounted
- **Standalone**: Should be `./magiclists.db` or absolute path to writable location
- **Verify**: The directory exists and is writable by the application

### AI Curation Not Working
- Ensure `AI_PROVIDER` and `AI_API_KEY` are set correctly (if required)
- For Groq: Check your API key from https://console.groq.com/
- For OpenRouter: Check your API key has sufficient credits
- For Ollama: Ensure Ollama server is running (`ollama serve`)
- Application will fall back to play-count based selection

### Docker Issues
- Ensure `MUSIC_PATH` points to your music directory
- Check Docker has permission to access music files
- Verify all environment variables are set in `.env`

## Feature Notes

### AI Curation
- **With AI**: Intelligent track selection considering quality, variety, and flow
- **Without AI**: Falls back to play-count + recency based selection
- **Track Limit**: User-configurable (default 25 tracks)

### Playlist Types
- **This Is (Artist)**: Single-artist playlists with hits and deep cuts
- **Re-Discover**: Surface forgotten tracks from your library based on listening history

### Auto-Refresh Scheduling
- **Daily/Weekly/Monthly**: Automatic playlist refresh at scheduled times
- **Catch-up Logic**: 7-day grace period for missed refreshes (system offline)
- **Length Preservation**: Refreshes maintain original user-specified playlist length

### Playlist Storage
- **Navidrome**: Actual playable playlists in your music server
- **Local Database**: Metadata, track titles, and scheduling information
- **Refresh Tracking**: Last refreshed timestamps and next refresh scheduling

## Scheduler System

### Automatic Operation
- **Runs every hour** checking for playlists due for refresh
- **Logs activity** to `scheduler.log` for monitoring
- **Heartbeat logging** shows when scheduler runs (even if no tasks)

### Manual Control
```bash
# Check scheduler status
curl "http://localhost:8000/api/scheduler/status"

# Start scheduler (auto-starts on app launch)
curl -X POST "http://localhost:8000/api/scheduler/start"

# Manually trigger refresh check
curl -X POST "http://localhost:8000/api/scheduler/trigger"
```

### AI Configuration (Optional)

For AI-powered playlist curation, choose from these providers:

#### Option 1: OpenRouter (Recommended - Free & Flexible)
1. **Get an OpenRouter API key** from https://openrouter.ai ($5 minimum)
2. **Add to your `.env` file:**
   ```bash
   AI_PROVIDER=openrouter
   AI_API_KEY=sk-or-v1-your-key-here
   AI_MODEL=deepseek/deepseek-chat     # Free model
   # AI_MODEL=anthropic/claude-3-haiku # Paid model
   ```

**Popular OpenRouter models:**
- `deepseek/deepseek-chat` - Very cost-effective (free)
- `openai/gpt-3.5-turbo` - Fast and reliable
- `anthropic/claude-3-haiku` - Good for creative tasks

#### Option 2: Groq (Fast & Free)
1. **Get a free Groq API key** from https://console.groq.com/ (no credit card required)
2. **Add to your `.env` file:**
   ```bash
   AI_PROVIDER=groq
   AI_API_KEY=gsk_your-groq-key-here
   AI_MODEL=llama-3.1-8b-instant
   ```

#### Option 3: Google AI (Free & Generous Quota)
1. **Get a free Google AI API key** from https://ai.google.dev/ (no credit card required)
2. **Add to your `.env` file:**
   ```bash
   AI_PROVIDER=google
   AI_API_KEY=AIzaSy_your-google-key-here
   AI_MODEL=gemini-2.5-flash
   ```

#### Option 4: Ollama (Local Models)
1. **Install Ollama** from https://ollama.com
2. **Pull and run a model:**
   ```bash
   ollama pull llama3.2
   ollama serve
   ```
3. **Add to your `.env` file:**
   ```bash
   AI_PROVIDER=ollama
   AI_MODEL=llama3.2
   OLLAMA_BASE_URL=http://localhost:11434/v1/chat/completions
   # OLLAMA_TIMEOUT=300  # Increase for slower CPUs (default: 180 seconds)
   ```

Without AI configuration, playlists use fallback algorithms based on play counts.

## API Documentation

Once running, visit:
- **Web Interface**: http://localhost:8000 (dev) or http://localhost:4545 (Docker)
- **API Docs**: http://localhost:8000/docs or http://localhost:4545/docs
- **OpenAPI Schema**: http://localhost:8000/openapi.json