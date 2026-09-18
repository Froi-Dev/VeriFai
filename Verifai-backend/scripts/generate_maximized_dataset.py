"""Generate an augmented, maximized dataset using Gemini API pool and local human sources.

Exerts Gemini quota across all keys in parallel to produce:
1. Long-form AI essays and analyses (1,500 - 5,000+ chars) in English and Taglish
2. Humanized AI texts engineered to bypass AI detectors
3. Authentic LLM Taglish (academic, conversational, reflective)
4. Paired authentic human long-form texts from Chapter_4.docx and Rizal PDF
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_maximized_dataset")

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


# Core prompt templates for generating difficult AI text
TOPICS = [
    ("college commuter crisis in Metro Manila", "urban transit and daily life of Filipino students"),
    ("impact of artificial intelligence in higher education", "AI ethics, plagiarism, and future learning modalities"),
    ("blended learning and online capstone development", "student experiences, tech hurdles, and thesis revisions"),
    ("climate change resilience and flood control in the Philippines", "infrastructure, typhoons, and local governance"),
    ("mental health and academic pressure among university students", "burnout, counseling support, and peer dynamics"),
    ("the rise of fintech and digital wallets in Southeast Asia", "financial inclusion, cybersecurity risks, and micro-transactions"),
    ("social media algorithms and polarization in Philippine politics", "information echo chambers, fact-checking, and digital literacy"),
    ("renewable energy transition and solar microgrids in rural provinces", "sustainable development and energy poverty"),
    ("cybersecurity best practices and phishing awareness", "data privacy act, multi-factor authentication, and human factor"),
    ("work-from-home vs return-to-office culture in IT and BPO industries", "productivity, work-life balance, and urban congestion"),
    ("Philippine economic growth, inflation, and MSME competitiveness", "supply chain challenges and purchasing power"),
    ("modern mobile app architecture and reactive state management", "software engineering principles, scalability, and code maintainability"),
    ("preservation of indigenous languages and cultural heritage in the digital era", "linguistic diversity and education policy"),
    ("telemedicine adoption and healthcare disparities in remote islands", "public health infrastructure and doctor-to-patient ratio"),
    ("the ethical dilemmas of autonomous decision making in smart cities", "algorithmic bias, transparency, and public trust"),
    ("food security and agrarian reform challenges in Central Luzon", "farmer subsidies, climate adaptation, and market access"),
    ("e-sports and competitive gaming as a career in the Philippines", "social perception, professionalization, and training routines"),
    ("history of Philippine revolutionary literature and propaganda movement", "Rizal, Plaridel, and the awakening of national consciousness"),
    ("the psychology of procrastination and time management among thesis writers", "cognitive fatigue, deadlines, and habit formation"),
    ("cryptocurrency adoption and regulatory frameworks in developing economies", "remittances, volatility, and central bank digital currency"),
]

PROMPT_STYLES = [
    # 1. Long-form English Academic / Analytical Essay
    {
        "style_id": "long_en_academic",
        "language": "english",
        "domain": "academic",
        "template": (
            "Write an extensive, in-depth academic analysis (at least 500 to 700 words) discussing {topic} ({detail}). "
            "Structure the essay with a formal introduction outlining the conceptual framework, three substantive "
            "analytical body paragraphs with evidence and counter-perspectives, and a comprehensive conclusion with "
            "policy recommendations. Maintain scholarly tone and vocabulary."
        ),
    },
    # 2. Long-form Taglish Academic / Reflective Essay
    {
        "style_id": "long_taglish_academic",
        "language": "taglish",
        "domain": "academic",
        "template": (
            "Write a thorough 450 to 650-word academic and reflective essay in Taglish (Filipino-English code-switching) "
            "discussing {topic} ({detail}). Use natural code-switching commonly seen in university thesis papers and "
            "college discussions in Manila (combining Tagalog grammatical structure with English technical terms like "
            "'i-prioritize', 'na-observe', 'nag-implement', 'mag-focus'). Include an introduction, three detailed body "
            "paragraphs explaining the challenges and solutions, and a strong conclusion."
        ),
    },
    # 3. Humanized / Anti-Detector English (conversational, high burstiness, evasive)
    {
        "style_id": "humanized_en",
        "language": "english",
        "domain": "essay",
        "template": (
            "Write a detailed 400 to 600-word personal and analytical essay about {topic} ({detail}). "
            "IMPORTANT WRITING INSTRUCTIONS TO SOUND TRULY HUMAN: "
            "Write in a relaxed, thoughtful, and conversational human tone. Vary your sentence lengths dramatically—mix "
            "punchy short sentences with longer flowing thoughts. Use natural colloquial transitions (like 'Look,', 'Honestly,', "
            "'Here is the thing:', 'At the end of the day,', 'To be fair,'). Avoid robotic AI clichés such as 'delve', "
            "'tapestry', 'testament', 'crucial', 'in conclusion', 'beacon', or 'interconnected landscape'. Sound like an "
            "insightful human writer sharing honest thoughts and lived experiences."
        ),
    },
    # 4. Humanized / Anti-Detector Taglish
    {
        "style_id": "humanized_taglish",
        "language": "taglish",
        "domain": "casual",
        "template": (
            "Write a 400 to 550-word thoughtful, conversational article/reflection in natural Taglish about {topic} ({detail}). "
            "Make it sound completely human and authentic, like a college student or young professional writing an honest blog "
            "post or op-ed. Use conversational Filipino-English (e.g. 'Sa totoo lang', 'Kung tutuusin', 'Grabe', 'Para sa akin', "
            "'Aminin man natin o hindi'). Avoid overly formulaic textbook phrasing; use natural storytelling and practical reflections."
        ),
    },
    # 5. Explanatory & Practical Guide Taglish
    {
        "style_id": "guide_taglish",
        "language": "taglish",
        "domain": "guide",
        "template": (
            "Write a comprehensive 450 to 600-word practical explainer guide in Taglish about {topic} ({detail}). "
            "Break down the background, why it matters today, key steps or recommendations, and what students or professionals "
            "should expect. Use modern Philippine professional/student Taglish tone."
        ),
    },
]


def load_gemini_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("No GEMINI_API_KEYS found in environment")
    return keys


def call_gemini(
    prompt: str,
    key: str,
    model_name: str = "gemini-3.5-flash-lite",
    timeout: float = 30.0,
) -> str | None:
    models_to_try = [model_name, "gemini-3.6-flash"] if model_name != "gemini-3.6-flash" else ["gemini-3.6-flash", "gemini-3.5-flash-lite"]
    for current_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": random.uniform(0.7, 1.0),
                "topP": 0.95,
                "maxOutputTokens": 2048,
            },
        }
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                elif resp.status_code in (429, 503):
                    time.sleep(2.0 * (attempt + 1))
                    continue
                else:
                    break
            except Exception as exc:
                time.sleep(1.5)
    return None


def extract_human_thesis_long_forms(docx_path: Path) -> list[str]:
    """Extract and combine contiguous paragraphs from thesis Chapter 4 to form genuine long-form human documents."""
    if not docx_path.is_file():
        logger.warning("Chapter 4 docx not found at %s", docx_path)
        return []
    with zipfile.ZipFile(docx_path) as z:
        xml_content = z.read("word/document.xml")
    tree = ET.fromstring(xml_content)
    paragraphs = []
    for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        t = normalize_text("".join(p.itertext()))
        if len(t) > 60:
            paragraphs.append(t)

    # Stitch pairs and triplets into long documents (1,500 - 3,500 chars)
    long_docs = []
    cur = []
    cur_len = 0
    for p in paragraphs:
        cur.append(p)
        cur_len += len(p)
        if cur_len >= 1200:
            doc_text = "\n\n".join(cur)
            if len(doc_text) >= 1000:
                long_docs.append(doc_text)
            cur = []
            cur_len = 0
    if cur and cur_len >= 800:
        long_docs.append("\n\n".join(cur))
    return long_docs


def extract_human_rizal_long_forms(pdf_path: Path, max_docs: int = 150) -> list[str]:
    """Extract and stitch multi-paragraph sections from the Rizal textbook PDF into 1,200 - 3,500 char human documents."""
    if not pdf_path.is_file():
        logger.warning("Rizal PDF not found at %s", pdf_path)
        return []
    pdf = pdfium.PdfDocument(pdf_path)
    full_text = []
    for i in range(len(pdf)):
        page_text = pdf[i].get_textpage().get_text_range()
        lines = [l.strip() for l in page_text.splitlines()]
        clean = [
            l for l in lines
            if not l.startswith("Module")
            and "LIFE, WORKS AND WRITINGS" not in l
            and not l.startswith("Course Title")
            and not l.startswith("Page ")
            and len(l) > 10
        ]
        if clean:
            full_text.append(" ".join(clean))

    combined = "\n\n".join(full_text)
    raw_paras = [normalize_text(p) for p in combined.split("\n\n") if len(normalize_text(p)) > 80]

    long_docs = []
    cur: list[str] = []
    cur_len = 0
    for p in raw_paras:
        cur.append(p)
        cur_len += len(p)
        if cur_len >= 1500:
            doc_text = "\n\n".join(cur)
            if 1200 <= len(doc_text) <= 4000:
                long_docs.append(doc_text)
                if len(long_docs) >= max_docs:
                    break
            cur = []
            cur_len = 0
    return long_docs


def build_and_generate(
    base_dataset: Path,
    output_path: Path,
    target_ai_generations: int = 300,
    seed: int = 42,
) -> None:
    random.seed(seed)
    keys = load_gemini_keys()
    logger.info("Loaded %d Gemini API keys from environment", len(keys))

    rows: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    def add_row(r: dict[str, Any]) -> bool:
        text = normalize_text(r.get("text", ""))
        if len(text) < 30:
            return False
        h = hashlib.sha256(text.casefold().encode()).hexdigest()
        if h in seen_hashes:
            return False
        seen_hashes.add(h)
        r["text"] = text
        rows.append(r)
        return True

    # 1. Load baseline rows
    if base_dataset.is_file():
        with base_dataset.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    add_row(item)
        logger.info("Loaded %d existing rows from %s", len(rows), base_dataset)

    # 2. Extract Human Long-Forms from Chapter_4.docx and Rizal PDF
    thesis_docs = extract_human_thesis_long_forms(Path(r"C:\Users\dever\Downloads\Chapter_4.docx"))
    for idx, doc in enumerate(thesis_docs):
        add_row({
            "text": doc,
            "label": "human",
            "group_id": f"human:thesis-long-{idx}",
            "language": "english",
            "domain": "academic",
            "source": "student-thesis-longform",
        })
    logger.info("Added %d authentic human long-form documents from Chapter 4 docx", len(thesis_docs))

    rizal_docs = extract_human_rizal_long_forms(
        Path(r"C:\Users\dever\Downloads\ilide.info-life-and-works-of-rizal-module-pr_5957ab2f5018b4cc8e166d850a5d1d65.pdf"),
        max_docs=120,
    )
    for idx, doc in enumerate(rizal_docs):
        add_row({
            "text": doc,
            "label": "human",
            "group_id": f"human:rizal-long-{idx}",
            "language": "english",
            "domain": "academic",
            "source": "academic-textbook-longform",
        })
    logger.info("Added %d authentic human long-form documents from Rizal PDF", len(rizal_docs))

    # 3. Parallel generation using all 8 Gemini keys
    task_specs = []
    for topic, detail in TOPICS:
        for style in PROMPT_STYLES:
            prompt = style["template"].format(topic=topic, detail=detail)
            task_specs.append({
                "prompt": prompt,
                "topic": topic,
                "style_id": style["style_id"],
                "language": style["language"],
                "domain": style["domain"],
            })

    random.shuffle(task_specs)
    task_specs = task_specs[:target_ai_generations]
    logger.info("Dispatching %d targeted generation tasks across %d Gemini keys...", len(task_specs), len(keys))

    successful_gen = 0

    def worker(item_idx: int, task: dict[str, Any]) -> dict[str, Any] | None:
        key = keys[item_idx % len(keys)]
        prompt = task["prompt"]
        for attempt in range(2):
            result = call_gemini(prompt, key)
            if result and len(result.strip()) >= 250:
                return {
                    "text": result.strip(),
                    "label": "ai",
                    "group_id": f"gemini-gen:{task['style_id']}-{task['topic'][:25].casefold()}-{item_idx}",
                    "language": task["language"],
                    "domain": task["domain"],
                    "source": "gemini-synthesized",
                    "style": task["style_id"],
                }
            time.sleep(1.0)
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(worker, i, t): t for i, t in enumerate(task_specs)}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                if add_row(res):
                    successful_gen += 1
                    if successful_gen % 20 == 0 or successful_gen == len(task_specs):
                        logger.info("Generated %d / %d targeted AI samples", successful_gen, len(task_specs))

    logger.info("Finished generation: %d new targeted AI samples successfully added", successful_gen)

    # 4. Stratified Group Splits Assignment
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        gid = r["group_id"]
        grouped.setdefault(gid, []).append(r)

    group_keys = list(grouped.keys())
    random.shuffle(group_keys)

    test_count = max(1, round(len(group_keys) * 0.15))
    val_count = max(1, round(len(group_keys) * 0.10))
    calib_count = max(1, round(len(group_keys) * 0.10))

    for idx, gid in enumerate(group_keys):
        if idx < test_count:
            s = "test"
        elif idx < test_count + val_count:
            s = "validation"
        elif idx < test_count + val_count + calib_count:
            s = "calibration"
        else:
            s = "train"
        for item in grouped[gid]:
            item["split"] = s

    # Write output JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info("Saved %d total rows to %s", len(rows), output_path)
    label_counts = Counter(r["label"] for r in rows)
    lang_counts = Counter(r["language"] for r in rows)
    split_counts = Counter(r["split"] for r in rows)
    long_count = sum(1 for r in rows if len(r["text"]) >= 1200)

    logger.info("Summary: Labels=%s, Languages=%s, Splits=%s, LongDocs(>=1200 chars)=%d",
                dict(label_counts), dict(lang_counts), dict(split_counts), long_count)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-dataset",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\verifai_academic_hard_v5.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\verifai_v7_maximized.jsonl"),
    )
    parser.add_argument("--target-generations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    build_and_generate(
        args.base_dataset,
        args.output,
        target_ai_generations=args.target_generations,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
