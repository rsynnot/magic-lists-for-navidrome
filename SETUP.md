# MagicLists Setup Guide

## Prerequisites

1. **Navidrome Server**: Running instance with music library scanned
2. **Navidrome API Token**: Required for API access
3. **OpenAI API Key**: Optional, for AI-powered curation

## Getting Your Navidrome API Token

### Method 1: Web Interface (Recommended)
1. Log into your Navidrome web interface
2. Go to **Settings** → **API Keys**
3. Click **"Generate New Token"**
4. Copy the generated token
5. Use this as your `NAVIDROME_TOKEN`

### Method 2: Direct API Call
```bash
curl -X POST "http://your-navidrome-url:4533/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'
```

## Environment Setup

### 1. Copy Environment Template
```bash
cp .env.example .env
```

### 2. Configure Required Variables
```bash
# Required - Navidrome connection
NAVIDROME_URL=http://localhost:4533
NAVIDROME_TOKEN=your_api_token_from_navidrome

# Optional - AI curation (without this, uses fallback algorithm)
AI_API_KEY=sk-your_openai_api_key
AI_MODEL=gpt-3.5-turbo

# Optional - Custom database path
DATABASE_PATH=./magiclists.db
```

### 3. For Docker Deployment
```bash
# Additional for Docker
MUSIC_PATH=/path/to/your/music/library
```

## Quick Start Options

### Option A: Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export NAVIDROME_URL=http://localhost:4533
export NAVIDROME_TOKEN=your_token_here

# Run the application
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### Option B: Docker Compose
```bash
# Configure .env file first, then:
docker-compose -f docker/docker-compose.yml up -d
```

## Testing Your Setup

### 1. Check Navidrome Connection
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:4533/api/artist"
```

### 2. Test MagicLists API
```bash
# Get artists
curl "http://localhost:8000/api/artists"

# Create test playlist
curl -X POST "http://localhost:8000/api/create_playlist" \
  -H "Content-Type: application/json" \
  -d '{"artist_id": "some_artist_id"}'
```

### 3. Access Web Interface
Open http://localhost:8000 in your browser

## Troubleshooting

### "No artists found"
- Ensure Navidrome has scanned your music library
- Check that `NAVIDROME_TOKEN` is valid
- Verify `NAVIDROME_URL` is correct

### "Failed to create playlist"
- Check Navidrome API permissions
- Ensure artist has tracks available
- Verify token has playlist creation permissions

### AI Curation Not Working
- Ensure `AI_API_KEY` is set correctly
- Check OpenAI API key has sufficient credits
- Application will fall back to play-count based selection

### Docker Issues
- Ensure `MUSIC_PATH` points to your music directory
- Check Docker has permission to access music files
- Verify all environment variables are set in `.env`

## Feature Notes

### AI Curation
- **With AI**: Intelligent track selection considering quality, variety, and flow
- **Without AI**: Falls back to play-count + recency based selection
- **Track Limit**: Currently set to 20 tracks per playlist

### Playlist Storage
- **Navidrome**: Actual playable playlists in your music server
- **Local Database**: Metadata and track titles for MagicLists interface
- **Sync**: Both databases updated when playlist is created

## API Documentation

Once running, visit:
- **Web Interface**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **OpenAPI Schema**: http://localhost:8000/openapi.json