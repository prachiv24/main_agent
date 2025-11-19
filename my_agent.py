import os
from livekit.agents import JobContext, Agent

# Additional custom imports—add utilities if needed

# Configuration: Filler words for interruption filtering
FILLERS = {"uh", "umm", "hmm", "haan", "like", "i mean"}

class ConversationalInterruptAgent(Agent):
    """
    A LiveKit agent built for nuanced voice interruption management.
    The design here emphasizes real-world conversational needs and experimental triggers.
    """

    def __init__(self, context: JobContext):
        super().__init__()
        self.context = context
        self.room = context.room

        # Tracks active speech synthesis (agent speaking status)
        self.synth_active = False

        # ASR and TTS modules—real implementations below
        self.speech_rec = self._setup_asr()
        self.speech_syn = self._setup_tts()

        # Register event listeners for relevant LiveKit events
        self.room.on("track_published", self._on_track_published)
        self.speech_rec.on("transcription_received", self._on_transcript_rx)

    # Event handler: speech synthesis starts
    def _on_tts_start(self):
        print("[INFO] Agent vocalization began.")
        self.synth_active = True

    # Event handler: synthesis completes (all audio sent)
    def _on_tts_finish(self):
        print("[INFO] Agent finished talking.")
        self.synth_active = False

    # Event handler: forced TTS interruption (external/user command)
    def _on_tts_halt(self):
        print("[WARN] Agent interrupted—TTS forced to stop.")
        self.synth_active = False

    # Core ASR event: transcript received from user
    def _on_transcript_rx(self, transcript: str):
        clean_txt = transcript.lower().strip()
        words = set(clean_txt.split())

        is_only_filler = words.issubset(FILLERS) and len(words) > 0

        # If the agent is talking, process interruptions
        if self.synth_active:
            if is_only_filler:
                print(f"[DEBUG] Ignored filler: '{transcript}' while agent speaks.")
                return
            # Interrupt agent with real user input
            print(f"[ACTION] Valid interruption: '{transcript}'. Stopping TTS for processing.")
            try:
                self.speech_syn.stop_output()
            except Exception as stop_err:
                print("[ERROR] Issue stopping TTS:", stop_err)
            self._on_tts_halt()
            self._process_user_input(transcript)
        else:
            # Agent is silent, so all speech is considered input
            print(f"[ACTION] Registered user input: '{transcript}' while agent is silent.")
            self._process_user_input(transcript)

    # Main dialogue logic—connect to your LLM/DM here
    def _process_user_input(self, utterance: str):
        # Placeholder: integrate business logic, external API, or language model
        # Example: send utterance to backend, get response, trigger TTS output
        print(f"[WORKFLOW] Processing user query: {utterance}")
        # After processing and preparing response:
        # self._on_tts_start()
        # self.speech_syn.play_audio(response_audio)
        # self._on_tts_finish()
        pass

    # Setup methods for ASR and TTS (customize for real implementations)
    def _setup_asr(self):
        # Implement actual ASR system integration here
        print("[INIT] Initializing ASR...")
        return None  # Replace with instantiated ASR object

    def _setup_tts(self):
        # Implement actual TTS engine setup here, including callbacks
        print("[INIT] Initializing TTS...")
        return None  # Replace with instantiated TTS object

    def _on_track_published(self, *args, **kwargs):
        print("[EVENT] Track published in room.")
        # Custom logic per track addition or relevant audio events
        pass
