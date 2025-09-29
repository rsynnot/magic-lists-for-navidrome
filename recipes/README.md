# Recipe System

This directory contains playlist generation recipes that define how different types of playlists are created.

## Structure

- `registry.json` - Maps playlist types to their current default recipe files
- `{type}_v{major}_{minor}.json` - Individual recipe files with versioning

## Recipe File Format

Each recipe file must include:

```json
{
  "version": "v1.001",
  "description": "Human-readable description of what this recipe does",
  "inputs": ["list", "of", "required", "input", "parameters"],
  "prompt_template": "Template string with {placeholders} for LLM-based recipes",
  "prompt_template_with_reasoning": "Optional template for when reasoning is requested",
  "strategy_notes": {
    "key": "value pairs describing the strategy and approach"
  },
  "llm_params": {
    "temperature": 0.7,
    "max_tokens": 1000,
    "model_fallback": "model/name"
  }
}
```

## Recipe Types

### Artist Radio (`artist_radio`)
- Uses LLM for intelligent track curation
- Balances popular hits with deep cuts
- Considers flow and album diversity

### Re-Discover Weekly (`re_discover`)
- Uses algorithmic approach (no LLM)
- Analyzes listening history patterns
- Scores tracks based on play count and recency

## Adding New Recipes

1. Create a new recipe file with proper versioning
2. Update `registry.json` to point to the new file
3. Test with `/api/recipes/validate` endpoint
4. The system will automatically use the new recipe

## Validation

Use the API endpoints to validate recipes:
- `GET /api/recipes` - List all available recipes
- `GET /api/recipes/validate` - Validate all recipe files