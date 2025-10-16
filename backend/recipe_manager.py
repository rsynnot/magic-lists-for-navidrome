import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

class RecipeManager:
    """Manages playlist generation recipes and their application"""
    
    def __init__(self, recipes_dir: str = "recipes"):
        self.recipes_dir = Path(recipes_dir)
        self.registry_path = self.recipes_dir / "registry.json"
        self._registry_cache = None
        self._recipe_cache = {}
    
    def _load_registry(self) -> Dict[str, str]:
        """Load the recipe registry mapping playlist types to recipe files"""
        if self._registry_cache is None:
            try:
                with open(self.registry_path, 'r') as f:
                    self._registry_cache = json.load(f)
            except FileNotFoundError:
                raise Exception(f"Recipe registry not found at {self.registry_path}")
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON in recipe registry: {e}")
        
        return self._registry_cache
    
    def _load_recipe(self, recipe_filename: str) -> Dict[str, Any]:
        """Load a specific recipe file"""
        if recipe_filename not in self._recipe_cache:
            recipe_path = self.recipes_dir / recipe_filename
            try:
                with open(recipe_path, 'r') as f:
                    self._recipe_cache[recipe_filename] = json.load(f)
            except FileNotFoundError:
                raise Exception(f"Recipe file not found: {recipe_path}")
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON in recipe file {recipe_filename}: {e}")
        
        return self._recipe_cache[recipe_filename]
    
    def get_recipe(self, playlist_type: str) -> Dict[str, Any]:
        """Get the current recipe for a playlist type"""
        registry = self._load_registry()
        
        if playlist_type not in registry:
            raise Exception(f"No recipe registered for playlist type: {playlist_type}")
        
        recipe_filename = registry[playlist_type]
        return self._load_recipe(recipe_filename)
    
    def _evaluate_math_expressions(self, obj: Any, inputs: Dict[str, Any]) -> Any:
        """First pass: Evaluate {{MATH:...}} expressions before regular replacements."""
        import re
        import math
        
        if isinstance(obj, str):
            # Find all {{MATH:...}} patterns
            math_pattern = r'\{\{MATH:([^}]+)\}\}'
            
            def evaluate_math(match):
                expression = match.group(1)
                
                # Replace DESIRED_TRACK_COUNT with actual value inside math expression
                if "DESIRED_TRACK_COUNT" in expression:
                    expression = expression.replace("DESIRED_TRACK_COUNT", str(inputs.get("num_tracks", 25)))
                
                try:
                    # Evaluate the math expression safely
                    # Allow basic math operations and functions
                    allowed_names = {
                        "__builtins__": {},
                        "abs": abs, "round": round, "min": min, "max": max,
                        "ceil": math.ceil, "floor": math.floor,
                        "pow": pow, "sqrt": math.sqrt
                    }
                    
                    result = eval(expression, allowed_names, {})
                    
                    # Convert to integer if it's a whole number
                    if isinstance(result, float) and result.is_integer():
                        result = int(result)
                    
                    return str(result)
                    
                except Exception as e:
                    print(f"❌ Math evaluation failed for '{expression}': {e}")
                    return match.group(0)  # Return original if evaluation fails
            
            # Replace all math expressions
            return re.sub(math_pattern, evaluate_math, obj)
            
        elif isinstance(obj, dict):
            return {key: self._evaluate_math_expressions(value, inputs) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._evaluate_math_expressions(item, inputs) for item in obj]
        else:
            return obj

    def _recursive_replace(self, obj: Any, replacements: Dict[str, str]) -> Any:
        """Recursively traverse and replace placeholders in strings within nested structures"""
        if isinstance(obj, dict):
            return {key: self._recursive_replace(value, replacements) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._recursive_replace(item, replacements) for item in obj]
        elif isinstance(obj, str):
            # Replace all placeholders in the string
            result = obj
            for placeholder, replacement in replacements.items():
                result = result.replace(placeholder, replacement)
            return result
        else:
            # Return unchanged for other types (int, float, bool, None)
            return obj
    
    def apply_recipe(self, playlist_type: str, inputs: Dict[str, Any], include_reasoning: bool = False) -> Dict[str, Any]:
        """Apply a recipe with given inputs and return the fully substituted recipe"""
        recipe = self.get_recipe(playlist_type)
        
        # Get recipe filename for logging
        registry = self._load_registry()
        recipe_filename = registry.get(playlist_type, "unknown")
        
        # Check if this is a new-style recipe (has llm_config) or legacy recipe
        if "llm_config" in recipe:
            # New recipe format - use recursive replacement
            replacements = {}
            
            # Map common inputs to new placeholder format
            if "artists" in inputs:
                replacements["{{TARGET_ARTIST}}"] = str(inputs["artists"])
            if "num_tracks" in inputs:
                replacements["{{DESIRED_TRACK_COUNT}}"] = str(inputs["num_tracks"])
            
            print(f"🔄 Processing recipe with {len(replacements)} placeholder replacements")
            
            # Map re-discover specific inputs
            if "candidate_tracks_json" in inputs:
                replacements["{{CANDIDATE_TRACKS_JSON}}"] = str(inputs["candidate_tracks_json"])
            if "analysis_summary" in inputs:
                replacements["{{ANALYSIS_SUMMARY}}"] = str(inputs["analysis_summary"])
            
            
            # Pass 1: Evaluate math expressions first
            math_evaluated_recipe = self._evaluate_math_expressions(recipe, inputs)
            
            # Pass 2: Apply recursive replacement to the entire recipe
            final_recipe = self._recursive_replace(math_evaluated_recipe, replacements)
            
            # Verify critical replacements occurred
            model_instructions = final_recipe.get("model_instructions", "")
            if "{{TARGET_ARTIST}}" in model_instructions or "{{DESIRED_TRACK_COUNT}}" in model_instructions:
                print(f"⚠️  Placeholder replacement failed - check recipe template")
            else:
                print(f"✅ Recipe processed successfully")
            
            # Add tracks data to the final recipe for AI processing
            if "tracks_data" in inputs:
                final_recipe["tracks_data"] = inputs["tracks_data"]
            
            return final_recipe
        
        else:
            # Legacy recipe format - maintain backward compatibility
            print(f"🍳 Using LEGACY recipe format: {recipe_filename}")
            print(f"📋 Recipe version: {recipe.get('version', 'N/A')}")
            print(f"📝 Recipe description: {recipe.get('description', 'N/A')[:100]}...")
            if recipe.get('llm_params'):
                print(f"🤖 Model fallback: {recipe.get('llm_params', {}).get('model_fallback', 'N/A')}")
                print(f"🌡️ Temperature: {recipe.get('llm_params', {}).get('temperature', 'N/A')}")
                print(f"🔢 Max tokens: {recipe.get('llm_params', {}).get('max_tokens', 'N/A')}")
            # Validate inputs
            required_inputs = recipe.get("inputs", [])
            missing_inputs = [inp for inp in required_inputs if inp not in inputs]
            if missing_inputs:
                raise Exception(f"Missing required inputs for {playlist_type}: {missing_inputs}")
            
            # Select the appropriate prompt template
            if include_reasoning and "prompt_template_with_reasoning" in recipe:
                prompt_template = recipe["prompt_template_with_reasoning"]
            else:
                prompt_template = recipe["prompt_template"]
            
            if prompt_template is None:
                # This recipe doesn't use LLM (e.g., re_discover uses algorithmic approach)
                return {
                    "recipe": recipe,
                    "prompt": None,
                    "llm_params": recipe.get("llm_params"),
                    "inputs": inputs
                }
            
            # Fill in the prompt template
            try:
                filled_prompt = prompt_template.format(**inputs)
            except KeyError as e:
                raise Exception(f"Missing template variable in recipe {playlist_type}: {e}")
            
            # Get LLM parameters
            llm_params = recipe.get("llm_params", {})
            
            return {
                "recipe": recipe,
                "prompt": filled_prompt,
                "llm_params": llm_params,
                "inputs": inputs
            }
    
    def list_available_recipes(self) -> Dict[str, Dict[str, Any]]:
        """List all available recipes with their metadata"""
        registry = self._load_registry()
        recipes_info = {}
        
        for playlist_type, recipe_filename in registry.items():
            try:
                recipe = self._load_recipe(recipe_filename)
                recipes_info[playlist_type] = {
                    "filename": recipe_filename,
                    "version": recipe.get("version"),
                    "description": recipe.get("description"),
                    "inputs": recipe.get("inputs", []),
                    "uses_llm": recipe.get("prompt_template") is not None
                }
            except Exception as e:
                recipes_info[playlist_type] = {
                    "filename": recipe_filename,
                    "error": str(e)
                }
        
        return recipes_info
    
    def validate_recipe(self, recipe_filename: str) -> List[str]:
        """Validate a recipe file and return any errors"""
        errors = []
        
        try:
            recipe = self._load_recipe(recipe_filename)
            
            # Check required fields
            required_fields = ["version", "description", "inputs", "strategy_notes"]
            for field in required_fields:
                if field not in recipe:
                    errors.append(f"Missing required field: {field}")
            
            # Check that inputs is a list
            if "inputs" in recipe and not isinstance(recipe["inputs"], list):
                errors.append("'inputs' must be a list")
            
            # Check prompt template if present
            if recipe.get("prompt_template"):
                # Try to identify placeholders in the template
                import re
                placeholders = re.findall(r'\{(\w+)\}', recipe["prompt_template"])
                inputs = recipe.get("inputs", [])
                
                # Check if all placeholders have corresponding inputs (allowing for some flexibility)
                for placeholder in placeholders:
                    if placeholder not in inputs and placeholder not in ["tracks_data", "num_tracks"]:
                        errors.append(f"Placeholder '{placeholder}' in prompt_template not found in inputs")
            
            # Validate LLM params if present
            if recipe.get("llm_params"):
                llm_params = recipe["llm_params"]
                if not isinstance(llm_params, dict):
                    errors.append("'llm_params' must be an object")
                
                # Check for valid temperature range
                if "temperature" in llm_params:
                    temp = llm_params["temperature"]
                    if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                        errors.append("'temperature' must be a number between 0 and 2")
        
        except Exception as e:
            errors.append(f"Failed to load recipe: {e}")
        
        return errors
    
    def clear_cache(self):
        """Clear the internal cache (useful for development/testing)"""
        self._registry_cache = None
        self._recipe_cache = {}

# Global instance for use throughout the application
recipe_manager = RecipeManager()