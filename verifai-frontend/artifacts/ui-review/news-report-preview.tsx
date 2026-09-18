// Temporary visual-review fixture. Never included in the application bundle.
import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { DashboardPage } from "/src/pages/DashboardPage";
import { api } from "/src/lib/api";
import "@fontsource-variable/manrope";
import "@fontsource-variable/source-sans-3";
import "/src/index.css";
import "/src/redesign.css";
import "/src/philippine.css";


// Synthetic data for visual verification only; never imported by the application.
const source = { title: "TEST FIXTURE: Ulat para sa pagsusuri ng disenyo", publisher: "Test source", url: "https://example.com/report", image_url: `${location.origin}/favicon.svg`, relationship: "SUPPORTS", source_tier: 1, reliability: 0.95, explanation: "Halimbawang paliwanag para sa layout lamang." };
const verification = { status: "SUCCESS", verdict: "VERIFIED", confidence: 92, explanation: "TEST FIXTURE — Hindi ito aktuwal na pagsusuri ng balita.", context_warnings: ["This input looks like a short headline. For more accurate verification, try including more text from the article.", "TEST: Mahalagang konteksto na dapat manatiling nakikita."], evidence: { supporting: [source, {...source, url: "https://example.com/missing", image_url: `${location.origin}/missing-test-image.png`, title: "TEST: Sirang larawan — dapat may malinaw na fallback"}], contradicting: [], related: [], debunks: [] }, closest_real_story: { ...source, found: true }, search: {} };
api.defaults.adapter = async (config) => {
  let data: unknown = { items: [] };
  if (config.url?.includes("/news/verify")) {
    await new Promise(resolve => setTimeout(resolve, 2500));
    data = config.url.endsWith("verify-image")
      ? { classification: "REAL", confidence: 92, overall_confidence: "HIGH", claims: [], verification }
      : verification;
  }
  return { data, status: 200, statusText: "OK", headers: {}, config };
};
createRoot(document.getElementById("root")!).render(<MemoryRouter initialEntries={["/dashboard/fake-news-analyzer"]}><DashboardPage /></MemoryRouter>);
