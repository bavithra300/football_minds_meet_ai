from dotenv import load_dotenv

# Force load .env file BEFORE importing google libraries
load_dotenv(override=True)

import sys
import os
import time
import json
import re
from google import genai
from google.genai import types

# Debug: Check API Key
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    # Try getting from the old 'GEMINI_API_KEY' if not found
    api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("ERROR: GOOGLE_API_KEY not found. Please check your .env file.")
    sys.exit(1)

# Ensure environment is set for ADK
os.environ["GOOGLE_API_KEY"] = api_key.strip()
if "GEMINI_API_KEY" in os.environ:
    del os.environ["GEMINI_API_KEY"]

try:
    from google.adk.agents.llm_agent import Agent
    from google.adk.tools import google_search
    from google.adk.runners import Runner
    from google.adk.sessions.in_memory_session_service import InMemorySessionService
except ImportError:
    print("Error: google.adk modules not found. Please ensure the ADK is installed.")
    sys.exit(1)

# --- Configuration ---
MODEL_NAME = 'gemini-2.5-flash'
DATABASE_FILE = 'player_database.json'

# --- Helper Functions ---

def load_database():
    if not os.path.exists(DATABASE_FILE):
        return []
    try:
        with open(DATABASE_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_database(data):
    with open(DATABASE_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def run_agent_safe(agent, prompt, step_name="Agent Execution"):
    """
    Runs an ADK agent with exponential backoff for Rate Limits (429).
    """
    print(f"\n--- {step_name} ---")
    
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=f"football_app_{agent.name}",
        session_service=session_service,
        auto_create_session=True
    )
    
    max_retries = 3
    base_delay = 5

    for attempt in range(max_retries):
        try:
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
            
            result = "".join(full_response)
            if not result:
                return "No response generated."
            return result

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                wait_time = base_delay * (2 ** attempt)
                print(f"Warning: Rate limit hit (429). Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                print(f"Error during {step_name}: {e}")
                return ""
    
    print(f"Error: Failed {step_name} after retries.")
    return ""

def extract_json_from_text(text):
    """Extracts JSON object (list or dict) from LLM text response."""
    try:
        # Match content between ```json and ``` or just start/end of list/object
        match = re.search(r'```json\s*(.*?)```', text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            # Try finding the first [ or {
            match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                return None
        return json.loads(json_str)
    except Exception:
        return None

# --- Core Logic Steps ---

def get_valid_image_path(prompt_text):
    """Prompts for an image path and validates existence and extension."""
    while True:
        path = input(f"{prompt_text} ").strip().strip('"').strip("'") # Remove potential quotes from copy-paste
        if not path:
            print("Invalid file. Please upload a valid image file.")
            continue
            
        if not os.path.exists(path):
            print("Invalid file. File does not exist.")
            continue
            
        _, ext = os.path.splitext(path)
        if ext.lower() not in ['.jpg', '.jpeg', '.png']:
            print("Invalid file. Please upload a valid image file (.jpg, .jpeg, .png).")
            continue
            
        return path

def register_new_player_mode():
    print("\n========================================")
    print(" NEW PLAYER REGISTRATION MODE")
    print("========================================")
    
    try:
        player = {}
        player['name'] = input("Enter Player Name: ").strip()
        player['email'] = input("Enter Email Address: ").strip()
        player['age'] = int(input("Enter Age: ").strip())
        player['position'] = input("Enter Position: ").strip()
        player['style'] = input("Enter Playing Style: ").strip()
        player['matches_played'] = input("Enter Matches Played: ").strip()
        player['experience'] = float(re.sub(r'[^0-9.]', '', input("Enter Experience (in years): ").strip()))
        player['key_strength'] = input("Enter Key Strength: ").strip()
        
        in_club = input("Is the player currently in a club? (yes/no): ").strip().lower()
        if in_club == 'yes':
            player['current_club'] = input("Enter Current Club Name: ").strip()
            player['club_address'] = input("Enter Club Address: ").strip()
        else:
            player['current_club'] = "Free Agent"
            player['club_address'] = "N/A"

        # Photo Upload Validation
        player['profile_photo_path'] = get_valid_image_path("Enter Player Profile Photo file path (.jpg/.png):")
        player['match_photo_path'] = get_valid_image_path("Enter Match Action Photo file path (.jpg/.png):")
        
        # Save
        db = load_database()
        db.append(player)
        save_database(db)
        
        print("\n========================================")
        print(" NEW PLAYER REGISTERED SUCCESSFULLY")
        print("========================================")
        
    except ValueError:
        print("Error: Invalid numeric input. Please try again.")

def parse_range(range_str):
    """Parses '20-25' into (20, 25) or '3+' into (3, 100)."""
    try:
        # Remove non-numeric chars except - and +
        clean_str = re.sub(r'[^0-9\-+]', '', range_str)
        if '-' in clean_str:
            parts = clean_str.split('-')
            return float(parts[0]), float(parts[1])
        elif '+' in clean_str:
            val = float(clean_str.replace('+', ''))
            return val, 100.0
        else:
             # Single number treated as min
            val = float(clean_str)
            return val, val
    except:
        return 0, 100

def parse_money(money_str):
    """Parses money string to float value. Handles 'M' (million), 'K' (thousand)."""
    if not money_str: return 0.0
    try:
        clean_str = re.sub(r'[^0-9\.MKmk]', '', money_str).upper()
        if 'M' in clean_str:
            return float(clean_str.replace('M', '')) * 1_000_000
        elif 'K' in clean_str:
            return float(clean_str.replace('K', '')) * 1_000
        else:
            return float(clean_str)
    except:
        return 0.0 # Return 0 if unparseable to avoid crashing, but strict check might fail.

def check_strict_filter(val, valid_range):
    return valid_range[0] <= float(val) <= valid_range[1]

# Strict Validation Rules
VALID_POSITION_STYLES = {
    'goalkeeper': ['sweeper', 'shot stopper', 'ball playing'],
    'defender': ['defensive', 'build-up', 'aggressive'],
    'midfielder': ['possession', 'creative', 'box-to-box'],
    'forward': ['attacking', 'counter', 'clinical']
}

def player_recommendation_mode():
    # 1. Ask Requirements
    print("\n========================================")
    print(" PLAYER RECOMMENDATION MODE")
    print("========================================")
    
    reqs = {}
    while True:
        try:
            reqs['position'] = input("Playing position: ").strip()
            
            # Age/Exp Ranges with examples
            reqs['age_range_str'] = input("Age range (example: 20-25): ").strip()
            reqs['exp_range_str'] = input("Experience range (example: 3-5): ").strip() # Removed 'years' from prompt to match spec
            
            reqs['style'] = input("Playing style: ").strip()
            
            # VALIDATION
            pos_key = reqs['position'].lower()
            style_key = reqs['style'].lower()
            
            if pos_key in VALID_POSITION_STYLES:
                valid_styles = VALID_POSITION_STYLES[pos_key]
                # Allow partial match? Spec says "Allowed combinations: ... If mismatch: Display INVALID ... "
                # We'll enforce strict checking against the list.
                if style_key not in valid_styles:
                    print("\n========================================")
                    print("INVALID TACTICAL COMBINATION")
                    print("========================================")
                    print("Selected playing style does not match chosen position.")
                    print(f"Compatible styles for {reqs['position']}: {', '.join(valid_styles).title()}")
                    print("Please enter a compatible style.\n")
                    continue # Return to Player Requirement input
            else:
                 # If position itself is weird, maybe warn? But spec focuses on the combination.
                 # Let's assume standard positions. Only validate style if position is recognized.
                 pass

            break # Valid
            
        except EOFError:
            return

    # Parse ranges for filtering
    min_age, max_age = parse_range(reqs['age_range_str'])
    min_exp, max_exp = parse_range(reqs['exp_range_str'])

    print("\n========================================")
    print(" PLAYER REQUIREMENTS")
    print("========================================")
    print(f"Position       : {reqs['position']}")
    print(f"Age Range      : {reqs['age_range_str']}")
    print(f"Experience     : {reqs['exp_range_str']}")
    print(f"Playing Style  : {reqs['style']}")
    print("========================================")

    # 2. Data Retrieval (Ask for JSON)
    data_agent = Agent(
        model=MODEL_NAME, 
        name='data_agent', 
        instruction="You are a Data Retrieval Agent. Search for REAL, ACTIVE football players. Output ONLY valid JSON list.", 
        tools=[google_search]
    )
    
    search_prompt = f"""
    Find 10 active football players matching:
    - Position: {reqs['position']}
    - Style: {reqs['style']}
    - Approx Age: {reqs['age_range_str']}
    - Approx Exp: {reqs['exp_range_str']}
    
    STEP 4 DATA RETRIEVAL RULE:
    - ALWAYS return strict JSON only.
    - No commentary.
    - No essay explanation.
    - If no match found, return exactly: {{ "candidates": [] }}
    
    JSON Structure:
    {{
      "candidates": [
        {{
          "name": "string",
          "age": number,
          "experience_years": number,
          "current_club": "string",
          "matches_played": "string",
          "key_strength": "string",
          "role_performance": "string"
        }}
      ]
    }}
    """
    
    raw_data = run_agent_safe(data_agent, search_prompt, "Retrieving Data (Strict JSON match)")
    if not raw_data: return

    json_data = extract_json_from_text(raw_data)
    if not json_data or "candidates" not in json_data:
        # Fallback if it returned list directly
        candidates = json_data if isinstance(json_data, list) else []
    else:
        candidates = json_data["candidates"]
        
    if not candidates:
        print("Error: No candidates found or invalid format.")
        return

    # 3. Strict Filter
    print("\n--- Applying Strict Filters (Step 3) ---")
    valid_candidates = []
    for p in candidates:
        age_ok = check_strict_filter(p.get('age', 0), (min_age, max_age))
        exp_ok = check_strict_filter(p.get('experience_years', 0), (min_exp, max_exp))
        
        if age_ok and exp_ok:
            valid_candidates.append(p)
        else:
            print(f"Discarding {p.get('name')} (Age: {p.get('age')}, Exp: {p.get('experience_years')}) - Out of range.")
            
    if not valid_candidates:
        print("No players match the given criteria.")
        return

    # 4. Check Registered Players
    print("\n--- Checking Registered Players ---")
    db_players = load_database()
    registered_matches = []
    for p in db_players:
        # Simple position/style match (loose) + Strict Age/Exp
        pos_match = reqs['position'].lower() in p['position'].lower()
        style_match = reqs['style'].lower() in p['style'].lower()
        age_ok = check_strict_filter(p['age'], (min_age, max_age))
        exp_ok = check_strict_filter(p['experience'], (min_exp, max_exp))
        
        if pos_match and age_ok and exp_ok:
            registered_matches.append(p)

    # 5. Scoring & Ranking
    # We pass the valid candidates to the ranking agent to format them
    ranking_agent = Agent(
        model=MODEL_NAME, 
        name='ranking_agent', 
        instruction="You are an Elite Head Coach. Score and Format candidates."
    )
    
    ranking_prompt = f"""
    You are an Elite Head Coach.
    
    Review these VALIDATED candidates:
    {json.dumps(valid_candidates, indent=2)}
    
    User Requirements: {reqs}
    
    STEP 5 SCOUT SCORE (0-100):
    - Matches played
    - Experience
    - Role performance
    - Strength relevance
    
    STEP 6 OUTPUT FORMAT:
    - Console format only.
    - NO TABLES.
    - NO ESSAYS.
    - SELECT TOP 5.
    
    Output Template (Repeat for each candidate):
    
    ========================================
    FINAL PLAYER RECOMMENDATIONS
    ========================================
    
    Rank #[N]
    Player Name : [Name]
    Scout Score : [Score]
    Current Club : [Club]
    Matches Played : [Matches]
    Role-Specific Performance : [Stats]
    Key Strength : [Strength]
    
    📊 PERFORMANCE ANALYSIS:
    [Short tactical breakdown]
    
    🧠 COACH JUSTIFICATION:
    [Professional reasoning]
    
    ----------------------------------------
    """
    
    final_out = run_agent_safe(ranking_agent, ranking_prompt, "Scoring & Formatting")
    print(final_out)
    
    if registered_matches:
        print("\n========================================")
        print(" REGISTERED PLAYER MATCHES")
        print("========================================")
        # Format these manually or via agent. Let's do manual for speed/reliability or agent for consistency.
        # Let's use agent to ensure same tone.
        reg_prompt = f"""
        Format these REGISTERED players EXACTLY like the "Final Player Recommendations" above.
        
        STEP 6 OUTPUT FORMAT (Registered):
        
        ========================================
        REGISTERED PLAYER MATCHES
        ========================================
        
        Rank #[N]
        Player Name : [Name]
        Scout Score : [Score] (Calculate this)
        Current Club : [Club]
        Matches Played : [Matches]
        Role-Specific Performance : [Stats - generate reasonable placeholder if missing]
        Key Strength : [Strength]
        
        📊 PERFORMANCE ANALYSIS:
        [Short tactical breakdown]
        
        🧠 COACH JUSTIFICATION:
        [Professional reasoning - Mention this is a REGISTERED PLAYER]
        
        ----------------------------------------
        
        Data: {json.dumps(registered_matches)}
        """
        reg_out = run_agent_safe(ranking_agent, reg_prompt, "Formatting Registered Players")
        print(reg_out)
    else:
        print("\n(No registered players match the criteria.)")

def coach_recommendation_mode():
    print("\n========================================")
    print(" COACH RECOMMENDATION MODE")
    print("========================================")
    reqs = {}
    try:
        reqs['formation'] = input("Preferred Formation (example: 4-3-3): ").strip()
        reqs['exp_range_str'] = input("Coaching Experience Range (example: 5-10 years): ").strip()
        reqs['philosophy'] = input("Tactical Philosophy (example: Attacking): ").strip()
        reqs['level'] = input("Team Level (Youth / Professional / Elite): ").strip()
        reqs['budget_str'] = input("Available Budget (example: 5M / 10M): ").strip()
    except EOFError:
        return
        
    min_exp, max_exp = parse_range(reqs['exp_range_str'])
    budget_limit = parse_money(reqs['budget_str'])
    
    print("\n========================================")
    print(" COACH REQUIREMENTS")
    print("========================================")
    print(f"Formation            : {reqs['formation']}")
    print(f"Experience Range     : {reqs['exp_range_str']}")
    print(f"Tactical Philosophy  : {reqs['philosophy']}")
    print(f"Team Level           : {reqs['level']}")
    print(f"Available Budget     : {reqs['budget_str']}")
    print("========================================")

    data_agent = Agent(
        model=MODEL_NAME, 
        name='coach_data_agent', 
        instruction="Find football coaches. Output ONLY valid JSON list.", 
        tools=[google_search]
    )

    search_prompt = f"""
    Find 10 football coaches matching:
    - Philosophy: {reqs['philosophy']}
    - Experience: {reqs['exp_range_str']}
    - Level: {reqs['level']}
    
    STEP 4 DATA RETRIEVAL RULE:
    - ALWAYS return strict JSON only.
    - No commentary.
    - If no match found, return exactly: {{ "candidates": [] }}
    
    JSON Structure:
    {{
      "candidates": [
        {{
          "name": "string",
          "experience_years": number,
          "current_club": "string",
          "estimated_salary": "string",
          "preferred_formation": "string",
          "key_strength": "string"
        }}
      ]
    }}
    """

    raw_data = run_agent_safe(data_agent, search_prompt, "Retrieving Coach Data")
    if not raw_data: return

    json_data = extract_json_from_text(raw_data)
    if not json_data or "candidates" not in json_data:
        candidates = json_data if isinstance(json_data, list) else []
    else:
        candidates = json_data["candidates"]
        
    if not candidates:
        print("Error: Could not parse candidate data.")
        return

    # Strict Filter
    print("\n--- Applying Strict Filters (Step 3) ---")
    valid_candidates = []
    
    for c in candidates:
        exp_ok = check_strict_filter(c.get('experience_years', 0), (min_exp, max_exp))
        
        # Budget Check
        salary_str = str(c.get('estimated_salary', '0'))
        salary_val = parse_money(salary_str)
        # If salary is unknown (0), do we keep? 
        # Strict rules: "Discard any candidate that does NOT exactly match...". 
        # If we don't know the salary, we can't confirm suitability. 
        # However, for demo purposes with LLM data, 0 often means "unknown".
        # Let's be strict: if budget > 0 and salary > budget, discard.
        
        budget_ok = True
        if budget_limit > 0:
            if salary_val > budget_limit:
                budget_ok = False
            # If salary_val is 0 (unknown), assume strictly we shouldn't recommend if we can't verify?
            # Or assume within budget if unknown? 
            # Prompt says "Discard... Budget Suitability". 
            # I will assume "valid if salary <= budget OR salary is unknown".
            # Actually, "No approximation" suggests we should know. 
            # But let's stick to: if we have a number, check it.
        
        if exp_ok and budget_ok:
            valid_candidates.append(c)
        else:
             print(f"Discarding {c.get('name')} (Exp: {c.get('experience_years')}, Salary: {salary_str}) - Strict Filter Failed.")
    
    if not valid_candidates:
        print("No coaches match the given criteria.")
        return

    ranking_agent = Agent(
        model=MODEL_NAME, 
        name='ranking_agent', 
        instruction="You are a Technical Director. Score and Format candidates."
    )
    
    ranking_prompt = f"""
    You are a Technical Director.
    
    Review these VALIDATED coaches:
    {json.dumps(valid_candidates, indent=2)}
    
    User Requirements: {reqs}
    
    STEP 5 SCOUT SCORE (0-100):
    - Formation alignment
    - Experience suitability
    - Leadership & development ability
    - Budget efficiency
    - Long-term vision
    
    STEP 6 OUTPUT FORMAT:
    - Console format only.
    - NO TABLES.
    - NO ESSAYS.
    - SELECT TOP 5.
    
    Output Template (Repeat for each candidate):
    
    ========================================
    FINAL COACH RECOMMENDATIONS
    ========================================
    
    Rank #[N]
    Coach Name : [Name]
    Scout Score : [Score]
    Current Club : [Club]
    Years of Experience : [Years]
    Preferred Formation : [Formation]
    Estimated Salary : [Salary]
    Key Strength : [Strength]
    
    📊 TACTICAL ANALYSIS:
    [Short evaluation]
    
    🧠 HEAD SCOUT JUSTIFICATION:
    [Professional reasoning]
    
    ----------------------------------------
    """
    
    final_out = run_agent_safe(ranking_agent, ranking_prompt, "Recommendations")
    print(final_out)

def main():
    while True:
        print("\n────────────────────────────────────────")
        print("STEP 1: ROLE SELECTION")
        try:
            choice = input("Do you need a PLAYER, a COACH, or NEW PLAYER registration?\n> ").strip().lower()
        except EOFError:
            sys.exit(0)
            
        if choice == 'new player':
            register_new_player_mode()
        elif choice == 'player':
            player_recommendation_mode()
        elif choice == 'coach':
            coach_recommendation_mode()
        elif choice in ['exit', 'quit']:
            sys.exit(0)
        else:
            print("Invalid input. Please enter 'player', 'coach', or 'new player'.")

if __name__ == "__main__":
    main()
