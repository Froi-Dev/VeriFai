# How VeriFai’s Fake-News Detector Works

VeriFai is an evidence-based news verification system. It does not decide whether an article is fake from writing style alone. Instead, it extracts the claim, looks for relevant evidence, compares the claim with that evidence, and returns a verdict with an explanation and confidence level.

## The high-level flow

```text
User submits text, a news URL, or an image
              |
              v
Normalize and extract the main claim
              |
              v
Find relevant news, fact-checks, and official sources
              |
              v
Check dates, event types, entities, numbers, and contradictions
              |
              v
Combine evidence using rules and the evidence adjudicator
              |
              v
Return verdict, confidence, explanation, and source analysis
```

## 1. Input handling

The API accepts a text claim or news content. An image can also be submitted. Image verification first prepares the image and uses Gemini Vision to extract readable text; the extracted text is then sent through the same news-verification pipeline. This means the image scanner is an OCR front end, not a separate fact-checking engine.

The service validates supported image formats, upload size, and processing limits. Requests are rate-limited, and authenticated scans can be saved to the user’s scan history.

## 2. Claim and text analysis

The verifier cleans and normalizes the submitted content, then identifies the important factual claim. It looks for signals such as:

- the people, organizations, places, and dates involved;
- the event being claimed, such as a death, arrest, election result, trial, disaster, or policy decision;
- numbers and other specific factual details;
- relative dates such as “today” or “last week”;
- negation and debunking language, including “not true,” “denied,” and “no evidence.”

This step also helps distinguish a claim about something that happened from a proposal, prediction, opinion, satire, or report about an ongoing event.

## 3. Evidence collection

VeriFai searches for coverage related to the claim and gathers evidence from news publishers, official government sources, and fact-checking organizations. Sources are normalized and deduplicated so that URL tracking parameters and repeated copies of the same story do not distort the result.

Each evidence item can include its publisher, source type, publication date, reliability tier, and relationship to the claim. Evidence may:

- support the claim;
- contradict the claim;
- debunk the claim;
- provide related context; or
- be irrelevant to the claim.

Source quality matters. Primary official sources and independent, high-reliability reporting receive more weight than unknown or unverified pages. Repetition is not treated as independent confirmation when many pages simply copy one another.

## 4. Deterministic checks

Before the final decision, the verifier applies explicit checks for common misinformation patterns. Examples include:

- a hospitalization being changed into a death claim;
- an investigation or questioning being described as an arrest;
- an accusation or trial being described as a conviction;
- a proposal or draft bill being described as an approved law;
- a forecast being described as an event that already happened;
- an official denial or credible fact-check directly contradicting the claim.

The verifier also compares event types, dates, entities, and numerical details. A similar number or loosely related article is not considered an exact match.

## 5. Evidence adjudication

When enough evidence is available, VeriFai’s evidence adjudicator reviews the claim and the collected sources together. It is instructed to weigh source authority, independence, timing, directness, and contradictions. It must explain which evidence is decisive and identify unresolved details instead of filling gaps with guesses.

Possible verdicts include:

- **TRUE** — the available evidence supports the claim;
- **FALSE** — reliable evidence directly contradicts the claim;
- **MISLEADING** — the claim is based on something real but changes the meaning, timing, status, or context;
- **UNVERIFIED** — there is not enough reliable evidence to confirm or refute it.

Satire and opinion are handled separately so they are not automatically treated as factual falsehoods.

## 6. Confidence and response

The response includes the verdict, a confidence score, a short explanation, and evidence analysis. Confidence increases when the evidence is direct, authoritative, current, and independently corroborated. It decreases when sources conflict, the claim is ambiguous, or important details remain unresolved.

Confidence is not the same as truth. A high-confidence result means the collected evidence strongly supports the system’s conclusion; it does not mean the system can never be wrong.

## 7. Auditability and limitations

Verification decisions are recorded in structured audit logs, including selected and rejected sources, the verdict, confidence, and whether rules or the adjudicator produced the final decision. Authenticated results can also be persisted as scan records.

The detector is a decision-support tool, not an absolute authority. Breaking news may not yet have reliable coverage, search results may be incomplete, and an accurate article can still be misleading if its wording or context is changed. Users should open the cited sources and check the original context before sharing consequential information.

## In one sentence

VeriFai works by turning a submitted post, article, or image into a factual claim, comparing that claim against weighted and cross-checked evidence, applying explicit contradiction checks, and returning a transparent verdict with confidence and supporting sources.
