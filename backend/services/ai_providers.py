import os
import httpx
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ProviderConfig:
    """Configuration for an AI provider"""
    base_url: str
    requires_key: bool
    default_model: str
    signup_url: str

class AIProviderConfig:
    """Hardcoded configurations for all supported AI providers"""
    
    PROVIDERS: Dict[str, ProviderConfig] = {
        "openrouter": ProviderConfig(
            base_url="https://openrouter.ai/api/v1/chat/completions",
            requires_key=True,
            default_model="openai/gpt-3.5-turbo",
            signup_url="https://openrouter.ai/"
        ),
        "groq": ProviderConfig(
            base_url="https://api.groq.com/openai/v1/chat/completions", 
            requires_key=True,
            default_model="mixtral-8x7b-32768",
            signup_url="https://console.groq.com/"
        ),
        "ollama": ProviderConfig(
            base_url="http://localhost:11434/v1/chat/completions",
            requires_key=False,
            default_model="llama3.2",
            signup_url=""  # Not applicable for local models
        )
    }

class AIProvider:
    """AI provider abstraction for OpenRouter, Groq, and Ollama"""
    
    def __init__(self, provider_type: str, api_key: Optional[str], model: str, base_url: str):
        self.provider_type = provider_type
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Send chat completion request to configured AI provider"""
        
        # Build headers - only include Authorization for providers that require keys
        headers = {"Content-Type": "application/json"}
        if self.provider_type in ["openrouter", "groq"] and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Build payload - all providers use OpenAI-compatible format
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        # Set timeout based on provider type
        if self.provider_type == "ollama":
            # Allow user to override Ollama timeout (default 180 seconds)
            timeout = float(os.getenv("OLLAMA_TIMEOUT", "180"))
            max_retries = 3
            retry_delay = 10
            
            # Handle Ollama model loading with retry logic
            for attempt in range(max_retries):
                try:
                    response = await self.client.post(
                        self.base_url,
                        json=payload,
                        headers=headers,
                        timeout=timeout
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 500:
                        # Check if it's a model loading error
                        try:
                            error_data = e.response.json()
                            error_message = error_data.get("error", {}).get("message", "")
                            
                            if "loading model" in error_message.lower():
                                print(f"🔄 Model still loading (attempt {attempt + 1}/{max_retries}), waiting {retry_delay}s...")
                                if attempt < max_retries - 1:
                                    import asyncio
                                    await asyncio.sleep(retry_delay)
                                    retry_delay += 10
                                    continue
                                else:
                                    print(f"❌ Model loading timeout after {max_retries} attempts")
                                    raise Exception(f"Ollama model '{self.model}' is still loading after {max_retries * retry_delay}s. Try again in a few minutes.")
                            else:
                                raise
                        except (json.JSONDecodeError, KeyError):
                            raise
                    else:
                        raise
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    else:
                        print(f"🔄 Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                        import asyncio
                        await asyncio.sleep(retry_delay)
                        continue
        else:
            # OpenRouter and Groq - single attempt with standard timeout
            timeout = 30.0
            response = await self.client.post(
                self.base_url,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
    
    async def close(self):
        """Close the HTTP client"""
        if hasattr(self, 'client') and self.client:
            if hasattr(self.client, 'is_closed') and not self.client.is_closed:
                await self.client.aclose()

def get_ai_provider() -> AIProvider:
    """Factory function that reads .env and returns configured provider"""
    provider_type = os.getenv("AI_PROVIDER", "openrouter")
    
    # Validate provider type
    if provider_type not in AIProviderConfig.PROVIDERS:
        available = ", ".join(AIProviderConfig.PROVIDERS.keys())
        raise ValueError(f"Unknown AI_PROVIDER: {provider_type}. Options: {available}")
    
    provider_config = AIProviderConfig.PROVIDERS[provider_type]
    
    # Check if API key is required
    api_key = os.getenv("AI_API_KEY")
    if provider_config.requires_key and not api_key:
        raise ValueError(f"{provider_type} requires AI_API_KEY. Get one at: {provider_config.signup_url}")
    
    # Get model (user override or provider default)
    model = os.getenv("AI_MODEL") or provider_config.default_model
    
    # Get base URL (allow Ollama override, use default for others)
    if provider_type == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", provider_config.base_url)
    else:
        base_url = provider_config.base_url
    
    return AIProvider(
        provider_type=provider_type,
        api_key=api_key,
        model=model,
        base_url=base_url
    )