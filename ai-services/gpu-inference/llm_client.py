"""
Qwen2.5-7B-Instruct client via Ollama — master build document §3.5.

This is a thin client, not a server: Ollama itself serves the OpenAI-
compatible API at :11434 (development_rule.md §1.3's `grmt-gpu-inference`
Studio, run sequentially with Binoculars per §3.6/§7 to stay within a
single L4's VRAM budget). This module is imported by the backend's AI
Orchestration Service once that's wired up — see backend/app/routers/
submissions.py's docstring for what's still a placeholder there.

Lowest-priority AI check in the product (master doc §1.6, development_rule.md
§7.4 descope list) — wire GROQ_API_KEY as a hosted-API fallback via
call_hosted_fallback() below if local Ollama serving isn't reliable during
integration (master doc §7.3 Day 11).
"""
import os

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_TAG = os.environ.get("OLLAMA_MODEL_TAG", "qwen2.5:7b-instruct-q4_K_M")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


async def check_logical_consistency(abstract: str, conclusion: str) -> dict:
    """master doc §3.5 — soft signal only, never a hard gate."""
    prompt = (
        "You are reviewing an academic paper for internal logical consistency only, "
        "not scientific merit. Compare the abstract and conclusion below. "
        "Respond with a short JSON object: "
        '{"consistent": true|false, "explanation": "one or two sentences"}.\n\n'
        f"ABSTRACT:\n{abstract}\n\nCONCLUSION:\n{conclusion}"
    )
    return await _generate(prompt, expect_json=True)


async def generate_cross_conference_summary(prior_paper_context: str) -> str:
    """master doc §1.5 — the ~200-word resubmission summary shown to organizers/reviewers of the NEW conference only."""
    prompt = (
        "Summarize in about 200 words why this paper was previously rejected "
        "and what appears to have changed in this resubmission, for a conference "
        "organizer's eyes only. Be factual and neutral.\n\n" + prior_paper_context
    )
    result = await _generate(prompt, expect_json=False)
    return result.get("text", "")


async def _generate(prompt: str, expect_json: bool) -> dict:
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_TAG,
                    "prompt": prompt,
                    "stream": False,
                    **({"format": "json"} if expect_json else {}),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return {"text": data.get("response", "")}
    except httpx.HTTPError as e:
        if GROQ_API_KEY:
            return await _call_hosted_fallback(prompt)
        raise RuntimeError(
            f"Ollama unreachable at {OLLAMA_URL} and no GROQ_API_KEY fallback configured. "
            f"See master doc §7.3 Day 11 for the fallback-wiring plan. Original error: {e}"
        )


async def _call_hosted_fallback(prompt: str) -> dict:
    """
    Groq free-tier fallback per master doc §7.3 Day 11 / §7.4 descope plan —
    used when local Ollama serving isn't reliable during integration. Model
    name is illustrative; confirm current Groq model availability before
    relying on this in a demo.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {"text": data["choices"][0]["message"]["content"]}
