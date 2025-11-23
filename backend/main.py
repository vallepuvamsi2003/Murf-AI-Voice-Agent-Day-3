from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import json
import os
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_FILE = "wellness_log.json"

# --- Data Models ---
class SessionState(BaseModel):
    step: int = 0  # 0=Start, 1=Mood Done, 2=Goals Done, 3=Complete
    mood: Optional[str] = None
    goals: List[str] = []
    summary_text: Optional[str] = None

class ChatRequest(BaseModel):
    user_input: str
    current_state: SessionState

class ChatResponse(BaseModel):
    agent_response: str
    updated_state: SessionState
    is_complete: bool

# --- Helper Functions ---

def load_history():
    """Reads the JSON log to find previous entries."""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_entry(entry):
    """Appends a new entry to the JSON log."""
    history = load_history()
    history.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(history, f, indent=4)

def get_contextual_greeting():
    """Generates a greeting based on the last session."""
    history = load_history()
    if not history:
        return "Hello! I'm your wellness companion. I'm here to check in on you. How is your mood and energy feeling today?"
    
    last = history[-1]
    last_date = last.get("date", "recently")
    last_mood = last.get("mood", "okay")
    
    return (f"Welcome back. Last time we spoke on {last_date}, you mentioned feeling {last_mood}. "
            "How are you feeling today? Any stress or low energy?")

# --- Main Logic Endpoint ---

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    state = request.current_state
    text = request.user_input
    response_text = ""
    
    # Step 0: Initial Greeting (The frontend calls this immediately on load)
    if state.step == 0:
        response_text = get_contextual_greeting()
        state.step = 1 # Move to waiting for Mood
        return ChatResponse(agent_response=response_text, updated_state=state, is_complete=False)

    # Step 1: User just answered "Mood" -> Ask for "Goals"
    if state.step == 1:
        # Capture mood (In a real app, use LLM to extract sentiment. Here we take the full text)
        state.mood = text
        
        response_text = ("Thank you for sharing that. Remember, I'm just a companion, not a doctor, "
                         "but I'm here to listen. \n\n"
                         "Now, looking ahead, what are 1 to 3 small, realistic things you'd like to accomplish today?")
        state.step = 2 # Move to waiting for Goals
        return ChatResponse(agent_response=response_text, updated_state=state, is_complete=False)

    # Step 2: User just answered "Goals" -> Generate Advice & Recap
    if state.step == 2:
        # Capture goals (Split by 'and' or commas for basic list making)
        raw_goals = text.replace(" and ", ",").split(",")
        state.goals = [g.strip() for g in raw_goals if g.strip()]
        
        # Generate simple grounded advice
        advice = "Remember to take short breaks between these tasks."
        if "tired" in state.mood.lower() or "low" in state.mood.lower():
            advice = "Since energy is low, maybe pick just the most important one and rest."
        
        state.summary_text = (f"Let's recap: You're feeling '{state.mood}'. "
                              f"Your main focus is: {', '.join(state.goals)}. "
                              f"{advice} Does this sound right?")
        
        response_text = state.summary_text
        state.step = 3 # Move to waiting for Confirmation
        return ChatResponse(agent_response=response_text, updated_state=state, is_complete=False)

    # Step 3: User confirmed -> Save and Finish
    if state.step == 3:
        if "no" in text.lower() or "wrong" in text.lower():
            # Simple retry loop
            state.step = 1
            response_text = "Oh, I apologize. Let's try again. How are you feeling right now?"
            return ChatResponse(agent_response=response_text, updated_state=state, is_complete=False)
        
        # Save to JSON
        entry = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "mood": state.mood,
            "goals": state.goals,
            "summary": state.summary_text
        }
        save_entry(entry)
        
        response_text = "Great. I've logged that for you. Have a mindful day!"
        return ChatResponse(agent_response=response_text, updated_state=state, is_complete=True)

    return ChatResponse(agent_response="I'm not sure where we are.", updated_state=state, is_complete=False)