import { useState, useEffect, useRef, useCallback } from "react";
import { Check, Crop, FileImage, Newspaper, ScanSearch, X } from "lucide-react";
import { getCropMode } from "../utils/storage.js";

/**
 * VeriFai — Screen Region Cropper Component
 *
 * Captures the screenshot, allows region selection with canvas dragging,
 * and sends cropped data to background service worker for live analysis.
 */
export default function Cropper() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const canvasRef = useRef(null);
  const imageRef = useRef(null);

  const [screenshot, setScreenshot] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selection, setSelection] = useState(null); // { startX, startY, endX, endY }
  const [dragStart, setDragStart] = useState(null);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [imageScale, setImageScale] = useState(1);
  const [analysisMode, setAnalysisMode] = useState("media"); // "media" | "news_image"

  // Load screenshot & crop mode from storage on mount
  useEffect(() => {
    async function loadData() {
      try {
        const storedMode = await getCropMode();
        if (storedMode) setAnalysisMode(storedMode);

        const data = await chrome.storage.local.get([
          "verifai_screenshot",
          "factguard_screenshot",
        ]);
        const dataUrl = data.verifai_screenshot || data.factguard_screenshot;

        if (!dataUrl) {
          setError("No screenshot found. Close this window and capture a tab again.");
          return;
        }

        const img = new Image();
        img.onload = () => {
          imageRef.current = img;

          const maxWidth = window.innerWidth;
          const maxHeight = window.innerHeight - 110; // Leave room for top toolbar
          const scale = Math.min(maxWidth / img.naturalWidth, maxHeight / img.naturalHeight, 1);

          const displayWidth = Math.floor(img.naturalWidth * scale);
          const displayHeight = Math.floor(img.naturalHeight * scale);

          setCanvasSize({ width: displayWidth, height: displayHeight });
          setImageScale(scale);
          setScreenshot(dataUrl);
        };
        img.onerror = () => setError("The screenshot could not be loaded. Please capture again.");
        img.src = dataUrl;
      } catch (err) {
        setError(err.message || "Could not load screenshot.");
      }
    }

    loadData();
  }, []);

  // Draw the canvas
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img) return;

    const ctx = canvas.getContext("2d");

    // Draw screenshot
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    // If there is a selection, draw dark backdrop and cutout
    if (selection) {
      const { startX, startY, endX, endY } = selection;
      const x = Math.min(startX, endX);
      const y = Math.min(startY, endY);
      const w = Math.abs(endX - startX);
      const h = Math.abs(endY - startY);

      // Semi-transparent backdrop
      ctx.fillStyle = "rgba(9, 9, 9, 0.62)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Cutout selected hole
      ctx.save();
      ctx.beginPath();
      ctx.rect(x, y, w, h);
      ctx.clip();
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      ctx.restore();

      // VeriFai crimson highlight border
      ctx.strokeStyle = "#d7263d";
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);

      // Inner white dashed guide
      ctx.strokeStyle = "rgba(255, 255, 255, 0.85)";
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 5]);
      ctx.strokeRect(x, y, w, h);
      ctx.setLineDash([]);

      // Corner handles
      const handleSize = 7;
      ctx.fillStyle = "#d7263d";
      const corners = [
        [x, y],
        [x + w, y],
        [x, y + h],
        [x + w, y + h],
      ];
      corners.forEach(([cx, cy]) => {
        ctx.fillRect(cx - handleSize / 2, cy - handleSize / 2, handleSize, handleSize);
      });

      // Dimensions badge
      if (w > 50 && h > 24) {
        const origW = Math.round(w / imageScale);
        const origH = Math.round(h / imageScale);
        const label = `${origW} × ${origH} px`;
        ctx.font = '600 11px "Source Sans 3 Variable", sans-serif';
        ctx.fillStyle = "rgba(9, 9, 9, 0.88)";
        const textWidth = ctx.measureText(label).width;
        ctx.fillRect(x + w / 2 - textWidth / 2 - 8, y + h / 2 - 10, textWidth + 16, 20);
        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, x + w / 2, y + h / 2);
      }
    }
  }, [selection, imageScale]);

  useEffect(() => {
    draw();
  }, [draw]);

  useEffect(() => {
    if (screenshot && canvasRef.current && imageRef.current) {
      draw();
    }
  }, [screenshot, canvasSize, draw]);

  // Mouse drag coordinates
  const getCanvasCoords = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min((e.clientX - rect.left) * canvas.width / rect.width, canvas.width)),
      y: Math.max(0, Math.min((e.clientY - rect.top) * canvas.height / rect.height, canvas.height)),
    };
  };

  const handleMouseDown = (e) => {
    if (e.button !== 0) return;
    const coords = getCanvasCoords(e);
    setIsDragging(true);
    setDragStart(coords);
    setSelection({ startX: coords.x, startY: coords.y, endX: coords.x, endY: coords.y });
  };

  const handleMouseMove = (e) => {
    if (!isDragging || !dragStart) return;
    const coords = getCanvasCoords(e);
    setSelection({
      startX: dragStart.x,
      startY: dragStart.y,
      endX: coords.x,
      endY: coords.y,
    });
  };

  const handleMouseUp = () => {
    if (!isDragging) return;
    setIsDragging(false);
    if (selection) {
      const w = Math.abs(selection.endX - selection.startX);
      const h = Math.abs(selection.endY - selection.startY);
      if (w < 10 || h < 10) {
        setSelection(null);
      }
    }
  };

  // Confirm crop
  const handleConfirm = async () => {
    if (busy || !selection || !imageRef.current) return;
    setBusy(true); setError("");

    const { startX, startY, endX, endY } = selection;
    const x = Math.min(startX, endX);
    const y = Math.min(startY, endY);
    const w = Math.abs(endX - startX);
    const h = Math.abs(endY - startY);

    const origX = Math.round(x / imageScale);
    const origY = Math.round(y / imageScale);
    const origW = Math.round(w / imageScale);
    const origH = Math.round(h / imageScale);

    const cropCanvas = document.createElement("canvas");
    cropCanvas.width = origW;
    cropCanvas.height = origH;
    const cropCtx = cropCanvas.getContext("2d");
    cropCtx.drawImage(imageRef.current, origX, origY, origW, origH, 0, 0, origW, origH);

    const croppedDataUrl = cropCanvas.toDataURL("image/png");

    try {
      const response = await chrome.runtime.sendMessage({
        type: "CROP_COMPLETE",
        croppedImage: croppedDataUrl,
        mode: analysisMode,
      });
      if (response?.error || response?.results?.error) throw new Error(response.error || response.results.error);
      if (!response?.results) throw new Error("No result received. Please try again.");
      setResult(response.results);
    } catch (err) {
      setError(err.message || "Could not complete the scan.");
    } finally { setBusy(false); }
  };

  const handleCancel = async () => {
    try {
      await chrome.runtime.sendMessage({ type: "CROP_CANCELLED" });
    } catch {
      // Ignore
    }
    window.close();
  };

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && !busy) handleCancel();
      if (e.key === "Enter" && selection && !busy && !result) handleConfirm();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  const hasSelection = selection && Math.abs(selection.endX - selection.startX) > 10 && Math.abs(selection.endY - selection.startY) > 10;

  if (result) return <div className="crop-result"><img src="icons/brand.svg" width="48" alt="Verif.ai"/><span className="result-kicker">VERIFICATION COMPLETE</span><h1>{result.label}</h1><p>{result.summary || result.reasoningSummary || "Review the evidence in your scan history."}</p><p className="result-confidence">{result.confidence}% confidence</p>{result.limitations && <p>{result.limitations}</p>}<button className="btn-confirm" onClick={() => window.close()}>Done · saved to history</button></div>;

  if (!screenshot) {
    return (
      <div className="cropper-loading">
        <p role="status">{error || "Loading screenshot…"}</p>
      </div>
    );
  }

  return (
    <div className="cropper-container">
      {/* Top Toolbar */}
      <header className="cropper-toolbar">
        <div className="toolbar-left">
          <div className="cropper-brand">
            <img src="icons/brand.svg" width="28" height="28" alt=""/>
            <strong>Verif<span style={{color:"#f4b400"}}>.</span>ai</strong>
            <span className="cropper-brand-pill">Capture Region</span>
          </div>

          <div className="mode-toggle">
            <button
              type="button"
              className={`mode-btn ${analysisMode === "media" ? "active" : ""}`}
              onClick={() => setAnalysisMode("media")}
            >
              <ScanSearch size={13} /> Visual AI Forensics
            </button>
            <button
              type="button"
              className={`mode-btn ${analysisMode === "news_image" ? "active" : ""}`}
              onClick={() => setAnalysisMode("news_image")}
            >
              <Newspaper size={13} /> News Graphic OCR
            </button>
          </div>
        </div>

        <div className="toolbar-right">
          <button className="btn-cancel" onClick={handleCancel} disabled={busy}>
            <X size={14} /> Cancel (Esc)
          </button>
          <button
            className="btn-confirm"
            onClick={handleConfirm}
            disabled={!hasSelection || busy}
          >
            <Check size={14} /> {busy ? "Analyzing…" : "Analyze region (Enter)"}
          </button>
        </div>
      </header>

      {/* Canvas Area */}
      {error && <div className="crop-error" role="alert">{error}</div>}
      {busy && <div className="crop-progress" role="status">Checking with the Verif.ai backend. Your result will appear here…</div>}
      <main className="canvas-wrapper">
        <canvas
          ref={canvasRef}
          width={canvasSize.width}
          height={canvasSize.height}
          onPointerDown={e => { if (!busy) { e.currentTarget.setPointerCapture(e.pointerId); handleMouseDown(e); } }}
          onPointerMove={handleMouseMove}
          onPointerUp={handleMouseUp}
          style={{ cursor: isDragging ? "crosshair" : "crosshair" }}
        />
        {!selection && (
          <div className="selection-prompt">
            <Crop size={18} />
            <span>Drag a box across the image or graphic region you want to check</span>
          </div>
        )}
      </main>
    </div>
  );
}
