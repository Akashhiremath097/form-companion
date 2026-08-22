import { useCallback, useEffect, useRef, useState } from "react";

import AccessibilityBar from "./components/AccessibilityBar";
import ChatWidget from "./components/ChatWidget";
import FormPreview from "./components/FormPreview";
import { useSpeech } from "./hooks/useSpeech";
import { api } from "./services/api";

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [formTitle, setFormTitle] = useState("");
  const [messages, setMessages] = useState([]);
  const [preview, setPreview] = useState([]);
  const [progress, setProgress] = useState({ answered: 0, skipped: 0, total: 10, remaining: 10 });
  const [currentFieldId, setCurrentFieldId] = useState(null);
  const [complete, setComplete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [readAloud, setReadAloud] = useState(false);

  const speech = useSpeech();
  const { speak, stopSpeaking, speaking } = speech;
  const startedRef = useRef(false);

  const pushMessage = useCallback((role, content) => {
    setMessages((current) => [...current, { role, content }]);
  }, []);

  const announce = useCallback(
    (text) => {
      if (readAloud) speak(text);
    },
    [readAloud, speak]
  );

  // Start a session once on mount. The ref guards against React 18 strict-mode
  // double-invoking the effect and creating two sessions.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    (async () => {
      setBusy(true);
      try {
        const data = await api.startSession();
        setSessionId(data.session_id);
        setFormTitle(data.form_title);
        setCurrentFieldId(data.current_field?.id ?? null);
        setProgress(data.progress);
        pushMessage("assistant", data.message);

        const previewData = await api.getPreview(data.session_id);
        setPreview(previewData.preview);
      } catch (error) {
        pushMessage(
          "error",
          `${error.message} The assistant could not start. Refresh the page to try again.`
        );
      } finally {
        setBusy(false);
      }
    })();
  }, [pushMessage]);

  const applyResponse = useCallback(
    (data) => {
      setPreview(data.preview);
      setProgress(data.progress);
      setCurrentFieldId(data.current_field?.id ?? null);
      setComplete(data.complete);
      pushMessage("assistant", data.message);
      announce(data.message);
    },
    [announce, pushMessage]
  );

  const handleSend = async (reply) => {
    if (!sessionId) return;
    pushMessage("user", reply);
    setBusy(true);
    try {
      const data = await api.sendAnswer(sessionId, reply);
      applyResponse(data);
    } catch (error) {
      pushMessage("error", error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleSimplify = async () => {
    if (!sessionId) return;
    setBusy(true);
    try {
      const data = await api.simplify(sessionId);
      pushMessage("assistant", data.explanation);
      announce(data.explanation);
    } catch (error) {
      pushMessage("error", error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleEdit = async (fieldId) => {
    if (!sessionId) return;
    setBusy(true);
    try {
      const data = await api.resetField(sessionId, fieldId);
      applyResponse(data);
    } catch (error) {
      pushMessage("error", error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleRepeat = () => {
    if (speaking) {
      stopSpeaking();
      return;
    }
    const last = [...messages].reverse().find((message) => message.role === "assistant");
    if (last) speak(last.content);
  };

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to the conversation
      </a>

      <div className="app">
        <header className="masthead">
          <h1>Form Companion</h1>
          <p>
            Fill in official forms by talking, not typing into boxes. Answer one question at
            a time, in your own words, and ask for an explanation whenever a question is
            unclear.
          </p>
        </header>

        <AccessibilityBar
          readAloud={readAloud}
          onToggleReadAloud={() => setReadAloud((value) => !value)}
          ttsSupported={speech.ttsSupported}
        />

        <main id="main" className="workspace">
          <ChatWidget
            messages={messages}
            onSend={handleSend}
            onSimplify={handleSimplify}
            onRepeat={handleRepeat}
            busy={busy}
            complete={complete}
            speech={speech}
          />

          <FormPreview
            formTitle={formTitle}
            preview={preview}
            progress={progress}
            currentFieldId={currentFieldId}
            onEdit={handleEdit}
            complete={complete}
          />
        </main>

        <p className="privacy-note">
          Your answers stay in this browser session only. Nothing is saved to an account,
          and the session is discarded when you close the page.
        </p>
      </div>
    </>
  );
}
