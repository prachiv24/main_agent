import os
from livekit.agents import JobContext, Agent
# Import other necessary LiveKit components (e.g., Room, TTS, ASR components)

# 1. CONFIGURATION (IGNORED_WORDS)
# Define the configurable list of filler words as a class constant or load from environment
IGNORED_WORDS = {'uh', 'umm', 'hmm', 'haan', 'like', 'i mean'} 

class MyIntelligentAgent(Agent):
    """
    A custom LiveKit Agent with intelligent voice interruption handling.
    """
    
    def __init__(self, ctx: JobContext):
        super().__init__()
        self.ctx = ctx
        self.room = ctx.room
        
        # 2. STATE INITIALIZATION (in __init__)
        # Crucial state flag: Tracks if the agent is actively talking (TTS output)
        self.is_agent_speaking = False 
        
        # Initialize your ASR and TTS components here
        self.asr = self.setup_asr() # Assume this function is defined
        self.tts = self.setup_tts() # Assume this function is defined
        
        # Setup event listeners for transcription and TTS output
        self.room.on('track_published', self.on_track_published)
        # Assuming your ASR output triggers this event:
        self.asr.on('transcription_received', self.on_user_transcription)
        
    # --- 3. TTS/OUTPUT EVENT HANDLERS ---
    
    # Called when the agent starts sending audio to the user
    def on_tts_start(self):
        """Called by the TTS component wrapper when audio generation starts."""
        print("[STATE] Agent STARTING to speak.")
        self.is_agent_speaking = True
        
    # Called when the agent finishes sending all buffered audio
    def on_tts_complete(self):
        """Called by the TTS component wrapper when the audio queue is empty."""
        print("[STATE] Agent FINISHED speaking.")
        self.is_agent_speaking = False
        
    # Optional: Handler for when TTS is forcefully stopped (e.g., by an interruption)
    def on_tts_interrupted(self):
        """Called when a valid interruption forces TTS to stop."""
        print("[STATE] Agent INTERRUPTED.")
        self.is_agent_speaking = False

    # --- 4. ASR/TRANSCRIPTION EVENT HANDLER (Core Logic) ---
    
    def on_user_transcription(self, transcription: str):
        
        normalized_text = transcription.lower().strip()
        words = set(normalized_text.split())
        
        # Helper check: is the transcription composed ONLY of ignored words?
        is_filler_only = words.issubset(IGNORED_WORDS) and len(words) > 0

        # Conditional Filtering based on Agent State
        if self.is_agent_speaking:
            
            if is_filler_only:
                # SCENARIO 1: Agent is speaking AND user said only fillers.
                # ACTION: IGNORE and CONTINUE speaking.
                print(f"[DEBUG] IGNORED FILLER: '{transcription}'. Agent continues TTS.")
                # Important: Return here to prevent the TTS from being paused by VAD
                return 
            else:
                # SCENARIO 2: Agent is speaking AND user said a genuine command.
                # ACTION: STOP TTS IMMEDIATELY and process input.
                print(f"[ACTION] VALID INTERRUPTION: '{transcription}'. Stopping TTS.")
                
                # Force the TTS pipeline to stop its current output
                self.tts.stop_output() 
                self.on_tts_interrupted() # Update state
                
                self.process_user_input(transcription)

        else:
            # SCENARIO 3: Agent is quiet. All speech (including fillers) is registered.
            # ACTION: REGISTER as valid speech to initiate the next turn.
            print(f"[ACTION] REGISTERED INPUT: '{transcription}'. Agent is quiet.")
            self.process_user_input(transcription)

    # Placeholder for your main dialogue function
    def process_user_input(self, text):
        # Your logic to get a response from an LLM/DM
        # ...
        
        # Then, when you get the response:
        # self.on_tts_start()
        # self.tts.play_audio(response_audio)
        # self.on_tts_complete() # Called once audio finishes
        pass

    # Placeholder for LiveKit boilerplate setup
    def setup_asr(self):
        # ... setup ASR component ...
        pass
        
    def setup_tts(self):
        # ... setup TTS component, ensuring it calls on_tts_start/complete ...
        pass
