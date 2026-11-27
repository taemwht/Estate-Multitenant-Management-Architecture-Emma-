"""
The AI model behind EMMA's chat. Which one is a setting in Emma/.env:

    CHAT_PROVIDER=openai
    CHAT_MODEL=gpt-6-luna

To add another provider, write one more `_run_<name>` function with the
same shape and add it to PROVIDERS. Nothing else needs to change.

`run_chat` drives the tool loop: the model asks for tools, `execute`
runs them (as the signed-in person), the results go back, until the
model writes its answer or the step limit is hit.
"""
import json
from typing import Awaitable, Callable

import httpx

from ..config import settings

Execute = Callable[[str, dict], Awaitable[str]]


class ChatError(Exception):
    """Something went wrong talking to the AI provider. Message is safe to show."""


async def _run_openai(system: str, messages: list, tools: list, execute: Execute) -> str:
    if not settings.openai_api_key:
        raise ChatError("EMMA's chat isn't set up yet (no OPENAI_API_KEY).")
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    items = [{"role": m["role"], "content": m["content"]} for m in messages]
    tool_defs = [{"type": "function", "name": t["name"], "description": t["description"],
                  "parameters": t["parameters"]} for t in tools]

    async with httpx.AsyncClient(base_url=settings.openai_base_url, headers=headers,
                                 timeout=settings.chat_timeout_seconds) as client:
        for step in range(settings.chat_max_steps + 1):
            last = step == settings.chat_max_steps
            payload = {
                "model": settings.chat_model,
                "instructions": system,
                "input": items,
                "tools": tool_defs,
                "tool_choice": "none" if last else "auto",
                "store": False,
                "include": ["reasoning.encrypted_content"],
                "max_output_tokens": settings.chat_max_output_tokens,
            }
            if settings.chat_reasoning_effort:
                payload["reasoning"] = {"effort": settings.chat_reasoning_effort}
            try:
                r = await client.post("/responses", json=payload)
            except httpx.HTTPError as e:
                raise ChatError(f"Couldn't reach the AI service ({type(e).__name__}).") from e
            if r.status_code != 200:
                try:
                    detail = r.json().get("error", {}).get("message", "")
                except ValueError:
                    detail = ""
                raise ChatError(f"The AI service returned an error ({r.status_code}). {detail[:200]}".strip())
            output = r.json().get("output", [])
            calls = [o for o in output if o.get("type") == "function_call"]
            if not calls:
                text = "".join(
                    c.get("text", "")
                    for o in output if o.get("type") == "message"
                    for c in o.get("content", []) if c.get("type") == "output_text"
                ).strip()
                return text or "Sorry, I didn't get an answer for that. Could you try rephrasing?"
            items += output
            for call in calls:
                try:
                    args = json.loads(call.get("arguments") or "{}")
                except ValueError:
                    args = None
                result = (await execute(call["name"], args) if isinstance(args, dict)
                          else json.dumps({"error": "arguments were not valid JSON"}))
                items.append({"type": "function_call_output", "call_id": call["call_id"], "output": result})
    raise ChatError("That took too many steps. Try asking something more specific.")


PROVIDERS = {"openai": _run_openai}


async def run_chat(system: str, messages: list, tools: list, execute: Execute) -> str:
    run = PROVIDERS.get(settings.chat_provider.strip().lower())
    if run is None:
        raise ChatError(f"Unknown CHAT_PROVIDER '{settings.chat_provider}'. Supported: {', '.join(PROVIDERS)}.")
    return await run(system, messages, tools, execute)
