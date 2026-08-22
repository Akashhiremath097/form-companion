import { useCallback, useEffect, useRef, useState } from "react";

import AccessibilityBar from "./components/AccessibilityBar";
import FormUpload from "./components/FormUpload";
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
  const [language, setLanguage] = useState("en");
  const [uploading, setUploading] = useState(false);
  const [isUpload, setIsUpload] = useState(false);

  const speech = useSpeech(language);
  const { speak, stopSpeaking, speaking } = speech;
  const startedRef = useRef(false);

  const pushMessage = useCallback((role, content) => {
    setMessages((current) => {
      // Guard against the same assistant message landing twice. React 18
      // StrictMode double-invokes effects in development, and a duplicated
      // question is confusing for anyone, but especially for someone using a
      // screen reader who hears the whole thing read out again.
      const last = current[current.length - 1];
      if (last && last.role === role && last.content === content) return current;
      return [...current, { role, content }];
    });
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
        const data = await api.startSession(language);
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

  const handleChangeLanguage = async (next) => {
    if (next === language) return;
    setLanguage(next);
    if (!sessionId) return;

    setBusy(true);
    try {
      const data = await api.setLanguage(sessionId, next);
      applyResponse(data);
    } catch (error) {
      pushMessage("error", error.message);
    } finally {
      setBusy(false);
    }
  };

  const handleUpload = async (file) => {
    setUploading(true);
    try {
      const data = await api.uploadForm(file, language);
      // A successful upload replaces the whole session, so the transcript
      // starts again from the new form's first question.
      setSessionId(data.session_id);
      setFormTitle(data.form_title);
      setMessages([{ role: "assistant", content: data.message }]);
      setPreview(data.preview);
      setProgress(data.progress);
      setCurrentFieldId(data.current_field?.id ?? null);
      setComplete(false);
      setIsUpload(true);
      announce(data.message);
    } catch (error) {
      pushMessage("error", error.message);
    } finally {
      setUploading(false);
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
          language={language}
          onChangeLanguage={handleChangeLanguage}
        />

        <FormUpload onUpload={handleUpload} busy={uploading} disabled={busy} />

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
            downloadUrl={isUpload && sessionId ? api.downloadUrl(sessionId) : null}
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
