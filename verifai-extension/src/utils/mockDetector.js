/**
 * Verif.AI — Mock AI Detector
 *
 * This module simulates an AI content detection API call.
 * It returns randomized results after a 1.5-second delay to mimic
 * real network latency.
 *
 * ┌──────────────────────────────────────────────────────────┐
 * │  TO SWAP FOR REAL API:                                   │
 * │                                                          │
 * │  Replace the function body with:                         │
 * │                                                          │
 * │    export async function analyzeImage(imageDataUrl) {    │
 * │      const response = await fetch(API_URL, {             │
 * │        method: 'POST',                                   │
 * │        headers: { 'Content-Type': 'application/json' },  │
 * │        body: JSON.stringify({ image: imageDataUrl }),     │
 * │      });                                                 │
 * │      if (!response.ok) throw new Error('API error');     │
 * │      return await response.json();                       │
 * │    }                                                     │
 * │                                                          │
 * │  The return shape should match:                          │
 * │  {                                                       │
 * │    isAIGenerated: boolean,                               │
 * │    confidence: string (e.g. "87.3"),                     │
 * │    label: "AI-Generated" | "Human-Made",                 │
 * │    details: {                                            │
 * │      model: string,                                      │
 * │      analysisTime: string,                               │
 * │      timestamp: string (ISO)                             │
 * │    }                                                     │
 * │  }                                                       │
 * └──────────────────────────────────────────────────────────┘
 */

/**
 * Analyze an image for AI-generated content.
 * @param {string} imageDataUrl - Base64 data URL of the image to analyze
 * @returns {Promise<Object>} Detection results
 */
export async function analyzeImage(imageDataUrl) {
  // Simulate network delay (1.5 seconds)
  await new Promise((resolve) => setTimeout(resolve, 1500));

  // Validate input (basic sanity check)
  if (!imageDataUrl || !imageDataUrl.startsWith("data:image")) {
    throw new Error("Invalid image data provided");
  }

  // Generate randomized mock results
  const isAI = Math.random() > 0.5;

  return {
    isAIGenerated: isAI,
    confidence: (Math.random() * 40 + 60).toFixed(1), // 60–100%
    label: isAI ? "AI-Generated" : "Human-Made",
    details: {
      model: "Mock Detector v1.0",
      analysisTime: "1.5s",
      timestamp: new Date().toISOString(),
    },
  };
}
