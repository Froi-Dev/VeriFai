"""Fast Fake News & Fact-Checking Module using Gemini 3.5 Flash & High-Speed Search.

This module provides an ultra-fast verification pipeline:
1. Native Search Grounding (Gemini 3.5 Flash with live Google Search tool).
2. Fast Snippet-Based Search Fallback (Serper / SearchApi + Gemini 3.5 Flash Reasoning)
   which bypasses heavy page-scraping for sub-2-second fact-checking.
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# Ensure backend path is loaded
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.Global.config import settings

logger = logging.getLogger("fast_news_checker")

from app.FakeNewsAnalyzer.fast_prompt import RESPONSE_SCHEMA, SYSTEM_INSTRUCTION


class FastNewsChecker:
    """Ultra-fast fact checker using Gemini 3.5 Flash."""

    def __init__(self, model: str = "gemini-3.5-flash", timeout: float = 15.0) -> None:
        self.model = model
        self.timeout = timeout
        self.gemini_keys = list(dict.fromkeys(settings.gemini_api_key_list))
        self.serper_keys = getattr(settings, "serper_api_key_list", [])
        self._key_index = 0

    def _get_gemini_key(self) -> str:
        if not self.gemini_keys:
            raise ValueError("No Gemini API keys configured in settings.")
        key = self.gemini_keys[self._key_index % len(self.gemini_keys)]
        self._key_index += 1
        return key

    async def _search_serper(self, query: str, client: httpx.AsyncClient) -> list[dict[str, str]]:
        """Fetch fast live search snippets via Serper (Google Search API)."""
        if not self.serper_keys:
            return []
        key = self.serper_keys[0]
        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": 6, "gl": "ph"}
        headers = {"X-API-KEY": key, "Content-Type": "application/json"}
        try:
            resp = await client.post(url, headers=headers, json=payload, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("organic", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "date": item.get("date", ""),
                    })
                return results
        except Exception as exc:
            logger.debug(f"Serper search failed: {exc}")
        return []

    async def _verify_via_search_grounding(
        self, claim: str, client: httpx.AsyncClient, key: str
    ) -> dict[str, Any] | None:
        """Attempt native Gemini 3.5 Search Grounding (tools: [{'googleSearch': {}}])."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        prompt = (
            f"Fact-check this claim: \"{claim}\".\n\n"
            f"Requirements:\n"
            f"1. Search live web facts to verify if this claim is TRUE, FALSE, or MISLEADING.\n"
            f"2. Return verdict, confidence (0-100), concise explanation, and cited sources.\n"
            f"3. Format response as JSON."
        )
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"googleSearch": {}}],
        }

        resp = await client.post(url, headers={"x-goog-api-key": key}, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            cand = data.get("candidates", [{}])[0]
            parts = cand.get("content", {}).get("parts", [])
            text = "\n".join(part.get("text", "") for part in parts).strip()
            grounding = cand.get("groundingMetadata", {})

            # Extract cited web sources from grounding metadata
            sources = []
            for chunk in grounding.get("groundingChunks", []):
                web = chunk.get("web")
                if web and web.get("uri"):
                    sources.append({"title": web.get("title", "Google Search Source"), "url": web.get("uri")})

            # Parse JSON from text
            parsed = self._extract_json(text)
            if parsed:
                if not parsed.get("sources") and sources:
                    parsed["sources"] = sources
                parsed["method"] = "gemini_native_search_grounding"
                return parsed

            return {
                "verdict": "VERIFIED" if "verified" in text.lower() else "UNVERIFIED",
                "confidence": 80,
                "explanation": text,
                "sources": sources,
                "reasoning": "Direct Google Search grounding via Gemini 3.5 Flash",
                "method": "gemini_native_search_grounding",
            }
        return None

    async def _verify_via_fast_search_pipeline(
        self, claim: str, client: httpx.AsyncClient, key: str
    ) -> dict[str, Any]:
        """Ultra-fast fallback: Search live snippets + Gemini 3.5 Flash structured reasoning."""
        # 1. Fetch live search results
        t0 = time.perf_counter()
        search_results = await self._search_serper(claim, client)
        t_search = time.perf_counter() - t0

        # 2. Build concise evidence block
        if search_results:
            evidence_text = "\n\n".join([
                f"Source [{idx+1}]: {item['title']}\nURL: {item['url']}\nSnippet: {item['snippet']}"
                for idx, item in enumerate(search_results[:5])
            ])
        else:
            evidence_text = "No immediate search results found."

        # 3. Call Gemini 3.5 Flash with structured output
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        user_prompt = (
            f"CLAIM TO FACT-CHECK:\n\"{claim}\"\n\n"
            f"LIVE SEARCH RESULTS:\n{evidence_text}\n\n"
            f"Evaluate the claim strictly based on the live search results and your knowledge of authoritative facts."
        )

        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }

        t1 = time.perf_counter()
        resp = await client.post(url, headers={"x-goog-api-key": key}, json=payload)
        t_gemini = time.perf_counter() - t1

        if resp.status_code == 200:
            data = resp.json()
            cand = data.get("candidates", [{}])[0]
            parts = cand.get("content", {}).get("parts", [])
            text = "\n".join(part.get("text", "") for part in parts).strip()
            parsed = self._extract_json(text)
            if parsed:
                if not parsed.get("sources") and search_results:
                    parsed["sources"] = [{"title": r["title"], "url": r["url"]} for r in search_results[:3]]
                parsed["method"] = "fast_serper_gemini_3.5"
                parsed["search_time_seconds"] = round(t_search, 2)
                parsed["gemini_time_seconds"] = round(t_gemini, 2)
                return parsed

        # Fallback if parsing failed or status code error
        return {
            "verdict": "UNVERIFIED",
            "confidence": 0,
            "explanation": f"API request error: {resp.status_code} - {resp.text[:150]}",
            "sources": [],
            "reasoning": "Could not complete fast verification.",
            "method": "error",
        }

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        """Robustly parse JSON object from model output."""
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try finding outermost { ... }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                pass
        return None

    async def verify(self, claim: str, *, try_grounding: bool = False) -> dict[str, Any]:
        """Verify a news claim using the fastest available pathway."""
        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            key = self._get_gemini_key()

            # Strategy 1: Native Search Grounding (if explicitly enabled or key supports it)
            if try_grounding:
                try:
                    grounding_res = await self._verify_via_search_grounding(claim, client, key)
                    if grounding_res:
                        elapsed = time.perf_counter() - start_time
                        grounding_res["elapsed_seconds"] = round(elapsed, 2)
                        return grounding_res
                except Exception as exc:
                    logger.debug(f"Native grounding attempt failed: {exc}")

            # Strategy 2: Ultra-fast live search snippets (Serper) + Gemini 3.5 Flash (<2 seconds)
            res = await self._verify_via_fast_search_pipeline(claim, client, key)
            elapsed = time.perf_counter() - start_time
            res["elapsed_seconds"] = round(elapsed, 2)
            return res


# ---------------------------------------------------------------------------
# CLI / Terminal Demonstration
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 70)
    print(" VeriFai Fast Fake News Checker (Gemini 3.5 Flash)")
    print("=" * 70)

    args = sys.argv[1:]
    try_grounding = False
    if "--grounding" in args:
        try_grounding = True
        args.remove("--grounding")

    model = "gemini-3.5-flash-lite"
    if "--model" in args:
        m_idx = args.index("--model")
        if m_idx + 1 < len(args):
            model = args[m_idx + 1]
            args.pop(m_idx + 1)
            args.pop(m_idx)

    if args:
        claim = " ".join(args)
    else:
        claim = "Ferdinand Marcos Jr. signed the Maharlika Investment Fund Act into law."

    print(f"\n[Claim to Check]:\n\"{claim}\"\n")
    print(f"Model: {model}")
    print(f"Mode:  {'Native Google Search Grounding' if try_grounding else 'Ultra-Fast Search Snippets + Gemini 3.5'}")
    print("Analyzing and searching live data...")

    checker = FastNewsChecker(model=model)
    result = await checker.verify(claim, try_grounding=try_grounding)

    print("\n" + "-" * 70)
    print(f"VERDICT:    {result.get('verdict')} (Confidence: {result.get('confidence')}%)")
    print(f"LATENCY:    {result.get('elapsed_seconds')}s (Search: {result.get('search_time_seconds', 'N/A')}s, Gemini: {result.get('gemini_time_seconds', 'N/A')}s)")
    print(f"METHOD:     {result.get('method')}")
    print("-" * 70)
    print(f"EXPLANATION:\n{result.get('explanation')}\n")
    print(f"REASONING:\n{result.get('reasoning')}\n")
    
    sources = result.get("sources", [])
    if sources:
        print("SOURCES & CITATIONS:")
        for s in sources:
            print(f"  • {s.get('title')}: {s.get('url')}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
