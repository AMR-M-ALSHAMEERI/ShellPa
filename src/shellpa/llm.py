import os
from pydantic import BaseModel, Field
from litellm import completion

class CommandResponse(BaseModel):
    command: str = Field(description="The shell command to execute.")
    explanation: str = Field(description="A brief explanation of what the command does.")

def generate_command(query: str, env_info: dict) -> CommandResponse:
    """Uses the LLM to generate a shell command based on the user's query."""
    system_prompt = f"""
You are a CLI agent. Your task is to translate natural language into a system shell command.
Target Operating System: {env_info['os']}
Target Shell: {env_info['shell']}

Respond ONLY with a valid JSON object matching this exact schema:
{{
    "command": "<the exact shell command>",
    "explanation": "<a brief explanation of what the command does>"
}}
Do not include any formatting like markdown blocks. Escape JSON properties properly.
"""
    # Grab user-configured model from setup wizard, default to OpenRouter 3.5 turbo
    model = os.getenv("SHELLPA_MODEL", "openrouter/openai/gpt-3.5-turbo")
    
    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ],
        response_format={"type": "json_object"}
    )
    
    content = response.choices[0].message.content.strip()
    
    # Clean possible markdown formatting left by the LLM (like ```json ... ```)
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
        
    content = content.strip()
    
    return CommandResponse.model_validate_json(content)
