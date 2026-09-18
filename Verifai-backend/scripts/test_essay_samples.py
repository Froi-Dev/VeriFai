import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.ContentDetector.detector import text_detector as detector

essay_samples = [
    (
        "AI Personal Statement (English)",
        "From a young age, I have always been fascinated by the boundless potential of technology to solve human problems. "
        "Growing up in a rapidly developing community, I witnessed firsthand how digital tools could bridge socio-economic divides. "
        "However, my path was not without adversity. When my family faced a sudden financial crisis during my sophomore year, "
        "it was not merely a challenge; it was a defining crucible that tested my character. "
        "This transformative experience taught me the profound value of resilience and empathy. "
        "Looking back on this journey, I realize that every obstacle was a catalyst for personal growth. "
        "As I step onto your campus, I am eager to contribute to your vibrant community and leverage software engineering to empower underserved populations.",
    ),
    (
        "AI About Me Essay (English)",
        "I am a passionate, driven individual who thrives at the intersection of technology and creative design. "
        "Ever since I wrote my first line of Python code, I have been captivated by the art of turning abstract ideas into tangible solutions. "
        "Beyond my academic pursuits, I find solace in landscape photography and digital illustration, pursuits that constantly challenge me "
        "to view the world through diverse perspectives. Whether I am collaborating on open-source projects or mentoring junior developers, "
        "my ultimate mission is to build software that creates lasting social impact.",
    ),
    (
        "AI Personal Essay (Taglish)",
        "Mula pagkabata, lagi kong naiisip kung ano nga ba ang tunay na kahulugan ng tagumpay. "
        "Sa aking paglaki, naging malaking bahagi ng aking buhay ang pagtulong sa aming munting negosyo sa Cavite. "
        "Hindi naging madali ang pagsasabay ng pag-aaral at pagtulong sa pamilya, ngunit natutunan kong mag-persevere sa kabila ng pagod. "
        "Sa pagbabalik-tanaw, napagtanto ko na ang bawat pagsubok ay nagsilbing aral. "
        "Ang karanasang ito ang naghubog sa akin upang maging isang mapagkumbaba at determinadong mag-aaral na handang harapin ang kinabukasan.",
    ),
    (
        "AI Formal Filipino Essay",
        "Sa modernong panahon, isa sa mga pinakamahalagang usapin na kinakaharap ng ating lipunan ay ang pangangalaga sa ating pambansang pagkakakilanlan. "
        "Hindi maikakaila na may malaking impluwensya ang teknolohiya at globalisasyon sa kaisipan ng kabataang Pilipino. "
        "Una sa lahat, mahalagang kilalanin na ang ating kultura ang pundasyon ng ating pagka-Pilipino. "
        "Bukod dito, may mahalagang papel na ginagampanan ang edukasyon sa pagpapanatili ng ating mga katutubong tradisyon. "
        "Bilang pagtatapos, nararapat lamang na ating pagnilayan ang ating mga responsibilidad upang manatiling buhay ang diwa ng ating lahi.",
    ),
    (
        "Human Personal Essay 1 (English)",
        "I never planned on falling in love with computer hardware. It actually started out of desperation when my older brother's "
        "hand-me-down laptop gave up on me the night before my tenth-grade science investigatory project was due. My hands were shaking "
        "as I unscrewed the backplate with a butter knife because we didn't own a precision screwdriver set. When I saw the caked dust "
        "clogging the microscopic copper heat pipes, something clicked. After two hours of frantic YouTube tutorials and blowing away debris "
        "with a bicycle tire pump, the blue screen gave way to the desktop. That adrenaline rush wasn't just relief; it was the realization "
        "that complex machines aren't magic—they're puzzles waiting to be solved.",
    ),
    (
        "Human Personal Essay 2 (English)",
        "Growing up, our kitchen was never quiet. My lola would wake up at four in the morning to prepare sinangag and dried fish, and the "
        "sharp aroma of burnt garlic would seep through the wooden floorboards into my tiny bedroom. She never finished elementary school, "
        "yet she could balance the family budget on the margins of old electricity bills with uncanny precision. When money was tight, "
        "lola would smile, hand me a freshly peeled mango, and whisper, 'Aral muna, apo. Ang karunungan, walang makakanakaw niyan sayo.' "
        "Those words became my shield whenever I felt out of place among private school peers during science quizzes.",
    ),
    (
        "Human About Me 1 (Taglish)",
        "Hi everyone, I'm Julian. To be completely honest, if you asked me three years ago what I'd be studying, software development "
        "would have been the absolute last thing on my list. I spent most of high school convinced I was going to be a music producer, "
        "spending way too many late nights tinkering with pirated DAWs and wondering why my basslines sounded like mud. Coding only entered "
        "the picture when I got frustrated that existing sound libraries didn't have the tag filtering I wanted. When I'm not "
        "staring at VS Code, you can usually find me hunting for cheap iced coffee or re-watching Studio Ghibli films.",
    ),
    (
        "Human About Me 2 (Taglish)",
        "Ako nga pala si Bea, 19 years old, taga-Pasig. Simpleng tao lang ako na mahilig sa pusa at instant ramen tuwing madaling araw. "
        "Pumasok ako sa kursong Education kasi idol ko talaga yung high school English teacher ko na hindi sumuko sa akin kahit muntik na akong "
        "bumagsak sa remedial reading nung first year. Medyo mahiyain ako sa simula pero madaldal kapag naging close na tayo, lalo na kapag anime haha.",
    ),
]

if __name__ == "__main__":
    print(f"{'Sample Name':36s} | {'Prediction':22s} | {'AI Prob':8s} | {'Conf':6s} | Signals")
    print("-" * 110)
    for name, text in essay_samples:
        res = detector.analyze(text)
        signals = res.signals
        print(f"{name:36s} | {res.classification:22s} | {res.ai_probability:.4f}   | {res.confidence:.2f}   | {signals}")
