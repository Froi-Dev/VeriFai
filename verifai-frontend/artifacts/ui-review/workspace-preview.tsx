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

api.defaults.adapter = async (config) => ({
  data: { items: [], stats: { total: 0, textCount: 0, mediaCount: 0, newsCount: 0, weeklyTotal: 0, weeklyScans: [] } },
  status: 200,
  statusText: "OK",
  headers: {},
  config,
});
const paths = { text: "/dashboard/text-analyzer", media: "/dashboard/media-analyzer", news: "/dashboard/fake-news-analyzer" };
const view = new URLSearchParams(location.search).get("view") || "";
createRoot(document.getElementById("root")!).render(<MemoryRouter initialEntries={[paths[view] || "/dashboard"]}><DashboardPage /></MemoryRouter>);
