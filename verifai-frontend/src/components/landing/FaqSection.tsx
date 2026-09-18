import { useState } from "react";
import { ChevronDown, HelpCircle } from "lucide-react";

type FaqItem = {
  question: string;
  answer: string;
};

const FAQ_ITEMS: FaqItem[] = [
  {
    question: "Can I check Filipino and Taglish writing?",
    answer:
      "Yes. Text Analyzer accepts English, Filipino, and Taglish passages and checks for patterns associated with AI writing. Read the assessment alongside the original text, especially for short passages or mixed-language writing.",
  },
  {
    question: "Is an assessment proof that content is real or fake?",
    answer:
      "No. Writing and image assessments identify patterns; they do not establish authorship or provenance. News Checker compares claims with available reporting. Review the explanation, limitations, and linked sources before drawing a conclusion.",
  },
  {
    question: "Where can I find my previous checks?",
    answer:
      "Completed analyses appear in your workspace’s Scan history. You can review scan summaries, delete individual entries, or clear your history using the controls on that page.",
  },
  {
    question: "How does fact-checking work with screenshots and images?",
    answer:
      "When you upload an image of a social media post, meme, or announcement, Verif.AI reads the text inside the screenshot and searches accredited Philippine news publishers and fact-checking records to see if the claim has been confirmed or debunked.",
  },
  {
    question: "Can schools, student publications, and teams use Verif.AI?",
    answer:
      "The web workspace is available for checking writing, news, and images. A browser extension is planned, but a downloadable package is not yet available.",
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
          <p className="kicker">Common questions</p>
          <h2>Clear answers to common questions.</h2>
          <p>
            What each tool can tell you, and how to use the results.
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
