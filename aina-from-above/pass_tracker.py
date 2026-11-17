import os
import re
import csv
import requests
import time
from datetime import datetime, timedelta, timezone
from skyfield.api import Topos, load, EarthSatellite

# ==============================================================================
# CONFIGURATION & GLOBAL SETUP
# ==============================================================================

# Directory where output pass logs (CSV files) will be stored.
# Defaults to a pass_logs folder next to this script; swap in your own path if you want them elsewhere.
TARGET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pass_logs")

# Standard file prefix to ensure uniform naming across all saved logs.
# This makes it easier to filter logs and enables quick autocompletion in Linux.
FILE_PREFIX = "passlog_"

# ------------------------------------------------------------------------------
# LINUX/MACOS AUTO-COMPLETION ENGINE (readline)
# ------------------------------------------------------------------------------
# Attempts to load Python's built-in 'readline' module to support Tab-completion
# in the CLI. If running on Windows, this block safely degrades via ImportError.
try:
    import readline
    import glob

    def path_completer(text, state):
        """
        Callback function for the readline engine.
        Matches text typed by the user against files in TARGET_DIR.
        """
        pattern = os.path.join(TARGET_DIR, text + "*")
        matches = [os.path.basename(p) for p in glob.glob(pattern)]
        try:
            return matches[state]
        except IndexError:
            return None

    # Register the tab completer function with readline
    readline.set_completer(path_completer)
    
    # Bind the Tab key to the completion action depending on the underlying terminal library
    if 'libedit' in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
except ImportError:
    # Readline is not natively available on Windows without third-party packages
    pass


# ==============================================================================
# HELPER FUNCTIONS (INPUT SANITIZATION & FILE PATH CREATION)
# ==============================================================================

def sanitize_filename(name: str) -> str:
    """
    Cleans raw user input to ensure it is safe for OS file systems.
    - Replaces spaces with underscores.
    - Removes illegal characters (e.g., /, \\, :, *, ?, ", <, >, |).
    """
    name = name.strip().replace(" ", "_")
    name = re.sub(r'[^\w\-]', '', name)
    return name


def get_save_filepath() -> str:
    """
    Prompts the user for a custom file descriptor, formats it using standard 
    naming rules (`passlog_[DESCRIPTOR]_[DATE].csv`), and prevents accidental 
    file overwrites by appending version tags (e.g., `_v1.csv`).
    """
    # Ensure the output directory exists before writing
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)

    today_str = datetime.now().strftime("%Y_%m_%d")

    print("\n--- Save Pass Log ---")
    print("Note: Do NOT type '.csv' (it will be added automatically).")
    raw_name = input("Enter log name (e.g., MauiPasses or PassAttempt1): ").strip()
    
    # Remove '.csv' extension if the user typed it anyway to prevent '.csv.csv'
    if raw_name.lower().endswith(".csv"):
        raw_name = raw_name[:-4]

    # Sanitize user string; default to 'SatellitePasses' if left blank or invalid
    clean_name = sanitize_filename(raw_name)
    if not clean_name:
        clean_name = "SatellitePasses"

    # Assemble filename structure: passlog_[USERFILENAME]_[DATE].csv
    filename = f"{FILE_PREFIX}{clean_name}_{today_str}.csv"
    filepath = os.path.join(TARGET_DIR, filename)

    # Collision Prevention Loop:
    # If a log with this exact name already exists today, append _v1, _v2, etc.
    counter = 1
    base_filepath = filepath[:-4]
    while os.path.exists(filepath):
        filepath = f"{base_filepath}_v{counter}.csv"
        counter += 1

    return filepath


# ==============================================================================
# CORE WEBSCRAPING & COMPUTATION FUNCTION
# ==============================================================================

def scrape_data():
    """
    Main webscraping and orbital calculation routine:
    1. Prompts for a file save path.
    2. Downloads real-time TLE orbital data from Celestrak for targeted satellites.
    3. Calculates visual passes relative to Maui ground station coordinates.
    4. Converts UTC times to Hawaii Standard Time (HST).
    5. Saves pass events (Rise, Culminate, Set) to a CSV file.
    """
    # Generate unique destination path for this scrape session
    filepath = get_save_filepath()

    # NORAD Catalog IDs for tracked satellites
    satellites = {
        "ISS": "25544",
        "METEOR M2-3": "57166",
        "METEOR M2-4": "59051"
    }

    # Initialize Skyfield timescale engine and Maui geographic coordinates
    ts = load.timescale()
    maui = Topos('20.8893 N', '156.4729 W')
    
    # Establish calculation window: Current time to +3 days forward
    now_utc = datetime.now(timezone.utc)
    t0 = ts.from_datetime(now_utc)
    t1 = ts.from_datetime(now_utc + timedelta(days=3))

    headers = ["Satellite", "Date", "Event", "Time (HST)", "Alt", "Az"]

    # Open target CSV file for writing
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        # Iterate through each defined satellite
        for name, norad_id in satellites.items():
            print(f"Fetching latest orbital data for {name}...")
            tle_url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"
            
            try:
                # Retrieve fresh Two-Line Element (TLE) set from Celestrak API
                response = requests.get(tle_url, timeout=15)
                tle_data = response.text.splitlines()
                
                # Validation check: A complete TLE response requires at least 3 lines (Header, Line 1, Line 2)
                if len(tle_data) < 3:
                    print(f"  ! Skip: No data returned for {name}")
                else:
                    # Extract TLE line 1 and line 2
                    line1, line2 = tle_data[1], tle_data[2]
                    satellite = EarthSatellite(line1, line2, name, ts)

                    # Calculate pass events above 10 degrees altitude threshold
                    t, events = satellite.find_events(maui, t0, t1, altitude_degrees=10.0)

                    # Process each calculated pass event
                    for ti, event in zip(t, events):
                        # Convert Skyfield UTC timestamp to Hawaii Standard Time (UTC -10)
                        hst_time = ti.utc_datetime().replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-10)))
                        
                        # Map Skyfield integer event codes (0, 1, 2) to descriptive text labels
                        event_type = ('Rise', 'Culminate (Max)', 'Set')[event]
                        
                        # Calculate topocentric positions (altitude, azimuth, distance) from Maui observer
                        difference = satellite - maui
                        topocentric = difference.at(ti)
                        alt, az, distance = topocentric.altaz()

                        # Write computed event details as a row in the CSV
                        writer.writerow([
                            name,
                            hst_time.strftime('%Y-%m-%d'),
                            event_type,
                            hst_time.strftime('%H:%M:%S'),
                            f"{alt.degrees:.1f}°",
                            f"{az.degrees:.1f}°"
                        ])
                    
                    print(f"  + {name} data added to CSV.")

            except Exception as e:
                # Catch network request or parsing errors without crashing the main script
                print(f"  ! Error on {name}: {e}")

            # Politeness delay between API web requests
            time.sleep(3)

    print(f"\n[Success] Pass log saved as: {os.path.basename(filepath)}")
    return filepath


# ==============================================================================
# CLI DISPLAY & CSV READING FUNCTION
# ==============================================================================

def read_from_csv(filepath=None):
    """
    Reads a pass log CSV file and outputs a cleanly formatted ASCII table.
    - If `filepath` is not provided, scans for existing logs, presents the 5 most
      recently updated files, and prompts the user to input a target filename.
    """
    if not os.path.exists(TARGET_DIR):
        print(f"\n[Error] Target directory does not exist: {TARGET_DIR}")
        return

    # IF STAGE 1: If no specific file was passed, enter interactive file selection mode
    if not filepath:
        # Search target directory for files matching prefix 'passlog_' and ending in '.csv'
        all_csvs = [
            os.path.join(TARGET_DIR, f) for f in os.listdir(TARGET_DIR) 
            if f.startswith(FILE_PREFIX) and f.endswith(".csv")
        ]
        
        # Sort files by last modification timestamp (newest files first)
        sorted_files = sorted(all_csvs, key=os.path.getmtime, reverse=True)
        recent_files = sorted_files[:5]  # Limit to 5 most recent files

        print("\n" + "="*65)
        print(" 5 MOST RECENT PASS LOGS")
        print(" (Note: Linux users can press TAB after typing passlog_ to autocomplete)")
        print("="*65)
        
        # Render the list of 5 recent logs with their modification dates
        if recent_files:
            for filepath_item in recent_files:
                filename = os.path.basename(filepath_item)
                mod_time = datetime.fromtimestamp(os.path.getmtime(filepath_item)).strftime('%Y-%m-%d %H:%M')
                print(f"  • {filename:<38} [Saved: {mod_time}]")
        else:
            print("  (No existing CSV logs found starting with 'passlog_')")
        print("="*65)

        print("\nNote: You do NOT need to type '.csv' at the end.")
        user_input = input("Enter filename: ").strip()
        
        # Strip .csv extension if typed by user
        if user_input.lower().endswith(".csv"):
            user_input = user_input[:-4]

        # Automatically prepend prefix if omitted by user
        if not user_input.startswith(FILE_PREFIX):
            user_input = FILE_PREFIX + user_input

        filename = user_input + ".csv"
        filepath = os.path.join(TARGET_DIR, filename)

    # IF STAGE 2: Validate whether target CSV exists before trying to open
    if not os.path.exists(filepath):
        print(f"\n[Error] Could not find file: {os.path.basename(filepath)}")
        return

    # STAGE 3: Parse CSV content and format ASCII output
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = list(csv.DictReader(f))

        if not reader:
            print("\n[Warning] CSV file is empty.")
            return

        print("\n" + "="*65)
        print(f"{'PASS LOG: ' + os.path.basename(filepath):^65}")
        print("="*65)

        current_sat = None
        current_date = None

        # Print structured ASCII table rows grouped by Satellite and Date
        for row in reader:
            sat = row['Satellite']
            date = row['Date']

            # Print Satellite Header banner when switching to a new satellite group
            if sat != current_sat:
                current_sat = sat
                current_date = None
                print(f"\n┌─────────────── {current_sat} ───────────────┐")

            # Print Date Section subheader when switching to a new date
            if date != current_date:
                current_date = date
                print(f"\n  DATE: {current_date}")
                print("  " + "─"*52)
                print(f"  │ {'Time (HST)':^10} │ {'Event':^16} │ {'Alt':^7} │ {'Az':^7} │")
                print("  " + "─"*52)

            time_val = row['Time (HST)']
            event = row['Event']
            alt = row['Alt']
            az = row['Az']

            # Print aligned event data row
            print(f"  │ {time_val:^10} │ {event:<16} │ {alt:>7} │ {az:>7} │")

            # Print bottom border after completing a pass sequence (Set event)
            if event == 'Set':
                print("  " + "─"*52)

        print("\n" + "="*65 + "\n")

    except Exception as e:
        print(f"\nError reading file: {e}")


# ==============================================================================
# MENU NAVIGATION & PROGRAM CONTROLS
# ==============================================================================

def prompt_next_action():
    """
    Navigation prompt that triggers after performing an action (scraping or reading).
    Returns True to return to the main menu, or False to terminate execution.
    """
    while True:
        choice = input("Would you like to (M)ain Menu or (E)xit? ").strip().lower()
        if choice in ['m', 'main', 'menu']:
            return True
        elif choice in ['e', 'exit', 'q', 'quit']:
            return False
        else:
            print("Invalid entry. Please enter 'M' to return to menu or 'E' to exit.\n")


def main():
    """
    Main application loop. Displays CLI option menu and manages execution state.
    """
    while True:
        print("\n---------------------------------")
        print("    Satellite Tracker Utility    ")
        print("---------------------------------")
        print(" [1] Scrape Fresh Data (Save New Log)")
        print(" [2] Load CSV File (Shows 5 Recent)")
        print(" [3] Exit")
        print("---------------------------------")
        
        choice = input("Select an option (1-3): ").strip()

        if choice == '1':
            saved_file = scrape_data()
            read_from_csv(saved_file)  # Display the freshly scraped file immediately
            if not prompt_next_action():
                print("\nClear skies! Exiting program...\n")
                break

        elif choice == '2':
            read_from_csv()
            if not prompt_next_action():
                print("\nClear skies! Exiting program...\n")
                break

        elif choice in ['3', 'e', 'exit', 'q', 'quit']:
            print("\nClear skies! Exiting program...\n")
            break

        else:
            print("\nInvalid selection. Please enter 1, 2, or 3.")


# Entry point guard: Ensures script runs only when executed directly (not when imported)
if __name__ == "__main__":
    main()