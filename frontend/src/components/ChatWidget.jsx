import { useEffect, useRef, useState } from "react";

const ROLE_LABEL = {
  assistant: "Assistant",
  user: "You",
  error: "Problem",
};

export default function ChatWidget({
  messages,
  onSend,
  onSimplify,
  onRepeat,
  busy,
  complete,
  speech,
}) {
  const [draft, setDraft] = useState("");
  const transcriptRef = useRef(null);
  const inputRef = useRef(null);

  const { transcript, clearTranscript, listening, startListening, stopListening, sttSupported } =
    speech;

  // Voice input lands in the textarea so the user can correct it before sending.
  useEffect(() => {
    if (transcript) {
      setDraft((current) => (current ? `${current} ${transcript}` : transcript));
      clearTranscript();
      inputRef.current?.focus();
    }
  }, [transcript, clearTranscript]);

  useEffect(() => {
    const node = transcriptRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  const submit = () => {
    const value = draft.trim();
    if (!value || busy) return;
    setDraft("");
    onSend(value);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <section className="panel" aria-labelledby="chat-heading">
      <div className="panel-head">
        <h2 id="chat-heading">Conversation</h2>
        <button
          type="button"
          className="btn secondary"
          onClick={onRepeat}
          disabled={!speech.ttsSupported || messages.length === 0}
        >
          {speech.speaking ? "Stop reading" : "Read last message"}
        </button>
      </div>

      <div
        className="transcript"
        ref={transcriptRef}
        role="log"
        aria-live="polite"
        aria-atomic="false"
        aria-label="Conversation history"
      >
        {messages.map((message, index) => (
          <div key={index} className={`bubble ${message.role}`}>
            <span className="bubble-role">{ROLE_LABEL[message.role]}</span>
            {message.content}
          </div>
        ))}
        {busy && (
          <p className="thinking" aria-live="polite">
            Working on that…
          </p>
        )}
      </div>

      <div className="composer">
        <label htmlFor="answer-input" className="visually-hidden">
          Your answer
        </label>
        <div className="composer-row">
          <textarea
            id="answer-input"
            ref={inputRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={complete ? "The form is finished." : "Type your answer here"}
            disabled={busy || complete}
            rows={2}
          />
          <button type="button" className="btn" onClick={submit} disabled={busy || complete || !draft.trim()}>
            Send
          </button>
        </div>

        <div className="composer-actions">
          {sttSupported && (
            <button
              type="button"
              className={`btn secondary ${listening ? "listening" : ""}`}
              onClick={listening ? stopListening : startListening}
              disabled={busy || complete}
              aria-pressed={listening}
            >
              {listening ? "Stop recording" : "Answer by voice"}
            </button>
          )}
          <button
            type="button"
            className="btn secondary"
            onClick={onSimplify}
            disabled={busy || complete}
          >
            Explain this question
          </button>
        </div>
      </div>
    </section>
  );
}
