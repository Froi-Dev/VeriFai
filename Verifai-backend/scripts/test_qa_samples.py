import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.ContentDetector.detector import text_detector as detector

qa_samples = [
    (
        "AI STEM Answer (English)",
        "Great question! Let's examine the core differences between mitosis and meiosis.\n\n"
        "Here are the key differences between the two cell division processes:\n"
        "1. **Purpose**: Mitosis facilitates tissue growth and cellular repair throughout the organism, whereas meiosis specifically produces gametes for sexual reproduction.\n"
        "2. **Daughter Cells**: Mitosis yields two genetically identical diploid daughter cells. In contrast, meiosis results in four genetically diverse haploid daughter cells.\n"
        "3. **Genetic Variation**: Crossing over occurs exclusively in meiosis, introducing genetic diversity.\n\n"
        "In conclusion, while mitosis preserves genetic continuity, meiosis drives biological evolution. "
        "I hope this helps clarify the concept! Let me know if you have any follow-up questions.",
    ),
    (
        "AI History Q&A (Taglish)",
        "Ang sagot sa iyong katanungan ay nakasalalay sa tatlong mahahalagang layunin ng batas na ito.\n\n"
        "Narito ang detalyadong paliwanag hinggil sa Republic Act 1425 o Rizal Law:\n"
        "1. **Paggising sa Nasyonalismo**: Mahalagang tandaan na ipinasa ito upang muling buhayin ang diwa ng pagkamakabayan sa mga kabataan pagkatapos ng digmaan.\n"
        "2. **Pagsusuri sa Kasaysayan**: Sa pamamagitan ng pagbabasa sa Noli Me Tangere at El Filibusterismo, nauunawaan ng mga mag-aaral ang mga sakripisyo ng ating mga bayani.\n"
        "3. **Paghubog ng Karakter**: Nagsisilbi itong inspirasyon upang maging responsableng mamamayan.\n\n"
        "Sana nakatulong ang paliwanag na ito sa iyong takdang-aralin! Sabihin mo lang kung may tanong ka pa.",
    ),
    (
        "AI Technical Q&A (English)",
        "To answer your question, the primary distinction between SQL and NoSQL databases revolves around schema rigidity and scalability.\n\n"
        "Here is a comprehensive breakdown of the differences between the two architectures:\n"
        "- **Data Structure**: SQL databases rely on relational tables with predefined schemas, making them ideal for complex queries and ACID transactions.\n"
        "- **Scalability**: NoSQL databases utilize document, key-value, or graph models that scale horizontally across distributed clusters.\n"
        "- **Use Cases**: Use SQL for banking and structured systems, and NoSQL for high-velocity real-time analytics.\n\n"
        "Hope this answers your question! Feel free to ask if you would like code examples or architectural recommendations.",
    ),
    (
        "AI Filipino Answer (Tagalog)",
        "Upang masagot ang iyong katanungan, narito ang mga pangunahing dahilan kung bakit mahalaga ang wika sa lipunan.\n\n"
        "Una, ang wika ang pangunahing instrumento ng komunikasyon at pagpapalitan ng ideya sa pagitan ng mga mamamayan. "
        "Ikalawa, nagsisilbi itong salamin ng kultura at pagkakakilanlan ng isang bansa. "
        "Ikatlo, may mahalagang papel na ginagampanan ang wika sa pagpapanatili ng kaayusan at pagpapatupad ng batas.\n\n"
        "Sa kabuuan, hindi maikakaila na ang wika ay pundasyon ng pambansang pagkakaisa. "
        "Sana ay nakatulong ang paliwanag na ito sa iyong pag-aaral! Huwag mag-atubiling magtanong kung may karagdagang paglilinaw.",
    ),
    (
        "Human Student Homework (English)",
        "Short answer: Mitosis produces two genetically identical diploid cells for tissue repair and growth, whereas meiosis produces four genetically unique haploid gametes (sperm or egg) for sexual reproduction.",
    ),
    (
        "Human Student Explanation (Taglish)",
        "ganto kasi yan pre, isipin mo yung async/await parang nag-order ka sa fast food. habang niluluto yung burger mo, pwede kang umupo at mag-cellphone, di mo kailangan tumayo lang dun hanggang matapos haha",
    ),
    (
        "Human Student Exam Answer (Filipino)",
        "Sa ilalim ng 1987 Saligang Batas, ang separation of powers ay naghahati sa kapangyarihan: Ehekutibo ang nagpapatupad ng batas, Lehislatibo ang gumagawa ng batas, at Hudikatura ang nagpapaliwanag kung naaayon sa konstitusyon ang mga ito.",
    ),
    (
        "Human Student Peer Banter (Taglish)",
        "nakasagot ako sa quiz kanina tungkol dyan haha! TCP 3-way handshake is just SYN (client asks to connect), SYN-ACK (server acknowledges and asks back), tapos ACK (client confirms). parang nagha-high five bago mag-usap.",
    ),
]

if __name__ == "__main__":
    print(f"{'Sample Name':36s} | {'Prediction':22s} | {'AI Prob':8s} | {'Conf':6s} | Signals")
    print("-" * 110)
    for name, text in qa_samples:
        res = detector.analyze(text)
        signals = res.signals
        print(f"{name:36s} | {res.classification:22s} | {res.ai_probability:.4f}   | {res.confidence:.2f}   | {signals}")
