"""
Upgraded LiveKit Agent (intern version)

This version adds:
- basic wake word handling
- simple interruption rules
- some token filtering stuff
- continuous speech check (rough attempt)
- multi-speaker mapping (still kinda basic)

Note: This is still a work-in-progress. I tried to keep things readable.
"""

import time
import logging
from typing import Dict, Any, Optional, List

try:
    from livekit.agents import JobContext, Agent
except:
    # fallback for local testing
    class JobContext:
        def __init__(self, room=None):
            self.room = room

    class Agent:
        def __init__(self, ctx=None):
            pass


# I put these up here so they’re easier to tweak later
IGNORED_WORDS = {"uh", "umm", "hmm", "haan", "like", "i mean", "mm"}
WAKE_WORDS = {"hey agent", "listen", "stop", "cancel"}

MIN_CONF = 0.55
PAUSE_WINDOW = 0.7
TOKEN_NOISE_TYPES = {"filler", "noise", "laugh", "breath"}


log = logging.getLogger("intern_agent")
logging.basicConfig(level=logging.DEBUG)


class UpgradedAgent(Agent):
    def __init__(self, ctx: JobContext):
        super().__init__(ctx)
        self.ctx = ctx
        self.room = getattr(ctx, "room", None)

        self.is_agent_speaking = False
        self.last_user_speech = 0.0

        # this maps trackIDs to actual participant identities
        self.track_map: Dict[str, str] = {}
        self.active_speaker: Optional[str] = None

        # temp fake TTS system until real one is connected
        self.tts = self._fake_tts()

        if self.room and hasattr(self.room, "on"):
            self.room.on("track_published", self._on_track)

        log.info("Intern agent initialized and running.")

    # -----------------------------
    # TTS status functions
    # -----------------------------
    def on_tts_start(self):
        self.is_agent_speaking = True
        log.debug("TTS started")

    def on_tts_complete(self):
        self.is_agent_speaking = False
        log.debug("TTS done")

    def on_tts_interrupted(self):
        self.is_agent_speaking = False
        log.debug("TTS interrupted")

    # -----------------------------
    # When LiveKit publishes a new track
    # -----------------------------
    def _on_track(self, track):
        # Trying to extract track + participant identity carefully
        try:
            tid = getattr(track, "id", None)
            identity = getattr(getattr(track, "participant", None), "identity", None)
            if tid and identity:
                self.track_map[tid] = identity
                log.debug(f"Track registered: {tid} -> {identity}")
        except Exception as e:
            log.warning(f"Couldn't read track metadata: {e}")

    # -----------------------------
    # Main ASR transcription entry
    # -----------------------------
    def on_transcription_event(self, text: str, meta: Optional[Dict[str, Any]] = None):
        meta = meta or {}
        if not text:
            return

        clean = text.lower().strip()
        conf = float(meta.get("confidence", 1.0))
        tokens = meta.get("tokens")
        tid = meta.get("track_id")
        speaker = self.track_map.get(tid) if tid else None

        # update timestamps
        now = time.time()
        self.last_user_speech = now
        if speaker:
            self.active_speaker = speaker

        log.debug(f"Got user speech: '{clean}' (conf={conf})")

        # 1 — wake words shortcut
        for ww in WAKE_WORDS:
            if ww in clean:
                log.info("Wake word triggered")
                return self._interrupt_and_process(clean, meta)

        # 2 — reject low-confidence speech unless it's a wake word
        if conf < MIN_CONF:
            log.debug("ASR too low confidence, skipping")
            return

        # 3 — attempt token-level filtering
        if tokens:
            non_noise = []
            for t in tokens:
                # some ASR tokens use "type", some "token_type" — interns learn as we go lol
                ttype = t.get("type") or t.get("token_type")
                if ttype not in TOKEN_NOISE_TYPES:
                    non_noise.append(t)

            if not non_noise:
                log.debug("All tokens were noise/filler → ignoring")
                return

            # rebuild text from tokens (optional)
            built = " ".join(t.get("text", "") for t in non_noise).strip()
            if built:
                clean = built.lower()

        # 4 — fallback filler detection
        words = set(clean.split())
        if words and words.issubset(IGNORED_WORDS):
            log.debug("Filler-only input → ignoring")
            return

        # 5 — continuous speech protection (not perfect)
        time_since = now - self.last_user_speech
        if self.is_agent_speaking:
            if time_since < PAUSE_WINDOW:
                log.debug("User might still be talking, waiting…")
                return
            return self._interrupt_and_process(clean, meta)

        # otherwise normal handling
        self._process_user(clean, meta)

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _interrupt_and_process(self, text, meta):
        try:
            self.tts.stop_output()
        except:
            pass
        self.on_tts_interrupted()
        self._process_user(text, meta)

    def _process_user(self, text, meta):
        speaker = meta.get("participant") or self.active_speaker
        log.info(f"Handling input from {speaker}: {text}")

        # TODO: call real model here
        reply = f"Okay, you said: {text}"

        # simulate TTS response
        self._fake_reply(reply)

    # -----------------------------
    # Fake TTS for dev/testing
    # -----------------------------
    def _fake_tts(self):
        class FakeTTS:
            def play_audio(self, data):
                log.info(f"[FakeTTS] playing {len(str(data))} chars of audio")

            def stop_output(self):
                log.info("[FakeTTS] stop_output")

        return FakeTTS()

    def _fake_reply(self, text: str):
        self.on_tts_start()
        time.sleep(0.05)
        self.on_tts_complete()


# ------------------------------------------------
# Simple local testing (not official tests)
# ------------------------------------------------
if __name__ == "__main__":
    a = UpgradedAgent(JobContext())

    # These are not perfect tests, just quick checks while developing
    a.on_transcription_event("umm uh", {"confidence": 0.9, "tokens": [{"text": "umm", "type": "filler"}]})
    a.on_transcription_event("hey agent stop", {"confidence": 0.1})
    a.on_transcription_event("yeah actually I wanted to ask", {"confidence": 0.95})
    a.on_transcription_event("hmm hmm", {"confidence": 0.99, "tokens": [{"text": "hmm", "type": "filler"}]})



