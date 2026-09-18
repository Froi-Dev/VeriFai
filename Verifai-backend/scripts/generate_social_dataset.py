"""Generate an augmented social media dataset focusing on Captions, Posts, and Comments.

Utilizes the 8-key Gemini API pool to generate difficult AI social content:
1. AI Captions (Instagram/TikTok/Facebook hooks, emoji bullets, CTAs, hashtags)
2. AI Posts (LinkedIn/FB advice, synthetic reflections, structured lists, thought leadership)
3. AI Bot Comments (sycophantic praise, formulaic agreements, synthetic engagement)

Curates and balances authentic Human social content:
1. Real human comments and posts extracted from test_predictions_with_breakdown.csv
2. Authentic human colloquial Taglish rants, banter, student chatter, and local slang
3. Balances and combines with verifai_v7_maximized.jsonl into verifai_v8_social_maximized.jsonl
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import logging
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_social_dataset")

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


# Social Media AI generation templates
SOCIAL_TOPICS = [
    ("time management and productivity hacks for college students", "Pomodoro, Notion, avoiding burnout"),
    ("freelancing and remote work tips in the Philippines", "client acquisition, Upwork, Upward mobility"),
    ("saving money and budgeting on an allowance or first job", "digital banks, emergency fund, tipid tips"),
    ("morning routine habits for mental clarity and focus", "journaling, screen time reduction, hydration"),
    ("navigating imposter syndrome as a tech beginner", "coding journey, debugging resilience, learning in public"),
    ("tips for surviving thesis and capstone defense", "presentation confidence, mock defense, handling panel questions"),
    ("why consistency beats motivation every single time", "daily discipline, compound effect, small wins"),
    ("how to dress smart casual on a budget for young professionals", "capsule wardrobe, ukay finds, professional styling"),
    ("essential soft skills that schools don't teach you", "active listening, negotiation, emotional intelligence"),
    ("coffee shop study culture and best spots in Metro Manila", "wifi speed, quiet ambiance, study buddies"),
    ("overcoming social media fatigue and digital detox", "screen limits, mental peace, presence"),
    ("simple meal prep ideas for busy college students", "healthy budget meals, quick cooking, air fryer hacks"),
    ("lessons learned from failing my first college exam", "growth mindset, study realignment, bouncing back"),
    ("why you should start building a personal portfolio early", "GitHub projects, case studies, LinkedIn presence"),
    ("navigating the daily commuter struggle with a positive mindset", "podcasts during transit, patience, early wake-up"),
]

AI_SOCIAL_PROMPT_STYLES = [
    # 1. Instagram / TikTok Captions (Taglish)
    {
        "style_id": "ai_caption_taglish",
        "language": "taglish",
        "domain": "caption",
        "content_type": "caption",
        "template": (
            "Write a realistic AI-generated social media caption (Instagram/TikTok style) in natural Taglish about {topic} ({detail}). "
            "Follow common AI social media copywriting conventions: "
            "- Catchy opening hook with an emoji (e.g. 'Gusto mo bang...?', 'Stop scrolling if...', 'Here is the secret...') "
            "- Short body with 3-4 bullet points using emojis (👉, ✨, 📌, 💡) "
            "- Clear Call to Action (CTA) at the end (e.g. 'Save this post for later!', 'I-share mo 'to sa tropa mo!', 'Drop your thoughts below 👇') "
            "- 3-5 relevant hashtags at the bottom. Keep length around 80 to 200 words."
        ),
    },
    # 2. Instagram / TikTok Captions (English)
    {
        "style_id": "ai_caption_en",
        "language": "english",
        "domain": "caption",
        "content_type": "caption",
        "template": (
            "Write a high-converting AI-generated social media caption (Instagram/LinkedIn style) in English about {topic} ({detail}). "
            "Include: "
            "- An intriguing hook question or bold statement "
            "- 3 actionable bullet points with emojis "
            "- Strong engagement CTA ('Save this for your next study session 📌', 'Double tap if this resonates with you!') "
            "- 3-5 hashtags. Keep length between 70 and 180 words."
        ),
    },
    # 3. Facebook / LinkedIn Advice & Reflection Posts (Taglish)
    {
        "style_id": "ai_post_taglish",
        "language": "taglish",
        "domain": "post",
        "content_type": "post",
        "template": (
            "Write an AI-generated Facebook or LinkedIn thought-leadership / advice post in Taglish about {topic} ({detail}). "
            "Use the typical AI post structure: "
            "- 1-sentence provocative or relatable hook "
            "- Short 1-2 sentence paragraphs with plenty of white space "
            "- A numbered list of 3 insights or steps "
            "- A reflective didactic conclusion ('Tandaan: Hindi karera ang buhay...', 'At the end of the day, ang mahalaga ay...') "
            "- An engagement question inviting people to comment. Keep length around 120 to 280 words."
        ),
    },
    # 4. Facebook / LinkedIn Advice & Reflection Posts (English)
    {
        "style_id": "ai_post_en",
        "language": "english",
        "domain": "post",
        "content_type": "post",
        "template": (
            "Write an AI-generated LinkedIn / Facebook personal growth post in English about {topic} ({detail}). "
            "Use signature AI characteristics: "
            "- 'Most people believe X. But here is what actually works:' "
            "- Clean, symmetrical bullet points "
            "- Uplifting, didactic advice summarizing the key lesson "
            "- Ending question like 'What habit helped you most this year? Let me know in the comments below.' "
            "Length: 130 to 260 words."
        ),
    },
    # 5. Sycophantic Bot / ChatGPT Comments (Taglish)
    {
        "style_id": "ai_comment_taglish",
        "language": "taglish",
        "domain": "comment",
        "content_type": "comment",
        "template": (
            "Write 3 distinct AI bot / synthetic comments in Taglish responding to a post about {topic}. "
            "Make them sound like typical overly polite, structured ChatGPT comments: "
            "1. Enthusiastic agreement with moral praise (e.g. 'Napakagandang punto nito! Tunay ngang napakahalaga ng...') "
            "2. Specific agreement with a point (e.g. 'Sobrang agree ako sa sinabi mo tungkol sa...') "
            "3. Polite encouraging sign-off (e.g. 'Maraming salamat sa pagbabahagi ng inspirasyong ito! Keep it up!'). "
            "Separate each comment with '---'. Keep each comment between 20 and 60 words."
        ),
    },
    # 6. Sycophantic Bot / ChatGPT Comments (English)
    {
        "style_id": "ai_comment_en",
        "language": "english",
        "domain": "comment",
        "content_type": "comment",
        "template": (
            "Write 3 distinct AI bot / synthetic comments in English responding to a social media post about {topic}. "
            "Characteristics of bot comments: "
            "1. 'Such an insightful and well-articulated post! Thank you for sharing your journey...' "
            "2. 'I couldn't agree more with your point about consistency. In today\\'s fast-paced world, this is a vital reminder...' "
            "3. 'Great breakdown! What advice would you give to someone just starting out?' "
            "Separate each comment with '---'. Keep each comment between 20 and 60 words."
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
                "temperature": random.uniform(0.7, 0.95),
                "topP": 0.95,
                "maxOutputTokens": 1024,
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
            except Exception:
                time.sleep(1.5)
    return None


# Authentic human colloquial student and commuter social text library (negative controls)
AUTHENTIC_HUMAN_SOCIAL_SAMPLES = [
    # Commute / Everyday rants
    {"text": "Grabe kanina sa jeep ang init tapos na-stuck pa kami sa trapik sa may cubao gutom na gutom na ko pota haha", "domain": "comment", "lang": "taglish"},
    {"text": "shet 2 hours bago nakasakay ng mrt grabe yung pila hanggang labas ng kalsada hays pilipinas kelan ba aasenso", "domain": "post", "lang": "taglish"},
    {"text": "sobrang init ngayong hapon parang impiyerno na talaga paglabas mo tagaktak agad pawis pota", "domain": "comment", "lang": "taglish"},
    {"text": "kanina sa bus may sumakay na nagpapatugtog ng budots nang walang earphones nakakabwisit sobra hahahaha", "domain": "post", "lang": "taglish"},
    {"text": "buti na lang umabot ako sa jeep kundi late na naman ako sa 7am class ko skl", "domain": "comment", "lang": "taglish"},
    {"text": "traffic na naman sa commonwealth araw araw na lang bang ganito lord give me strength", "domain": "post", "lang": "taglish"},
    {"text": "grabe yung ulan kanina biglang baha agad sa espana basang basa medyas ko pota", "domain": "comment", "lang": "taglish"},
    {"text": "nakakaantok mag-commute lalo pag pauwi na tapos malamig yung aircon sa bus sarap matulog", "domain": "comment", "lang": "taglish"},

    # Campus & Academic struggles
    {"text": "skl guys grabe yung prof namin kanina biglang nagpa surprise quiz eh wala pa nga kaming natapos na module haha iyak na lang talaga bukas sa remedial", "domain": "post", "lang": "taglish"},
    {"text": "di ko na kaya tong sem na to sobra yung tambak ng requirements tapos sabay sabay pa defense pota", "domain": "post", "lang": "taglish"},
    {"text": "haha relate sobra lodi sana all nakapasa sa exam congrats!", "domain": "comment", "lang": "taglish"},
    {"text": "wala na finish na bagsak na naman sa quiz kanina hahahaha shot puno mamaya guys", "domain": "comment", "lang": "taglish"},
    {"text": "charot lang pala yung sinabi ni sir akala ko may defense na sa monday kinabahan ako dun ah", "domain": "comment", "lang": "taglish"},
    {"text": "eme lang yun haha tara kape mamaya sa may novaliches libre kita kung pumasa ka", "domain": "comment", "lang": "taglish"},
    {"text": "lods baka naman may reviewers ka sa calculus di ko talaga magets yung derivative pota haha", "domain": "comment", "lang": "taglish"},
    {"text": "puyat na naman kaka-revise ng thesis tapos sasabihin lang ng panel palitan yung title hays nakakaiyak", "domain": "post", "lang": "taglish"},
    {"text": "sana all tapos na mag-defense kami ng groupmates ko nganga pa rin sa chapter 4 haha", "domain": "comment", "lang": "taglish"},
    {"text": "ang hirap maging working student pota 4 hours lang tulog ko kagabi tapos reporting pa mamaya", "domain": "post", "lang": "taglish"},
    {"text": "shoutout sa mga groupmates kong pabigat haha sana masarap tulog niyo habang ako gumagawa ng slides pota", "domain": "post", "lang": "taglish"},
    {"text": "omg totoo ba pumasa tayo??? weh di nga haha akala ko uulitin ko tong subject na to eh", "domain": "comment", "lang": "taglish"},
    {"text": "hays another day another breakdown pero laban lang para sa diploma skl", "domain": "post", "lang": "taglish"},
    {"text": "ano ba yan bakit laging down yung student portal pag enrollment season nakakagigil haha", "domain": "comment", "lang": "taglish"},
    {"text": "yey tapos na midterm exams makakatulog na rin ng higit sa 5 hours salamat lord!!", "domain": "post", "lang": "taglish"},
    {"text": "walang kwenta talaga yung wifi sa campus laging nadidisconnect habang nagqui-quiz pota", "domain": "comment", "lang": "taglish"},

    # Casual banter, humor & food
    {"text": "sarap ng siomai rice sa tapat ng school panalo pampalipas gutom pagkatapos ng 3 hours lab", "domain": "comment", "lang": "taglish"},
    {"text": "tara g kape tayo mamaya treat ko basta ikaw mag explain ng assignment haha", "domain": "comment", "lang": "taglish"},
    {"text": "ang corny mo pre haha pero seryoso galing nung presentation niyo kanina", "domain": "comment", "lang": "taglish"},
    {"text": "parang gusto ko na lang maging patatas at least walang deadlines haha", "domain": "post", "lang": "taglish"},
    {"text": "gutom na ko sobra ano masarap kainin mcdo or jollibee bilis vote kayo haha", "domain": "post", "lang": "taglish"},
    {"text": "lodi cake salamat sa pa-milk tea kanina bawi ako sayo sa susunod haha", "domain": "comment", "lang": "taglish"},
    {"text": "uy gising ka pa ba patulong naman saglit dito sa code ko may bug eh", "domain": "comment", "lang": "taglish"},
    {"text": "grabe bilis ng araw friday na naman bukas tapos tambak na naman homework over the weekend hays", "domain": "post", "lang": "taglish"},
    {"text": "haha totoo yan pre lagi na lang ganyan si sir pag bad trip", "domain": "comment", "lang": "taglish"},
    {"text": "wag ka mag-alala marami tayong babagsak di ka nag-iisa damay damay na to hahaha", "domain": "comment", "lang": "taglish"},

    # English informal human posts & comments
    {"text": "honestly so exhausted today lol spent 2 hours debugging just to find out i missed a semicolon fml", "domain": "post", "lang": "english"},
    {"text": "lmao this is so true i literally fell asleep on the bus this morning and almost missed my stop", "domain": "comment", "lang": "english"},
    {"text": "can anyone recommend good coffee shops near ust with fast wifi and lots of outlets?? need to finish my paper asap", "domain": "post", "lang": "english"},
    {"text": "congrats man!! so proud of you, you worked so hard for this!", "domain": "comment", "lang": "english"},
    {"text": "tbh that professor gives the most random exam questions ever like where did that even come from haha", "domain": "comment", "lang": "english"},
    {"text": "finally submitted my capstone manuscript! feels like a huge weight lifted off my shoulders let's goooo", "domain": "post", "lang": "english"},
    {"text": "dude same here haha i literally gave up trying to understand question 4", "domain": "comment", "lang": "english"},
    {"text": "anyone else feeling super burnt out this week or is it just me lol", "domain": "post", "lang": "english"},
]


def load_human_from_csv(csv_path: Path) -> list[dict[str, Any]]:
    """Extract real human comments and posts from test_predictions_with_breakdown.csv."""
    if not csv_path.is_file():
        logger.warning("CSV not found at %s", csv_path)
        return []

    human_rows = []
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("label") == "human":
                text = normalize_text(row.get("text", ""))
                if len(text) >= 15:
                    ctype = row.get("content_type", "comment")
                    human_rows.append({
                        "id": f"csv_human_{hashlib.md5(text.encode()).hexdigest()[:10]}",
                        "text": text,
                        "label": "human",
                        "language": row.get("language", "english"),
                        "domain": ctype,
                        "content_type": ctype,
                        "group_id": f"csv_human_group_{ctype}",
                    })
    logger.info("Loaded %d human samples from %s", len(human_rows), csv_path.name)
    return human_rows


def build_and_generate_social_dataset(
    base_v7_path: Path,
    csv_breakdown_path: Path,
    output_path: Path,
    target_ai_per_style: int = 30,
    seed: int = 42,
) -> None:
    random.seed(seed)
    seen_hashes: set[str] = set()
    rows: list[dict[str, Any]] = []

    def add_row(r: dict[str, Any]) -> bool:
        t = normalize_text(r["text"])
        if len(t) < 15:
            return False
        h = hashlib.sha256(t.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            return False
        seen_hashes.add(h)
        r["text"] = t
        rows.append(r)
        return True

    # 1. Load baseline v7 maximized dataset
    if base_v7_path.is_file():
        with open(base_v7_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line.strip())
                add_row(item)
        logger.info("Loaded %d baseline rows from %s", len(rows), base_v7_path.name)

    # 2. Add authentic human comments & posts from CSV
    csv_human_samples = load_human_from_csv(csv_breakdown_path)
    added_csv = 0
    for s in csv_human_samples:
        if add_row(s):
            added_csv += 1
    logger.info("Added %d new unique human samples from CSV", added_csv)

    # 3. Add curated authentic human casual social rants & banter
    added_curated = 0
    for idx, item in enumerate(AUTHENTIC_HUMAN_SOCIAL_SAMPLES):
        r = {
            "id": f"human_social_curated_{idx:03d}",
            "text": item["text"],
            "label": "human",
            "language": item["lang"],
            "domain": item["domain"],
            "content_type": item["domain"],
            "group_id": f"human_social_{item['domain']}",
        }
        if add_row(r):
            added_curated += 1
    logger.info("Added %d curated authentic human social items", added_curated)

    # 4. Generate AI Social samples using Gemini API Pool
    keys = load_gemini_keys()
    logger.info("Loaded %d Gemini API keys for social generation", len(keys))

    task_specs = []
    # Build tasks across styles and topics
    for style in AI_SOCIAL_PROMPT_STYLES:
        # Repeat topics to reach target_ai_per_style
        count = 0
        topic_idx = 0
        while count < target_ai_per_style:
            topic, detail = SOCIAL_TOPICS[topic_idx % len(SOCIAL_TOPICS)]
            task_specs.append((style, topic, detail, count))
            count += 1
            topic_idx += 1

    random.shuffle(task_specs)
    logger.info("Queued %d Gemini AI social generation tasks", len(task_specs))

    successful_gen = 0

    def worker(task_idx: int, spec: tuple[dict[str, Any], str, str, int]) -> list[dict[str, Any]]:
        style, topic, detail, iter_idx = spec
        key = keys[task_idx % len(keys)]
        prompt = style["template"].format(topic=topic, detail=detail)
        out = call_gemini(prompt, key=key)
        if not out:
            return []

        results = []
        # Check if style returned multiple comments separated by ---
        if style["content_type"] == "comment" and "---" in out:
            pieces = [p.strip() for p in out.split("---") if len(p.strip()) >= 15]
            for c_idx, piece in enumerate(pieces):
                clean_comment = re.sub(r"^\d+\.\s*", "", piece).strip()
                clean_comment = clean_comment.strip('"\n\r ')
                if len(clean_comment) >= 15:
                    results.append({
                        "id": f"ai_gen_{style['style_id']}_{task_idx}_{c_idx}",
                        "text": clean_comment,
                        "label": "ai",
                        "language": style["language"],
                        "domain": style["domain"],
                        "content_type": style["content_type"],
                        "group_id": f"ai_gen_{style['style_id']}_{task_idx}",
                    })
        else:
            # Single piece (caption or post)
            clean_text = out.strip('"\n\r ')
            if len(clean_text) >= 20:
                results.append({
                    "id": f"ai_gen_{style['style_id']}_{task_idx}",
                    "text": clean_text,
                    "label": "ai",
                    "language": style["language"],
                    "domain": style["domain"],
                    "content_type": style["content_type"],
                    "group_id": f"ai_gen_{style['style_id']}_{task_idx}",
                })
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(worker, i, t): t for i, t in enumerate(task_specs)}
        for future in concurrent.futures.as_completed(futures):
            res_list = future.result()
            for item in res_list:
                if add_row(item):
                    successful_gen += 1
            if successful_gen % 25 == 0 and successful_gen > 0:
                logger.info("Generated %d AI social items so far...", successful_gen)

    logger.info("Finished AI social generation: %d new items successfully added", successful_gen)

    # 5. Group-safe Leakage Partitioning (Train / Val / Calibration / Test)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        gid = r.get("group_id") or hashlib.md5(r["text"].encode()).hexdigest()[:12]
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
    domain_counts = Counter(r.get("domain", "unknown") for r in rows)
    lang_counts = Counter(r.get("language", "unknown") for r in rows)
    split_counts = Counter(r.get("split", "unknown") for r in rows)

    logger.info(
        "Summary: Total=%d | Labels=%s | Domains=%s | Languages=%s | Splits=%s",
        len(rows),
        dict(label_counts),
        dict(domain_counts),
        dict(lang_counts),
        dict(split_counts),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-dataset",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\verifai_v7_maximized.jsonl"),
    )
    parser.add_argument(
        "--csv-breakdown",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\test_predictions_with_breakdown.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\verifai_v8_social_maximized.jsonl"),
    )
    parser.add_argument("--ai-per-style", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    build_and_generate_social_dataset(
        args.base_dataset,
        args.csv_breakdown,
        args.output,
        target_ai_per_style=args.ai_per_style,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
