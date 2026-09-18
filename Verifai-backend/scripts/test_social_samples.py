import sys
from pathlib import Path
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.ContentDetector.detector import text_detector as detector

samples = [
    (
        "AI Caption 1 (English)",
        "Stop scrolling if you want to ace your college exams! Here are 3 habits you MUST build today:\n\n1. Pomodoro technique\n2. Active recall with flashcards\n3. Sleep at least 7 hours\n\nSave this post for finals week and drop a comment below with your favorite study hack! #StudyTips #CollegeHacks",
    ),
    (
        "AI Caption 2 (Taglish)",
        "Gusto mo bang maging productive this semester? Narito ang 3 tips na makakatulong sa iyo:\n\n- Plan your day the night before\n- Iwasan ang doomscrolling sa umaga\n- Mag-take ng regular breaks\n\nI-save mo ito para hindi mo makalimutan! I-tag mo na rin ang tropa mong laging puyat.",
    ),
    (
        "AI Bot Comment 1 (English)",
        "Such an insightful and thought-provoking post! I completely agree with your third point about consistency being key. Looking forward to reading more of your content!",
    ),
    (
        "AI Bot Comment 2 (Taglish)",
        "Napakagandang punto nito! Tunay ngang napakahalaga ng disiplina at tamang mindset para sa ating mga pangarap. Maraming salamat sa pagbabahagi ng inspirasyong ito!",
    ),
    (
        "Human Casual Comment/Rant",
        "Grabe kanina sa jeep ang init tapos na-stuck pa kami sa trapik sa may cubao gutom na gutom na ko pota haha",
    ),
    (
        "Human Casual Comment 2",
        "haha relate sobra lodi sana all nakapasa sa exam congrats!",
    ),
    (
        "Human Social Post",
        "skl guys grabe yung prof namin kanina biglang nagpa surprise quiz eh wala pa nga kaming natapos na module haha iyak na lang talaga bukas sa remedial",
    ),
    (
        "AI Advice Post",
        "Most college students believe success is about cramming overnight. In reality, real mastery requires incremental progress every single day. Here are 4 principles every student should remember to stay ahead.",
    ),
]

print(f"{'Sample Name':30s} | {'Prediction':22s} | {'AI Prob':8s} | {'Conf':6s} | Signals")
print("-" * 90)
for name, text in samples:
    res = detector.analyze(text)
    signals = res.signals
    print(f"{name:30s} | {res.classification:22s} | {res.ai_probability:.4f}   | {res.confidence:.2f}   | {signals}")
