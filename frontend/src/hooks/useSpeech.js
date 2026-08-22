import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Wraps the browser Web Speech API for both directions:
 *   speak()  - reads assistant messages aloud
 *   listen() - captures a spoken answer as text
 *
 * Both degrade silently on unsupported browsers; the caller checks
 * `ttsSupported` / `sttSupported` to decide whether to show controls.
 */
const SPEECH_LOCALES = {
  en: "en-IN",
  kn: "kn-IN",
};

export function useSpeech(language = "en") {
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [voiceAvailable, setVoiceAvailable] = useState(true);
  const [voicesLoaded, setVoicesLoaded] = useState(false);
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
      utterance.lang = SPEECH_LOCALES[language] || "en-IN";
      utterance.onstart = () => setSpeaking(true);
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);

      window.speechSynthesis.speak(utterance);
    },
    [ttsSupported, language]
  );

  const stopSpeaking = useCallback(() => {
    if (!ttsSupported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  }, [ttsSupported]);

  const startListening = useCallback(() => {
    if (!sttSupported || listening) return;

    const recognition = new SpeechRecognition();
    recognition.lang = SPEECH_LOCALES[language] || "en-IN";
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
  }, [SpeechRecognition, sttSupported, listening, language]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  const clearTranscript = useCallback(() => setTranscript(""), []);

  // The Web Speech API can only speak languages the device has a voice for.
  // Kannada voices are not bundled with most desktop browsers, so we check
  // rather than let read-aloud fail silently, which would leave a screen-reader
  // user waiting for audio that never arrives.
  useEffect(() => {
    if (!ttsSupported) return;

    const checkVoices = () => {
      const target = (SPEECH_LOCALES[language] || "en-IN").slice(0, 2);
      const voices = window.speechSynthesis.getVoices();
      // getVoices() is empty on first paint in most browsers and fills in
      // asynchronously, so an early check would wrongly report every language
      // as unsupported.
      if (voices.length === 0) return;
      setVoicesLoaded(true);
      setVoiceAvailable(voices.some((v) => v.lang.toLowerCase().startsWith(target)));
    };

    checkVoices();
    window.speechSynthesis.addEventListener("voiceschanged", checkVoices);
    return () =>
      window.speechSynthesis.removeEventListener("voiceschanged", checkVoices);
  }, [language, ttsSupported]);

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
    voiceAvailable: voicesLoaded ? voiceAvailable : true,
    startListening,
    stopListening,
    listening,
    transcript,
    clearTranscript,
    sttSupported,
  };
}
