# Ollama Integration Setup

This guide shows how to configure Magic Lists for Navidrome to use local Ollama LLM instances instead of OpenRouter.

## Quick Setup

1. **Update your `.env` file:**
   ```bash
   # Change from OpenRouter to Ollama
   AI_PROVIDER=ollama
   
   # Configure your Ollama instance
   OLLAMA_MODEL=llama3.2
   AI_BASE_URL=http://localhost:11434/v1/chat/completions
   ```

2. **Start your Ollama server:**
   ```bash
   # Install and start Ollama (if not already running)
   ollama serve
   
   # Pull your model (if not already downloaded)
   ollama pull llama3.2
   ```

3. **Restart your Magic Lists application** to pick up the new configuration.

## Configuration Options

### AI_BASE_URL Examples:
- **Local without Docker:** `http://localhost:11434/v1/chat/completions`
- **Local with Docker:** `http://host.docker.internal:11434/v1/chat/completions`  
- **Remote Ollama:** `http://192.168.1.100:11434/v1/chat/completions`

### Popular Models:
- `llama3.2` - Latest Llama model (recommended)
- `llama3.1` - Previous stable version
- `mistral` - Fast and efficient
- `codellama` - Code-focused model

## Docker Compose Setup

If running Magic Lists in Docker, update your docker-compose.yml:

```yaml
services:
  magiclists:
    environment:
      - AI_PROVIDER=ollama
      - OLLAMA_MODEL=llama3.2
      - AI_BASE_URL=http://host.docker.internal:11434/v1/chat/completions
```

## Troubleshooting

### Common Issues:

1. **Connection refused:** Make sure Ollama is running on the correct port
2. **Model not found:** Run `ollama pull <model-name>` first
3. **Slow responses:** Ollama on CPU can be slow - consider using GPU acceleration

### Performance Tips:

- Use smaller models like `llama3.2:8b` for faster responses
- Enable GPU acceleration if available
- Increase timeout if using CPU-only inference

## Switching Back to OpenRouter

To switch back to OpenRouter, update your `.env`:

```bash
AI_PROVIDER=openrouter
AI_API_KEY=your_openrouter_api_key_here
AI_MODEL=openai/gpt-3.5-turbo
AI_BASE_URL=https://openrouter.ai/api/v1/chat/completions
```