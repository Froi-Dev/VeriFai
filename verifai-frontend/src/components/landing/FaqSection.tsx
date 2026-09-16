import { useState } from "react";
import { ChevronDown, HelpCircle } from "lucide-react";

type FaqItem = {
  question: string;
  answer: string;
};

const FAQ_ITEMS: FaqItem[] = [
  {
    question: "How does Verif.Ai accurately analyze Taglish and casual Filipino text?",
    answer:
      "Most online detectors are only trained on formal English from abroad, so they often mistake normal Taglish slang or campus conversations for AI-generated text. Verif.Ai was trained on real Filipino student essays, local news, and casual Taglish alongside AI examples, helping it distinguish genuine local writing from repetitive AI formulas.",
  },
  {
    question: "Does Verif.Ai give a definitive '100% fake' or '100% real' verdict?",
    answer:
      "No, and by design. No detector can be 100% infallible. Instead of an abrupt guess, Verif.Ai gives you a calibrated likelihood percentage, highlighted writing clues, and links to verified news coverage. Borderline cases are marked as 'Review Recommended' so you can make an informed judgment.",
  },
  {
    question: "Is my submitted text or uploaded screenshot saved or used to train models?",
    answer:
      "No. Your submissions are analyzed securely in real-time. Your text, documents, and screenshots are never stored permanently, never shared publicly, and never used to train public AI models.",
  },
  {
    question: "How does fact-checking work with screenshots and images?",
    answer:
      "When you upload an image of a social media post, meme, or announcement, Verif.Ai reads the text inside the screenshot and searches accredited Philippine news publishers and fact-checking records to see if the claim has been confirmed or debunked.",
  },
  {
    question: "Can schools, student publications, and teams use Verif.Ai?",
    answer:
      "Yes. Verif.Ai provides both an intuitive web dashboard for in-depth checks and a fast browser extension for quick everyday verification while browsing.",
  },
];

export function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const toggleItem = (index: number) => {
    setOpenIndex((current) => (current === index ? null : index));
  };

  return (
    <section id="faq" className="section faq-section">
      <div className="container">
        <div className="center-heading">
          <p className="kicker">FREQUENTLY ASKED QUESTIONS</p>
          <h2>Clear answers to common questions.</h2>
          <p>
            Everything you need to know about our Taglish analysis, fact-checking, and privacy protections.
          </p>
        </div>

        <div className="faq-accordion-wrap">
          {FAQ_ITEMS.map((item, index) => {
            const isOpen = openIndex === index;
            return (
              <div
                key={item.question}
                className={`faq-accordion-item ${isOpen ? "open" : ""}`}
              >
                <button
                  type="button"
                  className="faq-question-trigger"
                  onClick={() => toggleItem(index)}
                  aria-expanded={isOpen}
                  aria-controls={`faq-answer-${index}`}
                  id={`faq-question-${index}`}
                >
                  <span className="faq-question-text">
                    <HelpCircle size={17} className="faq-question-icon" />
                    {item.question}
                  </span>
                  <ChevronDown
                    size={18}
                    className={`faq-chevron-icon ${isOpen ? "rotate" : ""}`}
                  />
                </button>

                <div
                  id={`faq-answer-${index}`}
                  role="region"
                  aria-labelledby={`faq-question-${index}`}
                  className={`faq-answer-collapse ${isOpen ? "show" : ""}`}
                  hidden={!isOpen}
                >
                  <div className="faq-answer-inner">
                    <p>{item.answer}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
