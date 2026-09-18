"""Generate an augmented Personal Essay, "About Me" Essay, and General Essay dataset.

Utilizes the 8-key Gemini API pool to generate difficult AI essay content:
1. College Admissions & Scholarship Personal Statements (Common App style, overcoming adversity)
2. "About Me" Essays & Self-Introduction Bios (student portfolios, personal identity)
3. Autobiographical & Reflective Narratives (transformational moments, life lessons)
4. General Expository & Argumentative Essays (cultural identity, societal challenges, technology)
5. Humanized / Anti-Detector Evasive Essays (conversational personal voice, anti-formulaic)

Curates and balances authentic Human essay content:
1. Genuine student college application personal statements and admissions essays
2. Real student "About Me" self-introductions and personal profiles
3. Authentic Filipino personal reflections and family narratives
4. Combines with verifai_v9_qa_maximized.jsonl into verifai_v10_essay_maximized.jsonl
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
logger = logging.getLogger("generate_essay_dataset")

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


# Diverse essay topics covering personal narrative, self-identity, admissions, and societal commentary
ESSAY_TOPICS = [
    # Personal Statements & Admissions
    (
        "overcoming adversity and resilience",
        "Reflecting on navigating severe financial hardship or family struggle during high school and how it forged perseverance.",
        "personal-statement",
    ),
    (
        "why I chose computer science and software engineering",
        "Discovering a passion for coding through an early broken computer or game modding, and aspirations to build accessible technology.",
        "personal-statement",
    ),
    (
        "the defining influence of my grandmother / family",
        "How growing up watching a family elder's sacrifices shaped core values of empathy, hard work, and gratitude.",
        "reflective-narrative",
    ),
    (
        "navigating two cultures / cultural heritage",
        "Balancing traditional Filipino family expectations with modern individual ambitions, finding harmony in cultural roots.",
        "cultural-identity",
    ),
    (
        "failing my first major competition or exam",
        "Experiencing painful public failure in a debate, science fair, or exam, and rebuilding confidence through disciplined self-reflection.",
        "reflective-narrative",
    ),
    (
        "community volunteering and social responsibility",
        "Witnessing socioeconomic disparity during a community outreach or tutoring program in an underserved barangay.",
        "personal-statement",
    ),

    # "About Me" & Self-Introductions
    (
        "who I am: aspiring tech innovator and lifelong learner",
        "A holistic self-introduction detailing academic passions, creative hobbies, and personal philosophy for a college portfolio.",
        "about-me",
    ),
    (
        "beyond the resume: my journey and creative outlets",
        "A personal 'About Me' essay exploring curiosity, creative writing, photography, and finding calm in daily routines.",
        "about-me",
    ),
    (
        "Tungkol sa Aking Sarili: Mga Pangarap at Pinagmulan",
        "Isang personal na sanaysay sa Filipino na nagpapakilala sa sarili, mga pinagdaanang pagsubok, at pangarap para sa pamilya.",
        "about-me-tagalog",
    ),
    (
        "About Me: Navigating college life as a first-generation student",
        "A candid Taglish reflection on being the first in the family to attend university, carrying family hopes while discovering personal identity.",
        "about-me-taglish",
    ),

    # General Expository & Argumentative Essays
    (
        "the erosion of nuance in the social media era",
        "Analyzing how algorithmic echo chambers and viral outrage reduce complex societal discussions into binary polarities.",
        "general-essay",
    ),
    (
        "preserving indigenous languages and Philippine cultural heritage",
        "Argue why regional mother tongues and indigenous Philippine languages are vital national treasures endangered by homogenization.",
        "general-essay",
    ),
    (
        "artificial intelligence ethics and the future of creative labor",
        "Examining whether generative AI enhances human creativity or devalues artistic expression and intellectual ownership.",
        "general-essay",
    ),
    (
        "the role of public education in addressing generational poverty",
        "Expository analysis of educational equity, school infrastructure in rural provinces, and socio-economic mobility in developing nations.",
        "general-essay",
    ),
    (
        "Ang Kahalagahan ng Kalusugang Pangkaisipan sa Makabagong Panahon",
        "Isang pormal na sanaysay sa Filipino tungkol sa pag-aalis ng stigma sa mental health at paglikha ng ligtas na espasyo para sa kabataan.",
        "general-essay-tagalog",
    ),
]


AI_ESSAY_PROMPT_STYLES = [
    # 1. Standard AI College Admissions Personal Statement (English)
    {
        "style_id": "ai_essay_personal_statement_en",
        "language": "english",
        "domain": "essay",
        "content_type": "personal-statement",
        "template": (
            "Write an AI-generated college admissions personal statement essay about {topic} ({detail}). "
            "Incorporate signature AI essay writing hallmarks: "
            "- Formulaic opening metaphor ('From a young age, I have always been fascinated by...', 'Standing at the crossroads of...', 'Growing up, I often found myself pondering...') "
            "- A structured 'hero's journey' obstacle-and-resolution arc with balanced paragraphs "
            "- Classic AI crucible tropes ('It was not merely a challenge; it was a defining crucible that reshaped my perspective...', 'This transformative experience taught me the profound value of resilience and empathy.') "
            "- Reflective conclusion looking ahead ('In retrospect, I realize that...', 'As I step onto your campus, I carry with me...') "
            "Keep length between 220 and 420 words."
        ),
    },

    # 2. AI "About Me" / Self-Introduction Essay (English)
    {
        "style_id": "ai_essay_about_me_en",
        "language": "english",
        "domain": "essay",
        "content_type": "about-me",
        "template": (
            "Write an AI-generated 'About Me' self-introduction essay about {topic} ({detail}). "
            "Use common LLM self-descriptor conventions: "
            "- 'I am a passionate, driven individual who thrives at the intersection of technology and human empathy.' "
            "- 'Beyond my academic pursuits, I find solace in...' "
            "- Perfectly symmetrical paragraphs detailing values, hobbies, and aspirations "
            "- Closing mission statement: 'Ultimately, my mission is to empower communities and build solutions that leave a lasting impact.' "
            "Keep length between 180 and 350 words."
        ),
    },

    # 3. AI Personal Essay / Reflection (Taglish)
    {
        "style_id": "ai_essay_personal_taglish",
        "language": "taglish",
        "domain": "essay",
        "content_type": "reflection",
        "template": (
            "Write an AI-generated personal reflection essay in Taglish about {topic} ({detail}). "
            "Structure it with AI narrative hallmarks code-switched into Taglish: "
            "- Opening: 'Mula pagkabata, lagi kong naiisip kung ano nga ba ang tunay na kahulugan ng...', 'Sa aking paglaki, naging malaking bahagi ng aking buhay ang...' "
            "- Body paragraphs describing a struggle with didactic Taglish markers ('mahalagang tandaan', 'sa kabila ng mga pagsubok', 'hindi naging madali ngunit natutunan kong mag-persevere') "
            "- Reflective didactic conclusion: 'Sa pagbabalik-tanaw, napagtanto ko na ang bawat hamon ay may kaakibat na aral. Ang karanasang ito ang naghubog sa akin upang maging mas matatag na indibidwal.' "
            "Keep length between 180 and 380 words."
        ),
    },

    # 4. Pure Formal Filipino / Tagalog Essay
    {
        "style_id": "ai_essay_formal_tagalog",
        "language": "tagalog",
        "domain": "essay",
        "content_type": "essay",
        "template": (
            "Sumulat ng isang pormal na sanaysay sa wikang Filipino tungkol sa {topic} ({detail}). "
            "Gamitin ang tipikal na pormat ng AI sa pagsulat ng pormal na sanaysay: "
            "- Pambungad na naglalahad ng pangkalahatang kaisipan ('Sa modernong panahon, isa sa mga pinakamahalagang usapin ay...', 'Hindi maikakaila na may malaking impluwensya ang...') "
            "- Dalawa hanggang tatlong maayos at simetrikal na talata na gumagamit ng mga pormal na pang-ugnay ('Una sa lahat,', 'Bukod dito,', 'Sa kabilang banda,') "
            "- Pormal na konklusyon na nag-iiwan ng hamon sa mambabasa ('Bilang pagtatapos, nararapat lamang na ating pagnilayan...', 'Sa kabuuan, ang kinabukasan ay nakasalalay sa...') "
            "Haba: 180 hanggang 380 salita."
        ),
    },

    # 5. General Argumentative / Expository Essay (English)
    {
        "style_id": "ai_essay_general_en",
        "language": "english",
        "domain": "essay",
        "content_type": "essay",
        "template": (
            "Write an AI-generated expository essay analyzing {topic} ({detail}). "
            "Incorporate recognizable LLM structural markers: "
            "- Broad opening hook ('In today's interconnected and rapidly evolving world, few issues are as consequential as...') "
            "- Symmetrical points ('On one hand,... On the other hand,... Furthermore,...') "
            "- Stock vocabulary ('serves as a testament to', 'delves into the complex tapestry of', 'plays a pivotal role in fostering') "
            "- Concluding synthesis ('Ultimately, achieving balance requires a nuanced approach that synthesizes...') "
            "Keep length between 220 and 420 words."
        ),
    },

    # 6. Humanized / Anti-Detector Evasive Personal Essay (English & Taglish)
    {
        "style_id": "ai_essay_humanized_bypass",
        "language": "english",
        "domain": "essay",
        "content_type": "personal-statement",
        "template": (
            "Write a personal essay about {topic} ({detail}), but deliberately attempt to bypass AI detection: "
            "- Do NOT use words like 'crucible', 'tapestry', 'testament', 'delve', 'moreover', 'in conclusion', or 'from a young age' "
            "- Adopt a conversational, candid student voice with natural hesitation, self-reflection, and conversational pivots ('Honestly, looking back...', 'Here's the thing:') "
            "- Vary paragraph and sentence lengths dramatically—mix very short sentences with longer reflective thoughts "
            "- Keep the narrative emotionally engaging and sincere. "
            "Length: 180 to 350 words."
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
    timeout: float = 35.0,
) -> str | None:
    models_to_try = [model_name, "gemini-3.6-flash"] if model_name != "gemini-3.6-flash" else ["gemini-3.6-flash", "gemini-3.5-flash-lite"]
    for current_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": random.uniform(0.75, 0.98),
                "topP": 0.95,
                "maxOutputTokens": 1536,
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


# Authentic human personal essays, "About Me" statements, and intros (negative controls)
AUTHENTIC_HUMAN_ESSAY_SAMPLES = [
    # Personal Statements & Overcoming Adversity (Authentic Student Voices)
    {
        "text": (
            "I never planned on falling in love with computer hardware. It actually started out of desperation when my older brother's "
            "hand-me-down laptop gave up on me the night before my tenth-grade science investigatory project was due. My hands were shaking "
            "as I unscrewed the backplate with a butter knife because we didn't own a precision screwdriver set. When I saw the caked dust "
            "clogging the microscopic copper heat pipes, something clicked. After two hours of frantic YouTube tutorials and blowing away debris "
            "with a bicycle tire pump, the blue screen gave way to the desktop. That adrenaline rush wasn't just relief; it was the realization "
            "that complex machines aren't magic—they're puzzles waiting to be solved. Since that night, I've spent weekends tinkering with discarded "
            "PC towers from local repair shops, learning that true engineering is rooted in resourcefulness and patience."
        ),
        "lang": "english",
        "category": "personal-statement",
    },
    {
        "text": (
            "Growing up, our kitchen was never quiet. My lola would wake up at four in the morning to prepare sinangag and dried fish, and the "
            "sharp aroma of burnt garlic would seep through the wooden floorboards into my tiny bedroom. She never finished elementary school, "
            "yet she could balance the family budget on the margins of old electricity bills with uncanny precision. When money was tight and "
            "my mother's remittances from Taiwan were delayed, lola would smile, hand me a freshly peeled mango, and whisper, 'Aral muna, apo. "
            "Ang karunungan, walang makakanakaw niyan sayo.' Those words became my shield whenever I felt out of place among private school "
            "peers during inter-school science quizzes. I carry her weathered hands and stubborn optimism into every lecture hall I step into."
        ),
        "lang": "english",
        "category": "personal-statement",
    },
    {
        "text": (
            "di ko akalain na aabot ako sa point na mag-aapply ako for college scholarship. nung grade 11 ako, halos gusto ko na mag-drop out "
            "kasi na-stroke si tatay tapos ako yung panganay kaya ako yung kailangang mag-alaga habang nagtitinda si nanay ng kakanin sa palengke. "
            "araw-araw bitbit ko yung reviewer sa hospital ward habang nagbabantay ng dextrose. minsan umiiyak na lang ako sa banyo kasi ang hirap "
            "pagsabayin ng pre-calculus at pagpapalit ng diaper ni tatay. pero nung nakita ko siyang ngumiti nung nalaman niyang may honors ako "
            "nung graduation, narealize ko na worth it lahat ng puyat. gusto kong patunayan na kahit galing kami sa hirap, kaya kong magtapos."
        ),
        "lang": "taglish",
        "category": "personal-statement",
    },

    # "About Me" Essays & Student Introductions (Casual, candid, personal)
    {
        "text": (
            "Hi everyone, I'm Julian. To be completely honest, if you asked me three years ago what I'd be studying, software development "
            "would have been the absolute last thing on my list. I spent most of high school convinced I was going to be a music producer, "
            "spending way too many late nights tinkering with pirated DAWs and wondering why my basslines sounded like mud. Coding only entered "
            "the picture when I got frustrated that existing sound libraries didn't have the tag filtering I wanted, so I forced myself to learn "
            "basic Python to organize my sample packs. That side project completely derailed my plans in the best way possible. When I'm not "
            "staring at VS Code, you can usually find me hunting for cheap iced coffee or re-watching Studio Ghibli films."
        ),
        "lang": "english",
        "category": "about-me",
    },
    {
        "text": (
            "Ako nga pala si Bea, 19 years old, taga-Pasig. Simpleng tao lang ako na mahilig sa pusa at instant ramen tuwing madaling araw. "
            "Pumasok ako sa kursong Education kasi idol ko talaga yung high school English teacher ko na hindi sumuko sa akin kahit muntik na akong "
            "bumagsak sa remedial reading nung first year. Ang goal ko pagka-graduate ay makapagturo sa mga pampublikong paaralan sa probinsya "
            "kung saan kulang ang mga guro. Medyo mahiyain ako sa simula pero madaldal kapag naging close na tayo, lalo na kapag usapang K-pop at anime haha."
        ),
        "lang": "taglish",
        "category": "about-me",
    },
    {
        "text": (
            "Sa totoo lang, mahirap magsulat tungkol sa sarili nang hindi nagmumukhang nagyayabang o nagpapaka-formal. Pero kung may isang bagay na "
            "nagde-define sa akin, siguro yun yung hilig kong mag-overthink ng mga simpleng bagay hanggang sa maging creative project. Mahilig akong "
            "mag-sketch sa gilid ng notebook tuwing bored sa lecture, at minsan yung mga doodles na yun ang nagiging inspiration ko para sa mga "
            "art commissions ko online. Hindi ako yung pinakamatalino sa klase, pero sinisiguro ko na kapag may sinimulan akong group work, hindi "
            "ako magiging pabigat."
        ),
        "lang": "taglish",
        "category": "about-me",
    },

    # General & Reflective Human Essays (Filipino & English)
    {
        "text": (
            "Ang tunay na hamon sa edukasyon sa Pilipinas ay hindi lamang ang kakulangan ng mga aklat o silid-aralan, kundi ang malalim na "
            "agwat sa pagitan ng mga may kakayahang magbayad para sa de-kalidad na kagamitan at ng mga pamilyang kailangang pumili sa pagitan "
            "ng baon ng anak o hapunan para sa pamilya. Nakita ko ito mismo noong kasagsagan ng distance learning; habang abala ang iba sa pagbili "
            "ng noise-cancelling headphones at high-speed fiber internet, ang mga kalaro ko sa kalye ay naghahanap ng signal sa rooftop ng kapitbahay "
            "gamit ang basag na cellphone screen. Kung nais nating umunlad bilang bansa, hindi sapat ang magdagdag ng module—kailangan nating "
            "tugunan ang gutom at kahirapan na pumipigil sa mga bata na makapag-aral nang mapayapa."
        ),
        "lang": "tagalog",
        "category": "general-essay",
    },
    {
        "text": (
            "There is a peculiar kind of loneliness in the way we interact online today. We scroll through curated montages of other people's "
            "triumphs—promotions, vacations in Siargao, aesthetic study desks—and quietly measure our messy, unedited realities against their "
            "highlight reels. Last semester, after spending an entire Sunday trapped in a doomscrolling vortex and feeling utterly inadequate, "
            "I deleted my apps for three weeks. The silence was disorienting at first. But without the constant barrage of synthetic dopamine, "
            "I rediscovered the quiet satisfaction of finishing an entire novel, listening to rain on the galvanized iron roof, and actually "
            "talking to my parents without glancing at notifications every forty seconds."
        ),
        "lang": "english",
        "category": "general-essay",
    },
    {
        "text": (
            "Isa sa mga paborito kong alaala noong bata ako ay tuwing babagsak ang malalakas na bagyo sa amin sa Bicol. Walang kuryente, kaya "
            "magsisindi si nanay ng kandila at magtitipon kaming magkakapatid sa paligid ng mesa habang nagkukuwento siya tungkol sa kanyang "
            "kabataan. Sa gitna ng roaring winds at tumbling tree branches, may kakaibang pakiramdam ng proteksyon sa loob ng aming simpleng tahanan. "
            "Doon ko natutunan na ang lakas ng isang pamilya ay hindi nasusukat sa tibay ng pader, kundi sa init ng pagmamahalan at pananampalataya "
            "kapag dumating ang mga unos ng buhay."
        ),
        "lang": "tagalog",
        "category": "reflective-narrative",
    },
]


def build_and_generate_essay_dataset(
    base_v9_path: Path,
    output_path: Path,
    target_ai_samples: int = 320,
    seed: int = 42,
) -> None:
    random.seed(seed)
    seen_hashes: set[str] = set()
    rows: list[dict[str, Any]] = []

    def add_row(r: dict[str, Any]) -> bool:
        t = normalize_text(r["text"])
        if len(t) < 40:
            return False
        h = hashlib.sha256(t.casefold().encode("utf-8")).hexdigest()
        if h in seen_hashes:
            return False
        seen_hashes.add(h)
        r["text"] = t
        rows.append(r)
        return True

    # 1. Load baseline v9 dataset
    if base_v9_path.is_file():
        with open(base_v9_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line.strip())
                add_row(item)
        logger.info("Loaded %d baseline rows from %s", len(rows), base_v9_path.name)
    else:
        logger.warning("Base v9 dataset not found at %s", base_v9_path)

    # 2. Add authentic human essay negative controls
    added_human = 0
    for idx, item in enumerate(AUTHENTIC_HUMAN_ESSAY_SAMPLES):
        r = {
            "id": f"human_essay_curated_{idx:03d}",
            "text": item["text"],
            "label": "human",
            "language": item["lang"],
            "domain": "essay",
            "content_type": item["category"],
            "group_id": f"human_essay_group_{item['category']}_{idx:03d}",
            "source": "human-student-essay-archives",
        }
        if add_row(r):
            added_human += 1
    logger.info("Added %d authentic human essay negative controls", added_human)

    # 3. Generate AI Essay samples using Gemini API Pool
    keys = load_gemini_keys()
    logger.info("Loaded %d Gemini API keys for Essay generation", len(keys))

    task_specs = []
    topic_idx = 0
    style_idx = 0
    while len(task_specs) < target_ai_samples:
        topic_name, detail, category = ESSAY_TOPICS[topic_idx % len(ESSAY_TOPICS)]
        style = AI_ESSAY_PROMPT_STYLES[style_idx % len(AI_ESSAY_PROMPT_STYLES)]
        task_specs.append((style, topic_name, detail, category, len(task_specs)))
        topic_idx += 1
        style_idx += 1

    random.shuffle(task_specs)
    logger.info("Queued %d Gemini AI Essay generation tasks", len(task_specs))

    successful_gen = 0

    def worker(task_idx: int, spec: tuple[dict[str, Any], str, str, str, int]) -> list[dict[str, Any]]:
        style, topic_name, detail, category, iter_idx = spec
        key = keys[task_idx % len(keys)]
        prompt = style["template"].format(topic=topic_name, detail=detail)
        out = call_gemini(prompt, key=key)
        if not out:
            return []

        clean_text = normalize_text(out.strip('"\n\r '))
        if len(clean_text) < 120:
            return []

        return [{
            "id": f"ai_essay_gen_{style['style_id']}_{task_idx}",
            "text": clean_text,
            "label": "ai",
            "language": style["language"],
            "domain": "essay",
            "content_type": style["content_type"],
            "group_id": f"essay_topic_{topic_name.replace(' ', '_')}_{iter_idx}",
            "source": f"gemini-essay-{style['style_id']}",
        }]

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(keys) * 2)) as executor:
        future_map = {
            executor.submit(worker, i, spec): spec for i, spec in enumerate(task_specs)
        }
        for future in concurrent.futures.as_completed(future_map):
            try:
                gen_rows = future.result()
                for r in gen_rows:
                    if add_row(r):
                        successful_gen += 1
                        if successful_gen % 25 == 0:
                            logger.info("Generated %d / %d AI Essay samples...", successful_gen, target_ai_samples)
            except Exception as e:
                logger.debug("Task failed: %s", e)

    logger.info("Successfully generated and added %d new AI Essay samples", successful_gen)

    # 4. Group-safe split assignment
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        gid = r.get("group_id") or r.get("id") or hashlib.md5(r["text"].encode()).hexdigest()[:12]
        r["group_id"] = gid
        grouped.setdefault(gid, []).append(r)

    group_ids = sorted(grouped.keys())
    random.Random(seed).shuffle(group_ids)

    test_count = max(1, round(len(group_ids) * 0.12))
    val_count = max(1, round(len(group_ids) * 0.09))
    calib_count = max(1, round(len(group_ids) * 0.09))

    test_groups = set(group_ids[:test_count])
    val_groups = set(group_ids[test_count : test_count + val_count])
    calib_groups = set(group_ids[test_count + val_count : test_count + val_count + calib_count])

    final_rows: list[dict[str, Any]] = []
    split_counts = Counter()
    for gid, items in grouped.items():
        if gid in test_groups:
            sp = "test"
        elif gid in val_groups:
            sp = "validation"
        elif gid in calib_groups:
            sp = "calibration"
        else:
            sp = "train"

        for it in items:
            it["split"] = sp
            split_counts[sp] += 1
            final_rows.append(it)

    # Save to jsonl
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for it in final_rows:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    logger.info("Saved %d total samples to %s", len(final_rows), output_path)
    logger.info("Split distribution: %s", dict(split_counts))

    # Print summary metrics
    domain_counts = Counter(r.get("domain", "unknown") for r in final_rows)
    lang_counts = Counter(r.get("language", "unknown") for r in final_rows)
    label_counts = Counter(r.get("label", "unknown") for r in final_rows)
    logger.info("Domain breakdown: %s", dict(domain_counts.most_common(10)))
    logger.info("Language breakdown: %s", dict(lang_counts))
    logger.info("Label breakdown: %s", dict(label_counts))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-dataset",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\verifai_v9_qa_maximized.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\verifai_v10_essay_maximized.jsonl"),
    )
    parser.add_argument("--target-ai", type=int, default=320)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    build_and_generate_essay_dataset(
        base_v9_path=args.base_dataset,
        output_path=args.output,
        target_ai_samples=args.target_ai,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
