import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Wraps the browser Web Speech API for both directions:
 *   speak()  - reads assistant messages aloud
 *   listen() - captures a spoken answer as text
 *
 * Both degrade silently on unsupported browsers; the caller checks
 * `ttsSupported` / `sttSupported` to decide whether to show controls.
 */
export function useSpeech() {
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const recognitionRef = useRef(null);

  const ttsSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const SpeechRecognition =
    typeof window !== "undefined" &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);
  const sttSupported = Boolean(SpeechRecognition);

  const speak = useCallback(
    (text) => {
      if (!ttsSupported || !text) return;
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      utterance.pitch = 1;
      utterance.lang = "en-IN";
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);

      window.speechSynthesis.speak(utterance);
    },
    [ttsSupported]
  );

  const stopSpeaking = useCallback(() => {
    if (!ttsSupported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [ttsSupported]);

  const startListening = useCallback(() => {
    if (!sttSupported || listening) return;

    const recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.continuous = false;

    recognition.onstart = () => {
      setTranscript("");
      setListening(true);
    };
    recognition.onresult = (event) => {
      setTranscript(event.results[0][0].transcript);
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    recognition.start();
  }, [SpeechRecognition, sttSupported, listening]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const clearTranscript = useCallback(() => setTranscript(""), []);

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort?.();
      if (ttsSupported) window.speechSynthesis.cancel();
    };
  }, [ttsSupported]);

  return {
    speak,
    stopSpeaking,
    speaking,
    ttsSupported,
    startListening,
    stopListening,
    listening,
    transcript,
    clearTranscript,
    sttSupported,
  };
}
