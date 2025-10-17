import os
import httpx
import json
from typing import Optional

class AIProvider:
    """AI provider abstraction for OpenRouter and Ollama"""
    
    def __init__(self, provider_type: str, api_key: Optional[str], model: str, base_url: str):
        self.provider_type = provider_type
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.client = httpx.AsyncClient()
    
    async def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Send chat completion request to configured AI provider"""
        
        # Build headers - only include Authorization for OpenRouter
        headers = {"Content-Type": "application/json"}
        if self.provider_type == "openrouter" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        # Build payload - both providers use OpenAI-compatible format
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        # Set longer timeout for Ollama (local models can be slow on CPU)
        # Extra long timeout for model loading and CPU inference
        timeout = 180.0 if self.provider_type == "ollama" else 30.0
        
        # Handle Ollama model loading with retry logic
        if self.provider_type == "ollama":
            max_retries = 3
            retry_delay = 10  # seconds
            
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
                                if attempt < max_retries - 1:  # Don't wait on the last attempt
                                    import asyncio
                                    await asyncio.sleep(retry_delay)
                                    retry_delay += 10  # Increase wait time for next retry
                                    continue
                                else:
                                    print(f"❌ Model loading timeout after {max_retries} attempts")
                                    raise Exception(f"Ollama model '{self.model}' is still loading after {max_retries * retry_delay}s. Try again in a few minutes.")
                            else:
                                # Different 500 error, re-raise immediately
                                raise
                        except (json.JSONDecodeError, KeyError):
                            # Couldn't parse error response, re-raise
                            raise
                    else:
                        # Non-500 error, re-raise immediately  
                        raise
                except Exception as e:
                    # Other errors (timeout, connection), re-raise on last attempt
                    if attempt == max_retries - 1:
                        raise
                    else:
                        print(f"🔄 Request failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                        import asyncio
                        await asyncio.sleep(retry_delay)
                        continue
        else:
            # OpenRouter - single attempt with standard timeout
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
    
    if provider_type == "ollama":
        return AIProvider(
            provider_type="ollama",
            api_key=None,  # Ollama doesn't need API key
            model=os.getenv("OLLAMA_MODEL", "llama3.2"),
            base_url=os.getenv("AI_BASE_URL", "http://localhost:11434/v1/chat/completions")
        )
    else:  # openrouter
        return AIProvider(
            provider_type="openrouter",
            api_key=os.getenv("AI_API_KEY"),
            model=os.getenv("AI_MODEL", "openai/gpt-3.5-turbo"),
            base_url=os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
        )