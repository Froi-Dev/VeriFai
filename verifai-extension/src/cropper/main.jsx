import React from "react";
import ReactDOM from "react-dom/client";
import "@fontsource-variable/manrope";
import "@fontsource-variable/source-sans-3";
import Cropper from "./Cropper.jsx";
import "./cropper.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Cropper />
  </React.StrictMode>
);
