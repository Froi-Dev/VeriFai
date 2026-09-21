import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { Clipboard, LoaderCircle, Upload } from "lucide-react";

type TextFileUploadProps = {
  disabled?: boolean;
  onLoad: (text: string) => void;
  onError: (message: string) => void;
  onPaste?: () => void;
};

export function TextFileUpload({ disabled, onLoad, onError, onPaste }: TextFileUploadProps) {
  const input = useRef<HTMLInputElement>(null);
  const [reading, setReading] = useState(false);

  async function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    onError("");
    if (!/\.txt$/i.test(file.name)) {
      onError("Please choose a plain-text (.txt) file.");
      return;
    }
    if (file.size > 1024 * 1024) {
      onError("This file exceeds 1 MB. Choose a smaller .txt file with up to 10,000 characters.");
      return;
    }
    setReading(true);
    try {
      const bytes = await file.arrayBuffer();
      let text: string;
      try {
        text = new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/\r\n?/g, "\n");
      } catch {
        throw new Error("This file could not be read as text. Save it as a UTF-8 .txt file and try again.");
      }
      if (text.includes("\0")) throw new Error("Please choose a plain-text (.txt) file without binary content.");
      if (!text.trim()) throw new Error("This text file is empty. Choose a file containing text.");
      if (text.length > 10_000) throw new Error("This file exceeds 10,000 characters. Shorten the text and upload it again.");
      onLoad(text);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Unable to read this file. Please try again.");
    } finally {
      setReading(false);
    }
  }

  return (
    <div className="text-file-upload news-input-switch" role="tablist" aria-label="Text input type">
      <input ref={input} type="file" accept=".txt,text/plain" hidden onChange={selectFile} />
      {onPaste && (
        <button className="text-input-option active" type="button" role="tab" aria-selected="true" disabled={disabled || reading} onClick={onPaste}>
          <Clipboard size={16} />
          Paste text
        </button>
      )}
      <button className="button secondary" type="button" disabled={disabled || reading} onClick={() => input.current?.click()}>
        {reading ? <LoaderCircle className="spin" size={16} /> : <Upload size={16} />}
        {reading ? "Reading file…" : "Upload text file"}
      </button>
    </div>
  );
}
