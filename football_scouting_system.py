import os
import sys
import json
import shutil
import datetime
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Ensure Google API Key is available for Agents
if not os.getenv("GOOGLE_API_KEY"):
    print("ERROR: GOOGLE_API_KEY not found in environment or .env file.")
    # We will strictly exit if key is missing, as agents are core to recommendation
    # But for registration mode, it might not be strictly necessary? 
    # The prompt implies the system is one whole.
    # We'll allow it to run but Agent creation might fail later if not checked there.
    pass

# --- Constants & Configuration ---
PLAYER_DB_FILE = "player_database.json"
UPLOAD_DIR_PROFILE = "uploads/profile_photos"
UPLOAD_DIR_MATCH = "uploads/match_photos"

VALID_TACTICAL_COMBOS = {
    "Goalkeeper": ["Sweeper", "Shot Stopper", "Ball Playing"],
    "Defender": ["Defensive", "Build-up", "Aggressive"],
    "Midfielder": ["Possession", "Creative", "Box-to-Box"],
    "Forward": ["Attacking", "Counter", "Clinical"]
}

# --- Utils ---

def setup_directories():
    os.makedirs(UPLOAD_DIR_PROFILE, exist_ok=True)
    os.makedirs(UPLOAD_DIR_MATCH, exist_ok=True)

def load_player_database():
    if not os.path.exists(PLAYER_DB_FILE):
        return []
    try:
        with open(PLAYER_DB_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_player_database(data):
    with open(PLAYER_DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def validate_email(email, db):
    if not email:
        return False, "Email cannot be empty."
    if "@" not in email or "." not in email:
        return False, "Invalid email format (must contain '@' and '.')."
    
    # Check uniqueness
    for player in db:
        if player.get("email") == email:
            return False, "Email already registered."
    
    return True, ""

def validate_tactical_combo(position, style):
    # Case insensitive matching
    valid_styles = []
    
    # Find matching position key (case-insensitive)
    for pos_key, styles in VALID_TACTICAL_COMBOS.items():
        if pos_key.lower() == position.lower():
            valid_styles = [s.lower() for s in styles]
            break
            
    if not valid_styles:
        # Assuming position was already validated or is free-text, but prompt implies strict valid inputs
        # If position is invalid, we can't really validate style against it, but let's assume valid position input first.
        return False 

    return style.lower() in valid_styles

def handle_photo_upload(prompt_text, target_dir, player_name):
    while True:
        file_path = input(f"{prompt_text}: ").strip()
        # Remove quotes if user copied path as "path"
        file_path = file_path.strip('"').strip("'")
        
        if not os.path.exists(file_path):
            print("Invalid file. Please upload a valid image file.")
            continue
            
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png']:
            print("Invalid file. Please upload a valid image file.")
            continue
            
        # Valid file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{player_name}_{os.path.basename(target_dir)}_{timestamp}{ext}".replace(" ", "_")
        target_path = os.path.join(target_dir, new_filename)
        
        try:
            shutil.copy(file_path, target_path)
            return target_path
        except Exception as e:
            print(f"Error saving file: {e}")
            return None

# --- ADK Integration ---
try:
    from google.adk.agents.llm_agent import Agent
    from google.adk.tools import google_search
    from google.adk.runners import Runner
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
    from google.genai import types
except ImportError:
    print("Error: google.adk modules not found.")
    sys.exit(1)

# --- Instructions ---

DATA_RETRIEVAL_INSTRUCTIONS_PLAYER = """
You are a Data Retrieval Agent for football scouting.
Your goal is to find detailed, real-time data about football players based on strict user requirements.

RULES:
1. Filter players ONLY within the given AGE and EXPERIENCE range.
2. For GOALKEEPERS, find: Matches, Clean Sheets, Saves, Save %.
3. For DEFENDERS, find: Matches, Tackles, Interceptions, Clearances, Duels Won %.
4. For MIDFIELDERS, find: Matches, Goals, Assists, Key Passes, Pass Accuracy %.
5. For FORWARDS, find: Matches, Goals, Assists, Shots on Target, Conversion Rate.
6. Use google_search to find actual 2024/2025 season data.
7. Return exactly 10 candidates if possible.
8. RETURN ONLY RAW JSON. Format: [{"name": "...", "age": 25, "experience": 4, "current_club": "...", "matches_played": 20, "stats": {...}, "key_strength": "..."}]
"""

SCORING_INSTRUCTIONS_PLAYER = """
You are a Scoring Agent, acting as a Professional Head Coach & Scout.
Assign a Scout Score (0-100) based on:
1. Position relevance
2. Tactical fit
3. Performance consistency
4. Long-term potential

Output JSON ONLY: [{"name": "...", "scout_score": 85, "coach_justification": "...", "performance_analysis": "..."}]
"""

RANKING_INSTRUCTIONS_PLAYER = """
You are a Ranking & Recommendation Agent.
Select the Top 5 candidates.
OUTPUT FORMAT: Strict JSON list of the top 5 candidates with all details.
"""

DATA_RETRIEVAL_INSTRUCTIONS_COACH = """
You are a Data Retrieval Agent for football technical directors.
Find head coach candidates matching requirements.
RULES:
1. Find estimated SALARY/CONTRACT.
2. Focus on Tactical Identity, Win %, Trophies.
3. RETURN ONLY RAW JSON. Format: [{"name": "...", "age": 45, "experience": 10, "current_club": "...", "estimated_salary": "...", "tactical_style": "...", "achievements": "..."}]
"""

SCORING_INSTRUCTIONS_COACH = """
You are a Technical Director evaluating Head Coaches.
Score (0-100) based on:
1. Tactical Match
2. Strategic Value
3. Financial Fit

Output JSON ONLY with score and analysis.
"""

# --- Helper Functions ---

def run_agent(agent, prompt):
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=f"football_app_{agent.name}",
        session_service=session_service,
        auto_create_session=True
    )
    
    events = runner.run(
        user_id="user",
        session_id="session",
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)])
    )
    
    full_response = []
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    full_response.append(part.text)
    
    return "".join(full_response)

def parse_json_response(response_text):
    # Extract JSON code block if present
    match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = response_text
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to find list start/end
        try:
            start = json_str.find('[')
            end = json_str.rfind(']') + 1
            if start != -1 and end != -1:
                return json.loads(json_str[start:end])
        except:
            pass
        return []

def filter_players_strict(candidates, age_req, exp_req):
    filtered = []
    # Parse range requirements
    # Example: "20-25" -> 20, 25
    try:
        age_min, age_max = map(int, age_req.split('-'))
    except ValueError:
        age_min, age_max = 0, 99
        
    try:
        exp_min, exp_max = map(int, exp_req.split('-'))
    except ValueError:
        exp_min, exp_max = 0, 99

    for c in candidates:
        age = c.get('age', 0)
        # Experience might be string "5 years", try to parse
        exp_raw = c.get('experience', 0)
        if isinstance(exp_raw, str):
            exp_match = re.search(r'\d+', exp_raw)
            exp = int(exp_match.group()) if exp_match else 0
        else:
            exp = exp_raw

        if age_min <= age <= age_max and exp_min <= exp <= exp_max:
            filtered.append(c)
            
    return filtered

def filter_coaches_strict(candidates, exp_req, budget_req):
    filtered = []
    try:
        exp_min, exp_max = map(int, exp_req.split('-'))
    except ValueError:
        exp_min, exp_max = 0, 99

    # Budget parsing is tricky, usually handled by Agent or exact match.
    # We will rely on agent for strict budget, but check experience here.
    
    for c in candidates:
        # Experience check
        exp_raw = c.get('experience', 0)
        if isinstance(exp_raw, str):
            exp_match = re.search(r'\d+', exp_raw)
            exp = int(exp_match.group()) if exp_match else 0
        else:
            exp = exp_raw
            
        if exp_min <= exp <= exp_max:
            filtered.append(c)
            
    return filtered

# --- Application Modes ---

def mode_new_player_registration():
    db = load_player_database()
    
    print("\n--- NEW PLAYER REGISTRATION ---\n")
    
    name = input("Enter Player Name: ").strip()
    
    while True:
        email = input("Enter Email Address: ").strip()
        is_valid, msg = validate_email(email, db)
        if is_valid:
            break
        print(f"Invalid email format or already registered.")

    age = input("Enter Age: ").strip()
    position = input("Enter Position: ").strip()
    style = input("Enter Playing Style: ").strip()
    matches_played = input("Enter Matches Played: ").strip()
    experience = input("Enter Experience (in years): ").strip()
    key_strength = input("Enter Key Strength: ").strip()
    
    club_name = ""
    club_address = ""
    in_club = input("Is the player currently in a club? (yes/no): ").strip().lower()
    if in_club == 'yes':
        club_name = input("Enter Current Club Name: ").strip()
        club_address = input("Enter Club Address: ").strip()
    
    setup_directories()
    
    print("\n[PHOTO UPLOAD]")
    profile_photo_path = handle_photo_upload("Enter Player Profile Photo file path (.jpg/.jpeg/.png)", UPLOAD_DIR_PROFILE, name)
    match_photo_path = handle_photo_upload("Enter Match Action Photo file path (.jpg/.jpeg/.png)", UPLOAD_DIR_MATCH, name)
    
    new_id = len(db) + 1
    
    player_record = {
        "player_id": new_id,
        "name": name,
        "email": email,
        "age": age,
        "position": position,
        "playing_style": style,
        "matches_played": matches_played,
        "experience": experience,
        "key_strength": key_strength,
        "current_club": club_name if in_club == 'yes' else "Free Agent",
        "club_address": club_address if in_club == 'yes' else "N/A",
        "profile_photo_path": profile_photo_path,
        "match_photo_path": match_photo_path,
        "registration_timestamp": datetime.datetime.now().isoformat()
    }
    
    db.append(player_record)
    save_player_database(db)
    
    print("\n========================================")
    print("NEW PLAYER REGISTERED SUCCESSFULLY")
    print("========================================\n")

def mode_player_recommendation():
    print("\n--- PLAYER RECOMMENDATION MODE ---")
    
    position = input("Playing position: ").strip()
    age_range = input("Age range (example: 20-25): ").strip()
    exp_range = input("Experience range (example: 3-5): ").strip()
    
    while True:
        style = input("Playing style: ").strip()
        if validate_tactical_combo(position, style):
            break
        print("\n========================================")
        print("INVALID TACTICAL COMBINATION")
        print("========================================")
        print("Selected playing style does not match chosen position.")
        print("Please enter a compatible style.\n")
        
    print("\n========================================")
    print("PLAYER REQUIREMENTS")
    print("========================================")
    print(f"Position       : {position}")
    print(f"Age Range      : {age_range}")
    print(f"Experience     : {exp_range}")
    print(f"Playing Style  : {style}")
    print("========================================\n")
    
    # 1. Data Retrieval
    data_agent = Agent(model='gemini-2.5-flash', name='data_agent', instruction=DATA_RETRIEVAL_INSTRUCTIONS_PLAYER, tools=[google_search])
    search_prompt = f"Find 10 active football players who are {position}s, aged {age_range}, with {exp_range} years experience, playing style: {style}. Return strict JSON."
    print("Retrieving candidates...")
    candidates_json = run_agent(data_agent, search_prompt)
    candidates = parse_json_response(candidates_json)
    
    # 2. Strict Filtering
    filtered_candidates = filter_players_strict(candidates, age_range, exp_range)
    
    # 3. Operations on Valid Candidates
    final_output = []
    
    if filtered_candidates:
        # Scoring
        scoring_agent = Agent(model='gemini-2.5-flash', name='scoring_agent', instruction=SCORING_INSTRUCTIONS_PLAYER)
        score_prompt = f"Score these candidates: {json.dumps(filtered_candidates)}"
        scored_json = run_agent(scoring_agent, score_prompt)
        scored_candidates = parse_json_response(scored_json)
        
        # Ranking (or just sorting by score)
        scored_candidates.sort(key=lambda x: x.get('scout_score', 0), reverse=True)
        top_5 = scored_candidates[:5]
        
        print("\n========================================")
        print("FINAL PLAYER RECOMMENDATIONS")
        print("========================================")
        
        for i, p in enumerate(top_5, 1):
            print(f"\nRank #{i}")
            print(f"Player Name      : {p.get('name')}")
            print(f"Scout Score      : {p.get('scout_score')}/100")
            print(f"Current Club     : {p.get('current_club', 'N/A')}")
            print(f"Matches Played   : {p.get('matches_played', 'N/A')}")
            print(f"Role-Specific Performance : {p.get('role_performance', 'N/A')}") # Agent needs to populate this
            print(f"Key Strength     : {p.get('key_strength', 'N/A')}")
            print(f"\n📊 PERFORMANCE ANALYSIS:\n{p.get('performance_analysis', 'N/A')}")
            print(f"\n🧠 COACH JUSTIFICATION:\n{p.get('coach_justification', 'N/A')}")
            print("\n----------------------------------------")
    else:
        print("No candidates found matching strict criteria.")

    # 4. Registered Player Matches
    print("\n========================================")
    print("REGISTERED PLAYER MATCHES")
    print("========================================")
    
    db = load_player_database()
    matches = []
    
    # Simple strict matching for DB
    try:
        age_min, age_max = map(int, age_range.split('-'))
    except: age_min, age_max = 0, 99
    
    for p in db:
        p_age = int(p.get('age', 0))
        p_pos = p.get('position', '').lower()
        if age_min <= p_age <= age_max and p_pos == position.lower():
            matches.append(p)
            
    if matches:
        for p in matches:
            print(f"\n[Registered Player]")
            print(f"Player Name : {p.get('name')}")
            print(f"Age         : {p.get('age')}")
            print(f"Position    : {p.get('position')}")
            print(f"Style       : {p.get('playing_style')}")
            print(f"Club        : {p.get('current_club')}")
            print("----------------------------------------")
    else:
        print("No registered players match the criteria.")

def mode_coach_recommendation():
    print("\n--- COACH RECOMMENDATION MODE ---")
    
    formation = input("Preferred Formation (example: 4-3-3): ").strip()
    exp_range = input("Coaching Experience Range (example: 5-10): ").strip()
    philosophy = input("Tactical Philosophy (Attacking / Defensive / Possession): ").strip()
    level = input("Team Level (Youth / Professional / Elite): ").strip()
    budget = input("Available Budget: ").strip()
    
    print("\n========================================")
    print("COACH REQUIREMENTS")
    print("========================================")
    print(f"Formation            : {formation}")
    print(f"Experience Range     : {exp_range}")
    print(f"Tactical Philosophy  : {philosophy}")
    print(f"Team Level           : {level}")
    print(f"Available Budget     : {budget}")
    print("========================================\n")

    # 1. Data Retrieval
    data_agent = Agent(model='gemini-2.5-flash', name='data_agent', instruction=DATA_RETRIEVAL_INSTRUCTIONS_COACH, tools=[google_search])
    search_prompt = f"Find football coaches with {exp_range} years experience, style: {philosophy}, formation: {formation}. Budget around {budget}. Return strict JSON."
    print("Retrieving candidates...")
    candidates_json = run_agent(data_agent, search_prompt)
    candidates = parse_json_response(candidates_json)
    
    # 2. Strict Filtering
    filtered_candidates = filter_coaches_strict(candidates, exp_range, budget)
    
    # 3. Scoring & Output
    if filtered_candidates:
        scoring_agent = Agent(model='gemini-2.5-flash', name='scoring_agent', instruction=SCORING_INSTRUCTIONS_COACH)
        score_prompt = f"Score these coaches: {json.dumps(filtered_candidates)}"
        scored_json = run_agent(scoring_agent, score_prompt)
        scored_candidates = parse_json_response(scored_json)
        
        scored_candidates.sort(key=lambda x: x.get('scout_score', 0), reverse=True)
        top_5 = scored_candidates[:5]
        
        print("\n========================================")
        print("FINAL COACH RECOMMENDATIONS")
        print("========================================")
        
        for i, c in enumerate(top_5, 1):
            print(f"\nRank #{i}")
            print(f"Coach Name     : {c.get('name')}")
            print(f"Scout Score    : {c.get('scout_score')}/100")
            print(f"Current Club   : {c.get('current_club', 'N/A')}")
            print(f"Years of Exp   : {c.get('experience', 'N/A')}")
            print(f"Pref Formation : {c.get('formation', 'N/A')}")
            print(f"Est Salary     : {c.get('estimated_salary', 'N/A')}")
            print(f"Key Strength   : {c.get('key_strength', 'N/A')}")
            print(f"\n📊 TACTICAL ANALYSIS:\n{c.get('tactical_analysis', 'N/A')}")
            print(f"\n🧠 HEAD SCOUT JUSTIFICATION:\n{c.get('justification', 'N/A')}")
            print("\n----------------------------------------")
    else:
        print("No candidates found matching strict criteria.")

def main():
    while True:
        print("────────────────────────────────────────")
        print("STEP 1: ROLE SELECTION")
        print("────────────────────────────────────────")
        choice = input("Do you need a PLAYER, a COACH, or NEW PLAYER registration? (player/coach/new player): ").strip().lower()
        
        if choice == 'new player':
            mode_new_player_registration()
        elif choice == 'player':
            mode_player_recommendation()
        elif choice == 'coach':
            mode_coach_recommendation()
        else:
            print("Invalid selection. Please try again.")

if __name__ == "__main__":
    setup_directories()
    main()
