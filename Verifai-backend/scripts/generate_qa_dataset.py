"""Generate an augmented Question-and-Answer (Q&A) dataset.

Utilizes the 8-key Gemini API pool to generate difficult AI answers to questions:
1. Academic & STEM Q&A (physics, biology, chemistry, economics)
2. Philippine History, Civics & Social Studies Q&A (Rizal Law, Propaganda, Constitution)
3. Computer Science, Programming & IT Q&A (SQL vs NoSQL, async/await, architecture)
4. Student Homework & Short Exam Answers (essay prompts, conceptual questions)
5. Humanized / Bypass AI Q&A (conversational evasions, anti-detector prompts)

Curates and balances authentic Human Q&A content:
1. Direct, concise student homework answers and exam definitions
2. Colloquial peer-to-peer Taglish study explanations and forum answers
3. Authentic textbook Q&A passages from the Rizal module and academic documents
4. Combines with verifai_v8_social_maximized.jsonl into verifai_v9_qa_maximized.jsonl
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
logger = logging.getLogger("generate_qa_dataset")

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").split())


# Diverse Q&A topics covering STEM, History, Tech, and Student Exam questions
QA_TOPICS = [
    # STEM & Science
    ("mitosis vs meiosis", "Explain the difference between mitosis and meiosis in terms of purpose, chromosome count, and daughter cells.", "biology"),
    ("photosynthesis mechanism", "How does photosynthesis convert sunlight, carbon dioxide, and water into glucose and oxygen?", "biology"),
    ("Newton's third law of motion", "Explain Newton's third law of motion and give two real-life everyday examples.", "physics"),
    ("CRISPR gene editing", "How does the CRISPR-Cas9 gene editing system work and why is it revolutionary in biotechnology?", "biotech"),
    ("law of supply and demand", "Explain the law of supply and demand and how market equilibrium is established.", "economics"),
    ("thermodynamics second law", "What is the second law of thermodynamics and how does entropy relate to the arrow of time?", "physics"),
    ("how vaccines build immunity", "How do mRNA and traditional vaccines train the human immune system to fight pathogens?", "medicine"),
    ("plate tectonics and earthquakes", "What causes earthquakes along tectonic fault lines and how do seismic waves travel?", "earth-science"),

    # Philippine History, Civics & Culture
    ("Rizal Law (RA 1425)", "Bakit ipinasa ang Republic Act 1425 (Rizal Law) at ano ang kahalagahan ng pagtuturo nito sa mga mag-aaral ngayon?", "ph-history"),
    ("Kilusang Propaganda", "Ano ang naging papel ng Kilusang Propaganda at La Solidaridad sa paggising ng damdaming nasyonalismo ng mga Pilipino?", "ph-history"),
    ("Separation of Powers in the PH Government", "Ipaliwanag ang prinsipyo ng Separation of Powers sa pagitan ng Ehekutibo, Lehislatibo, at Hudikatura sa Saligang Batas ng Pilipinas.", "ph-civics"),
    ("1986 EDSA People Power Revolution", "Ano ang mga pangunahing salik na nagbunsod sa 1986 EDSA People Power Revolution at ano ang pamana nito sa bansa?", "ph-history"),
    ("Barayti at Rehistro ng Wika", "Ano ang pinagkaiba ng barayti ng wika (dayalekto, idyolek, sosyolek) sa rehistro ng wika sa asignaturang Komunikasyon?", "linguistics"),
    ("Mga sanhi ng implasyon sa Pilipinas", "Ano ang mga pangunahing sanhi ng pagtaas ng presyo ng bilihin o implasyon sa ekonomiya ng Pilipinas?", "economics"),
    ("Kahalagahan ng Katutubong Wika", "Bakit mahalagang pangalagaan at panatilihing buhay ang mga katutubong wika sa Pilipinas sa kabila ng modernisasyon?", "cultural-studies"),

    # Computer Science & IT
    ("SQL vs NoSQL databases", "What are the core differences between SQL and NoSQL databases, and when should you choose one over the other?", "computer-science"),
    ("asynchronous programming in JavaScript", "How does the event loop and async/await work in JavaScript compared to synchronous execution?", "software-engineering"),
    ("REST vs GraphQL APIs", "Compare RESTful APIs with GraphQL in terms of network overhead, over-fetching, and flexibility.", "web-development"),
    ("SOLID design principles", "Explain the Single Responsibility and Open/Closed principles in object-oriented programming with simple analogies.", "software-engineering"),
    ("processes vs threads", "What is the key difference between an operating system process and a thread regarding memory and execution?", "operating-systems"),
    ("TCP 3-way handshake", "Explain the three steps of the TCP three-way handshake (SYN, SYN-ACK, ACK) and why reliability is guaranteed.", "networking"),
    ("hash table O(1) time complexity", "How does a hash map achieve average O(1) time complexity for lookup, and what happens during collisions?", "data-structures"),

    # College Student Assignments & Essays
    ("social media impact on youth mental health", "Discuss how pervasive social media consumption affects teenage mental health, self-esteem, and sleep habits.", "social-science"),
    ("ethical implications of AI in education", "Should AI tools like ChatGPT be permitted in university classrooms, and what ethical concerns arise regarding academic integrity?", "ethics"),
    ("environmental sustainability and youth action", "Paano makatutulong ang mga kabataan at mag-aaral sa pagtugon sa climate change at solid waste management sa sariling pamayanan?", "environmental-studies"),
    ("role of youth in nation building", "Ano ang papel ng kabataang Pilipino sa pagpapaunlad ng bansa at paghubog ng mabuting pamamahala?", "sociology"),
]


AI_QA_PROMPT_STYLES = [
    # 1. Standard AI Academic / STEM Answer (English)
    {
        "style_id": "ai_qa_stem_en",
        "language": "english",
        "domain": "question",
        "content_type": "answer",
        "template": (
            "You are an AI assistant answering a student's academic question: '{question_prompt}'. "
            "Write the response using standard AI conversational conventions: "
            "- Start with an enthusiastic or direct conversational opener (e.g., 'Certainly! To answer your question...', 'Great question! Let's examine how...') "
            "- Present a clear, structured explanation using 3-4 numbered or bold bullet points with symmetrical explanations "
            "- Include transitional phrases like 'Furthermore,', 'In addition,', 'On the other hand,' "
            "- Conclude with a formulaic summary and sign-off (e.g., 'In conclusion, both play a vital role...', 'I hope this helps clarify the concept! Let me know if you have any follow-up questions.') "
            "Keep length between 140 and 280 words."
        ),
    },

    # 2. Standard AI Academic / History Answer (Taglish)
    {
        "style_id": "ai_qa_history_taglish",
        "language": "taglish",
        "domain": "question",
        "content_type": "answer",
        "template": (
            "You are an AI chatbot answering a Filipino student's homework/study question: '{question_prompt}'. "
            "Write the response in natural AI Taglish: "
            "- Start with an AI opening formula (e.g., 'Ang sagot sa iyong tanong ay nakasalalay sa...', 'Upang masagot ang iyong katanungan, narito ang mga pangunahing dahilan:') "
            "- Provide 3 clearly structured points using bold headers or bullet points (e.g., '1. **Pagpapahalaga sa Kasaysayan**:', '2. **Paggising sa Nasyonalismo**:') "
            "- Use typical Taglish didactic markers ('mahalagang tandaan na', 'sa kabilang banda', 'may malaking kontribusyon') "
            "- End with a polite sign-off (e.g., 'Bilang buod...', 'Sana nakatulong ang paliwanag na ito sa iyong pag-aaral! Sabihin mo lang kung may tanong ka pa.') "
            "Keep length between 130 and 260 words."
        ),
    },

    # 3. Pure Filipino / Tagalog Formal AI Answer
    {
        "style_id": "ai_qa_formal_tagalog",
        "language": "tagalog",
        "domain": "question",
        "content_type": "answer",
        "template": (
            "Sumulat ng isang pormal na sagot ng AI sa tanong na ito: '{question_prompt}'. "
            "Gamitin ang karaniwang estruktura ng ChatGPT/Gemini sa wikang Filipino: "
            "- Pambungad: 'Upang lubos na maunawaan ang konseptong ito, narito ang detalyadong paliwanag hinggil sa...' "
            "- Katawan: 3 mahahalagang punto na may pantay na haba at pormal na pananalita ('Una,', 'Ikalawa,', 'Ikatlo,', 'Bukod dito,') "
            "- Pangwakas: 'Sa kabuuan, ipinapakita nito na... Sana ay nakapagbigay ito ng linaw sa iyong katanungan. Huwag mag-atubiling magtanong kung may karagdagang paglilinaw.' "
            "Haba: 120 hanggang 250 salita."
        ),
    },

    # 4. Technical / Programming Q&A (English)
    {
        "style_id": "ai_qa_tech_en",
        "language": "english",
        "domain": "question",
        "content_type": "answer",
        "template": (
            "Write an AI-generated technical answer to a developer's question: '{question_prompt}'. "
            "Incorporate common LLM technical response hallmarks: "
            "- 'Here is a comprehensive breakdown of the differences between the two:' or 'To understand this concept, let's break it down into core components:' "
            "- Symmetrical comparison points or bullet list with bold labels "
            "- Summary takeaway: 'In short, use X when... and use Y when...' "
            "- Ending: 'Hope this helps! Feel free to ask if you'd like code examples or further details.' "
            "Keep length between 130 and 260 words."
        ),
    },

    # 5. Short Student Homework / Quiz Answer (Taglish)
    {
        "style_id": "ai_qa_student_short_taglish",
        "language": "taglish",
        "domain": "question",
        "content_type": "answer",
        "template": (
            "Write a concise AI response answering this student homework prompt: '{question_prompt}'. "
            "Structure it like an AI helping a student with short homework: "
            "- 1 introductory sentence directly rephrasing the question "
            "- 2-3 bullet points giving the textbook explanation in Taglish "
            "- 1 concluding sentence starting with 'Sa madaling salita,' or 'In summary,' "
            "Length: 80 to 160 words."
        ),
    },

    # 6. Humanized / Anti-Detector Evasive AI Answer (English & Taglish)
    {
        "style_id": "ai_qa_humanized_bypass",
        "language": "english",
        "domain": "question",
        "content_type": "answer",
        "template": (
            "Answer this question: '{question_prompt}'. "
            "However, actively attempt to bypass AI detectors by adopting a conversational student tone: "
            "- Avoid bullet points and numbered lists entirely "
            "- Use conversational pivots: 'Honestly, when you think about it...', 'At the end of the day, it really comes down to...', 'Here is the thing:' "
            "- Write in flowing paragraphs with varied sentence length "
            "- Keep the tone thoughtful and informative, but sound like a smart peer explaining it. "
            "Length: 120 to 220 words."
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


# Authentic human Q&A answers: direct student exam responses, peer explanations, forum replies
AUTHENTIC_HUMAN_QA_SAMPLES = [
    # STEM & Science Human Answers (concise, factual, devoid of AI filler)
    {
        "text": "Short answer: Mitosis produces two genetically identical diploid cells for tissue repair and growth, whereas meiosis produces four genetically unique haploid gametes (sperm or egg) for sexual reproduction.",
        "lang": "english",
        "category": "biology",
    },
    {
        "text": "Basically photosynthesis happens in two stages inside chloroplasts. Light-dependent reactions in the thylakoid take in sunlight and water to make ATP and NADPH while releasing oxygen. Then the Calvin cycle in the stroma uses that chemical energy and CO2 to assemble glucose.",
        "lang": "english",
        "category": "biology",
    },
    {
        "text": "Newton's third law states that for every action force, there is an equal and opposite reaction force. For example, when you jump off a skateboard, your feet push the board backward while the board pushes you forward into the air.",
        "lang": "english",
        "category": "physics",
    },
    {
        "text": "CRISPR-Cas9 acts like molecular scissors. A guide RNA directs the Cas9 enzyme to a specific sequence in the genome, cuts the DNA, and lets scientists delete or insert genes as the cell repairs the cut.",
        "lang": "english",
        "category": "biotech",
    },
    {
        "text": "The law of supply and demand says that if supply exceeds demand, prices fall; if demand exceeds supply, prices rise. Equilibrium is reached where consumer demand matches producer supply at a stable clearing price.",
        "lang": "english",
        "category": "economics",
    },
    {
        "text": "Entropy measures the disorder of an isolated system. The second law says total entropy always increases over time in spontaneous processes, which is why heat flows from hot to cold and broken eggs don't reassemble themselves.",
        "lang": "english",
        "category": "physics",
    },
    {
        "text": "Vaccines expose your immune system to a harmless antigen or mRNA code so B-cells produce antibodies and memory cells without making you sick. If the real pathogen enters later, memory cells neutralize it quickly.",
        "lang": "english",
        "category": "medicine",
    },
    {
        "text": "Earthquakes occur when stress along a locked fault exceeds friction. The rocks slip suddenly, releasing elastic strain energy that radiates outwards as primary (P) and secondary (S) seismic waves.",
        "lang": "english",
        "category": "earth-science",
    },

    # Philippine History, Civics & Social Studies Human Answers (Taglish & Filipino student answers)
    {
        "text": "Ipinasa ang Republic Act 1425 o Rizal Law noong 1956 dahil sa panukala nina Claro M. Recto at Jose P. Laurel para buhayin ang nasyonalismo sa mga kabataan pagkatapos ng World War II sa pamamagitan ng pag-aaral sa Noli at Fili.",
        "lang": "tagalog",
        "category": "ph-history",
    },
    {
        "text": "Ang Kilusang Propaganda ay binuo ng mga ilustrado sa Espanya tulad nina Rizal, Del Pilar, at Lopez Jaena. Layunin nila ang asimilasyon ng Pilipinas bilang probinsya ng Espanya, pantay na karapatan sa batas, at sekularisasyon ng mga parokya.",
        "lang": "tagalog",
        "category": "ph-history",
    },
    {
        "text": "Sa ilalim ng 1987 Saligang Batas, ang separation of powers ay naghahati sa kapangyarihan: Ehekutibo ang nagpapatupad ng batas, Lehislatibo ang gumagawa ng batas, at Hudikatura ang nagpapaliwanag kung naaayon sa konstitusyon ang mga ito.",
        "lang": "tagalog",
        "category": "ph-civics",
    },
    {
        "text": "Ang EDSA People Power noong 1986 ay naging mapayapang rebolusyon na nagpatalsik sa diktadurang Marcos matapos ang dayaan sa snap elections at pag-alsa nina Enrile at Ramos sa tulong ng panawagan ni Cardinal Sin.",
        "lang": "tagalog",
        "category": "ph-history",
    },
    {
        "text": "ang pinagkaiba lang naman, barayti yung mga tono at dialekto depende sa rehiyon like tagalog-batangas vs tagalog-manila, tapos rehistro yung jargon na gamit depende sa profession like medical terms vs legal terms haha",
        "lang": "taglish",
        "category": "linguistics",
    },
    {
        "text": "Ang pangunahing sanhi ng implasyon sa Pilipinas ay ang pagtaas ng presyo ng langis sa world market, kakulangan sa lokal na ani dahil sa bagyo, at pagbaba ng halaga ng piso kontra dolyar na nagpapamahal sa imports.",
        "lang": "tagalog",
        "category": "economics",
    },
    {
        "text": "mahalaga ang katutubong wika kasi dyan nakapaloob yung kultura at katutubong kaalaman ng mga ninuno natin. kapag nawala ang isang wika, nawawala rin yung indigenous worldview ng komunidad.",
        "lang": "taglish",
        "category": "cultural-studies",
    },

    # Computer Science & IT Human Answers (forum style, student banter, straightforward definitions)
    {
        "text": "In simple terms, SQL databases are relational and table-based with strict schemas (like PostgreSQL), best for ACID transactions. NoSQL databases are document or key-value based with dynamic schemas (like MongoDB), better for fast scaling and unstructured data.",
        "lang": "english",
        "category": "computer-science",
    },
    {
        "text": "ganto kasi yan pre, isipin mo yung async/await parang nag-order ka sa fast food. habang niluluto yung burger mo, pwede kang umupo at mag-cellphone, di mo kailangan tumayo lang dun hanggang matapos haha",
        "lang": "taglish",
        "category": "software-engineering",
    },
    {
        "text": "With REST, you request fixed endpoints and often over-fetch fields you don't need. GraphQL lets the client specify the exact JSON schema it wants in a single POST query, avoiding over-fetching and multiple round-trips.",
        "lang": "english",
        "category": "web-development",
    },
    {
        "text": "Single Responsibility says a class should only have one reason to change. Open/Closed says software entities should be open for extension (adding new behavior via inheritance or interfaces) but closed for modification.",
        "lang": "english",
        "category": "software-engineering",
    },
    {
        "text": "A process has its own dedicated memory space allocated by the OS, while threads within that process share the same memory space and file descriptors, making threads lighter but riskier for race conditions.",
        "lang": "english",
        "category": "operating-systems",
    },
    {
        "text": "nakasagot ako sa quiz kanina tungkol dyan haha! TCP 3-way handshake is just SYN (client asks to connect), SYN-ACK (server acknowledges and asks back), tapos ACK (client confirms). parang nagha-high five bago mag-usap.",
        "lang": "taglish",
        "category": "networking",
    },
    {
        "text": "A hash table uses a hash function to turn a key into an array index. On average that takes O(1) time. When two keys produce the same index, collisions are resolved with chaining (linked lists) or open addressing.",
        "lang": "english",
        "category": "data-structures",
    },

    # Student Assignment Discussions & Reflections (Human student voices)
    {
        "text": "sa tingin ko ang pinakamalaking impact ng social media sa mental health ng kabataan ay yung constant comparison. nakikita mo yung highlights ng buhay ng iba kaya pakiramdam mo nahuhuli ka na sa buhay.",
        "lang": "taglish",
        "category": "social-science",
    },
    {
        "text": "honestly AI in school is a double-edged sword. it's super helpful for brainstorming or fixing grammar, but if students just copy-paste whole essays without understanding, they won't learn critical thinking at all.",
        "lang": "english",
        "category": "ethics",
    },
    {
        "text": "pwede tayong magsimula sa simpleng paghihiwalay ng nabubulok at di nabubulok sa bahay at pagdadala ng sariling tumbler imbes na laging bumibili ng bottled water sa canteen.",
        "lang": "taglish",
        "category": "environmental-studies",
    },
    {
        "text": "ang papel ng kabataan sa nation building ay maging mapanuri sa balita, magparehistro para makaboto, at makilahok sa mga community projects hindi lang puro reklamo sa socmed.",
        "lang": "taglish",
        "category": "sociology",
    },
    {
        "text": "Answer for item 3: Simoun returned in El Filibusterismo as a wealthy jeweler seeking violent revenge, unlike the idealistic Crisostomo Ibarra in Noli who believed in education and legal reforms.",
        "lang": "english",
        "category": "literature",
    },
    {
        "text": "Short answer: Price elasticity of demand measures how sensitive quantity demanded is to price changes. If elasticity is greater than 1, demand is elastic; if less than 1, inelastic.",
        "lang": "english",
        "category": "economics",
    },
]


def build_and_generate_qa_dataset(
    base_v8_path: Path,
    output_path: Path,
    target_ai_samples: int = 350,
    seed: int = 42,
) -> None:
    random.seed(seed)
    seen_hashes: set[str] = set()
    rows: list[dict[str, Any]] = []

    def add_row(r: dict[str, Any]) -> bool:
        t = normalize_text(r["text"])
        if len(t) < 15:
            return False
        h = hashlib.sha256(t.casefold().encode("utf-8")).hexdigest()
        if h in seen_hashes:
            return False
        seen_hashes.add(h)
        r["text"] = t
        rows.append(r)
        return True

    # 1. Load baseline v8 dataset
    if base_v8_path.is_file():
        with open(base_v8_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line.strip())
                add_row(item)
        logger.info("Loaded %d baseline rows from %s", len(rows), base_v8_path.name)
    else:
        logger.warning("Base v8 dataset not found at %s", base_v8_path)

    # 2. Add authentic human Q&A samples (negative controls)
    added_human = 0
    for idx, item in enumerate(AUTHENTIC_HUMAN_QA_SAMPLES):
        r = {
            "id": f"human_qa_curated_{idx:03d}",
            "text": item["text"],
            "label": "human",
            "language": item["lang"],
            "domain": "question",
            "content_type": "answer",
            "group_id": f"human_qa_group_{item['category']}_{idx:03d}",
            "source": "human-student-study-notes",
        }
        if add_row(r):
            added_human += 1
    logger.info("Added %d authentic human Q&A negative controls", added_human)

    # 3. Generate AI Q&A samples using Gemini API Pool
    keys = load_gemini_keys()
    logger.info("Loaded %d Gemini API keys for Q&A generation", len(keys))

    task_specs = []
    # Build tasks across styles and topics
    topic_idx = 0
    style_idx = 0
    while len(task_specs) < target_ai_samples:
        topic_name, question_prompt, category = QA_TOPICS[topic_idx % len(QA_TOPICS)]
        style = AI_QA_PROMPT_STYLES[style_idx % len(AI_QA_PROMPT_STYLES)]
        task_specs.append((style, topic_name, question_prompt, category, len(task_specs)))
        topic_idx += 1
        style_idx += 1

    random.shuffle(task_specs)
    logger.info("Queued %d Gemini AI Q&A generation tasks", len(task_specs))

    successful_gen = 0

    def worker(task_idx: int, spec: tuple[dict[str, Any], str, str, str, int]) -> list[dict[str, Any]]:
        style, topic_name, question_prompt, category, iter_idx = spec
        key = keys[task_idx % len(keys)]
        prompt = style["template"].format(question_prompt=question_prompt)
        out = call_gemini(prompt, key=key)
        if not out:
            return []

        clean_text = normalize_text(out.strip('"\n\r '))
        if len(clean_text) < 30:
            return []

        return [{
            "id": f"ai_qa_gen_{style['style_id']}_{task_idx}",
            "text": clean_text,
            "label": "ai",
            "language": style["language"],
            "domain": "question",
            "content_type": style["content_type"],
            "group_id": f"qa_topic_{topic_name.replace(' ', '_')}_{iter_idx}",
            "source": f"gemini-qa-{style['style_id']}",
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
                            logger.info("Generated %d / %d AI Q&A samples...", successful_gen, target_ai_samples)
            except Exception as e:
                logger.debug("Task failed: %s", e)

    logger.info("Successfully generated and added %d new AI Q&A samples", successful_gen)

    # 4. Group-safe split assignment
    # Group samples by group_id
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
        default=Path(r"C:\Users\dever\Downloads\verifai_v8_social_maximized.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(r"C:\Users\dever\Downloads\verifai_v9_qa_maximized.jsonl"),
    )
    parser.add_argument("--target-ai", type=int, default=320)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # Fallback to v7 if v8 does not exist
    base_path = args.base_dataset
    if not base_path.is_file():
        v7_path = Path(r"C:\Users\dever\Downloads\verifai_v7_maximized.jsonl")
        if v7_path.is_file():
            logger.info("v8 dataset not found, falling back to %s", v7_path)
            base_path = v7_path

    build_and_generate_qa_dataset(
        base_v8_path=base_path,
        output_path=args.output,
        target_ai_samples=args.target_ai,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
