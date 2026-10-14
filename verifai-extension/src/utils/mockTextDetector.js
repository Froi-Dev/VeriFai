/**
 * Verif.AI — Mock Text Detector
 *
 * Simulates an AI text detection API call. Returns randomized results
 * after a 1.2-second delay to mimic real network latency.
 *
 * ┌──────────────────────────────────────────────────────────────┐
 * │  TO SWAP FOR REAL API:                                       │
 * │                                                              │
 * │  Replace the function body with:                             │
 * │                                                              │
 * │    export async function analyzeText(text) {                 │
 * │      const response = await fetch(API_URL, {                 │
 * │        method: 'POST',                                       │
 * │        headers: { 'Content-Type': 'application/json' },      │
 * │        body: JSON.stringify({ text }),                        │
 * │      });                                                     │
 * │      if (!response.ok) throw new Error('API error');         │
 * │      return await response.json();                           │
 * │    }                                                         │
 * │                                                              │
 * │  The return shape should match:                              │
 * │  {                                                           │
 * │    isAIGenerated: boolean,                                   │
 * │    confidence: string (e.g. "87.3"),                         │
 * │    label: "Likely AI-Generated" | "Likely Human-Written",    │
 * │    details: {                                                │
 * │      wordCount: number,                                      │
 * │      characterCount: number,                                 │
 * │      model: string,                                          │
 * │      analysisTime: string,                                   │
 * │      timestamp: string (ISO),                                │
 * │      perplexityScore: string,                                │
 * │      burstinessScore: string                                 │
 * │    }                                                         │
 * │  }                                                           │
 * └──────────────────────────────────────────────────────────────┘
 */

/**
 * Analyze text for AI-generated content.
 * @param {string} text - The text to analyze
 * @returns {Promise<Object>} Detection results
 */
export async function analyzeText(text) {
  // Simulate network delay (1.2 seconds)
  await new Promise((resolve) => setTimeout(resolve, 1200));

  // Validate input
  if (!text || typeof text !== "string" || text.trim().length === 0) {
    throw new Error("Invalid or empty text provided");
  }

  const wordCount = text.split(/\s+/).filter(Boolean).length;
  const aiScore = Math.random() * 100;

  return {
    isAIGenerated: aiScore > 50,
    confidence: aiScore.toFixed(1),
    label: aiScore > 50 ? "Likely AI-Generated" : "Likely Human-Written",
    details: {
      wordCount: wordCount,
      characterCount: text.length,
      model: "Mock Text Detector v1.0",
      analysisTime: "1.2s",
      timestamp: new Date().toISOString(),
      perplexityScore: (Math.random() * 50 + 20).toFixed(2),
      burstinessScore: (Math.random() * 100).toFixed(2),
    },
  };
}
