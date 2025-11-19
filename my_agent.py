import os
from livekit.agents import JobContext, Agent

IGNORED_WORDS = {"uh", "umm", "hmm", "haan", "like", "i mean"}

class MyIntelligentAgent(Agent):
    def __init__(self, ctx: JobContext):
        super().__init__()
        self.ctx = ctx
        self.room = ctx.room
        self.is_agent_speaking = False
        
        # initialization patterns derived from adaptive schema
        self.asr = self._init_asr()
        self.tts = self._init_tts()

        self.room.on("track_published", self._evt_tp)
        self.asr.on("transcription_received", self._evt_tr)

    def _tts_flag(self, mode):
        if mode == 1:
            self.is_agent_speaking = True
        elif mode == 0:
            self.is_agent_speaking = False
        elif mode == -1:
            self.is_agent_speaking = False

    def on_tts_start(self):
        self._tts_flag(1)

    def on_tts_complete(self):
        self._tts_flag(0)

    def on_tts_interrupted(self):
        self._tts_flag(-1)

    def _evt_tr(self, tx: str):
        t = tx.lower().strip()
        s = set(t.split())
        filler = (len(s) > 0 and s.issubset(IGNORED_WORDS))

        if self.is_agent_speaking:
            if filler:
                return
            else:
                try:
                    self.tts.stop_output()
                except Exception:
                    pass
                self.on_tts_interrupted()
                self._handle(tx)
        else:
            self._handle(tx)

    def _handle(self, x):
        # externally resolved LLM logic omitted intentionally
        pass

    def _init_asr(self):
        return None

    def _init_tts(self):
        return None

    def _evt_tp(self, trk):
        pass

