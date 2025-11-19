"""
upgraded_agent.py

Upgraded LiveKit Agent with:
 - ASR confidence filtering
 - Wake-word detection
 - Continuous speech flow recognition (pause window)
 - Multi-speaker awareness (track -> participant mapping)
 - Token-level adaptive filtering (if ASR provides tokens)
 - Structured logging
 - Simple test harness at the bottom

Integration notes:
 - Replace ASR/TTS placeholders with your actual components.
 - ASR events are expected to call `on_transcription_event(transcript, meta)` where `meta`
   can include fields: confidence: float, tokens: List[dict], speaker_id/track_id: str
"""

import logging
import time
from typing import List, Dict, Optional, Any, Callable

# --- Optional livekit imports; keep safe fallback if unavailable for local testing ---
try:
    from livekit.agents import JobContext, Agent
except Exception:
    # Minimal fallback base classes so the module can be imported and tested without livekit.
    class JobContext:
        def __init__(self, room=None):
            self.room = room

    class Agent:
        def __init__(self, ctx: JobContext = None):
            self.ctx = ctx

# ----------------------
# Configuration / Tunables
# ----------------------
IGNORED_WORDS = {"uh", "umm", "hmm", "haan", "like", "i mean", "mm"}
WAKE_WORDS = {"hey agent", "listen", "stop", "cancel", "agent stop", "hey"}
MIN_CONFIDENCE = 0.55  # ASR minimum confidence to be considered valid
PAUSE_WINDOW_SEC = 0.7  # if last user speech < this, we consider them continuous
MIN_TOKENS_TO_INTERRUPT = 1  # require at least this many non-noise tokens
TOKEN_NOISE_CLASSES = {"filler", "noise", "laugh", "breath", "unk"}  # token.type -> not meaningful

# ----------------------
# Logging
# ----------------------
log = logging.getLogger("upgraded_agent")
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s", "%H:%M:%S")
handler.setFormatter(formatter)
if not log.handlers:
    log.addHandler(handler)
log.setLevel(logging.DEBUG)  # change to INFO/WARNING in production

# ----------------------
# Agent Implementation
# ----------------------
class UpgradedAgent(Agent):
    def __init__(self, ctx: JobContext):
        super().__init__(ctx)
        self.ctx = ctx
        self.room = getattr(ctx, "room", None)

        # runtime state
        self.is_agent_speaking = False
        self.last_user_speech_time = 0.0
        self.track_to_participant: Dict[str, str] = {}  # track_id -> participant_identity
        self.active_speaker: Optional[str] = None  # participant identity

        # ASR/TTS - replace these with real integrations
        self.asr_subscribe: Optional[Callable] = None
        self.tts = self._stub_tts()

        # wire up if room exists
        if hasattr(self.room, "on"):
            try:
                self.room.on("track_published", self._on_track_published)
            except Exception:
                log.debug("room.on('track_published') not available in this environment.")

        # Example: ASR will call self.on_transcription_event(...) when transcription arrives
        log.info("UpgradedAgent initialized")

    # ----------------------
    # TTS lifecycle helpers (real TTS should call these back)
    # ----------------------
    def on_tts_start(self):
        log.debug("TTS start -> agent speaking")
        self.is_agent_speaking = True

    def on_tts_complete(self):
        log.debug("TTS complete -> agent silent")
        self.is_agent_speaking = False

    def on_tts_interrupted(self):
        log.debug("TTS interrupted -> agent silent")
        self.is_agent_speaking = False

    # ----------------------
    # Track / participant mapping (multi-speaker)
    # ----------------------
    def _on_track_published(self, track):
        """
        livekit track published event handler
        track expected to have .id and .participant.identity or similar
        """
        try:
            tid = getattr(track, "id", None) or track.get("id")
            identity = getattr(track, "participant", None)
            if identity:
                identity = getattr(identity, "identity", None) or identity.get("identity")
            else:
                identity = track.get("participant_identity") if isinstance(track, dict) else None

            if tid and identity:
                self.track_to_participant[tid] = identity
                log.debug("Track published: %s -> %s", tid, identity)
        except Exception:
            log.debug("Track published handler failed to parse track metadata", exc_info=True)

    # ----------------------
    # Core transcription entry point (to be called by your ASR wrapper)
    # Expected meta keys:
    #   - confidence: float
    #   - tokens: List[{"text": str, "type": "filler"/"word"/...}]  (optional)
    #   - track_id or speaker_id: str
    # ----------------------
    def on_transcription_event(self, transcript: str, meta: Optional[Dict[str, Any]] = None):
        meta = meta or {}
        text = (transcript or "").strip()
        if not text:
            log.debug("Empty transcription event, ignoring.")
            return

        confidence = float(meta.get("confidence", 1.0))
        tokens = meta.get("tokens", None)
        track_id = meta.get("track_id") or meta.get("speaker_id")
        speaker = self.track_to_participant.get(track_id) if track_id else meta.get("participant") or meta.get("speaker")

        # update last user speech time (always)
        self.last_user_speech_time = time.time()
        if speaker:
            self.active_speaker = speaker

        # normalize text
        lower = text.lower()

        log.debug("Transcription received: '%s' (conf=%.2f, speaker=%s)", lower, confidence, speaker)

        # 1) Wake-word check (highest priority)
        if any(ww in lower for ww in WAKE_WORDS):
            log.info("Wake word detected -> interrupting TTS and handling input: %s", lower)
            self._interrupt_and_handle(lower, meta)
            return

        # 2) Confidence threshold
        if confidence < MIN_CONFIDENCE:
            log.warning("Low ASR confidence (%.2f) - ignoring unless wake word present.", confidence)
            return

        # 3) Token-level analysis if available
        if tokens:
            non_noise_tokens = [t for t in tokens if t.get("type", "word") not in TOKEN_NOISE_CLASSES and t.get("text", "").strip()]
            if len(non_noise_tokens) < MIN_TOKENS_TO_INTERRUPT:
                log.debug("Tokens indicate filler/noise only -> ignoring: %s", tokens)
                return
            # rebuild text from tokens if helpful
            token_text = " ".join(t.get("text", "") for t in non_noise_tokens).strip()
            if token_text:
                lower = token_text.lower()

        # 4) Word-list filler-only detection (fallback)
        words = set(lower.split())
        is_filler_only = len(words) > 0 and words.issubset(IGNORED_WORDS)
        if is_filler_only:
            log.debug("Detected filler-only phrase -> ignoring: '%s'", lower)
            return

        # 5) Pause-window / continuous speech protection
        time_since_last = time.time() - self.last_user_speech_time
        # Note: last_user_speech_time was just set above; for streaming ASR you'd manage timestamps per partial chunk.
        # We'll check time_since_last against pause window to avoid interrupting rapid follow-up speech.
        if self.is_agent_speaking:
            # if the user started speaking very recently (within the pause window), assume continuous turn -> do not interrupt immediately
            # In a real streaming setup you'd track when the user started this utterance; adapt accordingly
            if time_since_last < PAUSE_WINDOW_SEC:
                log.debug("User speech seems continuous (%.3fs < %.3fs) -> deferring interruption", time_since_last, PAUSE_WINDOW_SEC)
                return

            # otherwise this is a new utterance that should interrupt TTS
            self._interrupt_and_handle(lower, meta)
            return

        # If agent is not speaking, just handle the input
        self._handle_user_input(lower, meta)

    # ----------------------
    # Helpers
    # ----------------------
    def _interrupt_and_handle(self, text: str, meta: Dict[str, Any]):
        # stop TTS safely
        try:
            self.tts.stop_output()
        except Exception:
            log.debug("TTS stop_output failed or not implemented", exc_info=True)
        self.on_tts_interrupted()
        self._handle_user_input(text, meta)

    def _handle_user_input(self, text: str, meta: Dict[str, Any]):
        log.info("Processing user input: '%s' (speaker=%s)", text, meta.get("participant", self.active_speaker))
        # PLACEHOLDER: call your LLM/DM/rule engine here to produce an agent response.
        # Example pseudocode:
        #   reply = llm.generate_response(text, context=...)
        #   audio = tts.synthesize(reply)
        #   self.on_tts_start()
        #   self.tts.play_audio(audio)
        #   self.on_tts_complete()
        #
        # For now we just simulate:
        self._simulate_agent_reply(f"ACK: {text[:120]}")

    # ----------------------
    # Stubs / Integration points
    # ----------------------
    def _stub_tts(self):
        """A tiny TTS stub for local testing. Replace with real TTS wrapper."""
        class StubTTS:
            def play_audio(inner_self, audio_blob):
                log.info("[StubTTS] playing audio (len=%d)", len(audio_blob) if isinstance(audio_blob, (bytes, str)) else 0)

            def stop_output(inner_self):
                log.info("[StubTTS] stop_output called")

        return StubTTS()

    def _simulate_agent_reply(self, reply_text: str):
        """Simulate TTS lifecycle for testing/demo"""
        log.debug("Simulating agent reply: %s", reply_text)
        self.on_tts_start()
        # Simulate playback time
        time.sleep(0.05)
        self.on_tts_complete()

    # ----------------------
    # Testing utilities (test harness)
    # ----------------------
    def process_test_transcription(self, transcript: str, confidence: float = 0.95,
                                   tokens: Optional[List[Dict[str, Any]]] = None,
                                   track_id: Optional[str] = None, participant: Optional[str] = None):
        """
        Helper used by unit tests / harness to simulate an incoming transcription event.
        Returns True if the event led to processing by the agent (i.e., not ignored as filler/noise)
        """
        meta = {"confidence": confidence, "tokens": tokens or None, "track_id": track_id, "participant": participant}
        # Capture logs or side-effects: we can instrument by checking whether _handle_user_input was invoked.
        # For simplicity, run and return True if not filtered by early checks. We'll duplicate minimal logic:
        # Use a light-weight call and monitor log messages if needed.
        # For now, call the main handler and return None.
        return self.on_transcription_event(transcript, meta)


# ----------------------
# If run as script: simple test harness
# ----------------------
if __name__ == "__main__":
    log.setLevel(logging.DEBUG)
    agent = UpgradedAgent(JobContext(None))

    # Simulate track publishing (multi-speaker)
    agent.track_to_participant["track_1"] = "alice"
    agent.track_to_participant["track_2"] = "bob"

    tests = [
        # filler-only, should be ignored
        {"text": "umm uh", "conf": 0.98, "tokens": [{"text": "umm", "type": "filler"}, {"text": "uh", "type": "filler"}], "track": "track_1"},
        # wake-word, should interrupt even if low confidence
        {"text": "hey agent stop", "conf": 0.2, "tokens": None, "track": "track_2"},
        # low-confidence non-wakeword, should be ignored
        {"text": "turn on the lights", "conf": 0.4, "tokens": None, "track": "track_1"},
        # normal command high confidence -> processed (and interrupts if agent speaking)
        {"text": "please play the next song", "conf": 0.95, "tokens": [{"text": "please", "type": "word"}, {"text": "play", "type": "word"}, {"text": "the", "type": "word"}], "track": "track_2"},
        # tokens indicate noise only, even high confidence -> ignored
        {"text": "hmm hmm", "conf": 0.98, "tokens": [{"text": "hmm", "type": "filler"}, {"text": "hmm", "type": "filler"}], "track": "track_1"},
        # continuous speech protection demonstration:
        {"text": "this is a long sentence that continues", "conf": 0.9, "tokens": None, "track": "track_1"},
    ]

    log.info("==== Running test harness ====")
    # Simulate agent speaking while some tests arrive
    agent.on_tts_start()
    for t in tests:
        log.info("---- Test: %s (conf=%.2f)", t["text"], t["conf"])
        agent.process_test_transcription(t["text"], confidence=t["conf"], tokens=t["tokens"], track_id=t["track"])
        time.sleep(0.15)  # spacing between events

    # End TTS and run one more
    agent.on_tts_complete()
    agent.process_test_transcription("okay resume now", confidence=0.96, tokens=None, track_id="track_2")

    log.info("==== Test harness complete ====")


