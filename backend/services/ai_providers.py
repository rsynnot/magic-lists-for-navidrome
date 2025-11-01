import os
import httpx
import json
import re
from typing import Optional, Dict, Any, Union, NoReturn
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
        "google": ProviderConfig(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            requires_key=True,
            default_model="gemini-2.5-flash",
            signup_url="https://ai.google.dev/"
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
    
    async def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 16000, temperature: float = 0.7) -> str:
        """Send chat completion request to configured AI provider"""
        
        # Handle Google AI's different API format
        if self.provider_type == "google":
            return await self._generate_google(system_prompt, user_prompt, max_tokens, temperature)
        
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
    
    async def _generate_google(self, system_prompt: str, user_prompt: str, max_tokens: int = 16000, temperature: float = 0.7) -> Union[str, NoReturn]:  # type: ignore
        """Handle Google AI's specific API format with controlled generation for JSON"""
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"

        # Add JSON-specific instructions to the prompt
        combined_prompt = f"""
        {system_prompt}

        Important: Your response must be formatted as a valid JSON object.
        Do not include any explanatory text outside the JSON structure.
        Return only the JSON object, nothing else.

        {user_prompt}
        """

        # For genre mix, responses are small JSON, so cap output tokens reasonably
        if "Genre Mix" in system_prompt or "genre_mix" in user_prompt.lower():
            # max_output = 2500  # Genre mix responses are ~500 tokens
            max_output = min(int(max_tokens), 16000)
        else:
            max_output = min(int(max_tokens), 16000)

        generation_config = {
            "temperature": temperature,
            "maxOutputTokens": max_output
        }

        payload = {
            "contents": [{
                "parts": [{
                    "text": combined_prompt
                }]
            }],
            "generationConfig": generation_config
        }

        headers = {"Content-Type": "application/json"}

        # Debug: Save payload to file for inspection
        import json
        import time
        timestamp = int(time.time())

        # Add debug info to payload
        debug_info = {
            "timestamp": timestamp,
            "model": self.model,
            "max_tokens_param": max_tokens,
            "max_output_tokens_calculated": generation_config.get("maxOutputTokens"),
            "combined_prompt_length": len(combined_prompt),
            "system_prompt_length": len(system_prompt),
            "user_prompt_length": len(user_prompt),
            "is_genre_mix": "Genre Mix" in system_prompt or "genre_mix" in user_prompt.lower()
        }

        payload_with_debug = {
            "debug_info": debug_info,
            "payload": payload
        }

        payload_file = f"payloads/google_ai_payload_{timestamp}.json"
        with open(payload_file, 'w') as f:
            json.dump(payload, f, indent=2)
        print(f"📄 Saved payload to {payload_file} (prompt: ~{len(combined_prompt)//4} tokens)")

        try:
            response = await self.client.post(
                url,
                json=payload,
                headers=headers,
                timeout=60.0
            )
            response.raise_for_status()

            result = response.json()

            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]

                # Check finish reason 
                finish_reason = candidate.get("finishReason", "")
                if finish_reason:
                    if finish_reason in ["SAFETY", "RECITATION", "OTHER"]:
                        raise Exception(f"Google AI blocked the response due to: {finish_reason}")
                    elif finish_reason == "MAX_TOKENS":
                        # This means output hit the limit, not input
                        prompt_tokens = result.get('usageMetadata', {}).get('promptTokenCount', 'unknown')
                        output_tokens = result.get('usageMetadata', {}).get('candidatesTokenCount', 'unknown')
                        raise Exception( 
                            f"Google AI response incomplete: output hit {max_output} token limit. "
                            f"Input: {prompt_tokens} tokens, Output: {output_tokens} tokens. "
                            f"Increase max_tokens parameter if you need longer responses."
                        )

                # Parse the actual content
                if "content" in candidate:
                    content = candidate["content"]

                    if "parts" in content and isinstance(content["parts"], list):
                        parts = content["parts"]
                        if len(parts) > 0:
                            part = parts[0]
                            if "text" in part:
                                text = part["text"].strip()

                                # Try to extract JSON from the response
                                try:
                                    # First try direct JSON parsing
                                    json_response = json.loads(text)
                                    return json.dumps(json_response, ensure_ascii=False)
                                except json.JSONDecodeError:
                                    # Try to find JSON within the text (in case of extra content)
                                    json_match = re.search(r'\{.*\}', text, re.DOTALL)
                                    if json_match:
                                        try:
                                            json_response = json.loads(json_match.group())
                                            return json.dumps(json_response, ensure_ascii=False)
                                        except json.JSONDecodeError:
                                            pass

                                    # If all else fails, return the text as-is and let upstream handle it
                                    return text

                raise Exception("Google AI response missing content structure")

            raise Exception("Google AI response missing candidates array")

        except Exception as e:
            raise Exception(f"Google AI error: {str(e)}")

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