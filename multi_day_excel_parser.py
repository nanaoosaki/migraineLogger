import pandas as pd
import json
from datetime import datetime
import os
import re

def extract_time_from_text(text, default_date="2025-07-01"):
    """Extract time information from text descriptions"""
    if pd.isna(text):
        return []
    
    text_str = str(text)
    times = []
    
    # Look for time patterns like "22 : 00", "05 : 24", "06 : 54"
    time_patterns = re.findall(r'(\d{1,2})\s*[:：]\s*(\d{2})', text_str)
    
    for hour, minute in time_patterns:
        iso_time = f"{default_date}T{int(hour):02d}:{int(minute):02d}"
        times.append(iso_time)
    
    return times

def categorize_event(field, description):
    """Categorize events based on field name and description"""
    if pd.isna(field) or pd.isna(description):
        return "note", "general", str(description)
    
    field_str = str(field).lower().strip()
    desc_str = str(description).strip()
    
    # Sleep-related fields
    if 'sleep' in field_str:
        return "sleep_note", "general", desc_str
    elif 'wake' in field_str:
        return "sleep_note", "wake", desc_str
    elif 'bedtime' in field_str:
        return "sleep_note", "bedtime", desc_str
        
    # Pain/fog related
    elif any(word in field_str for word in ['pain', 'fog', 'wake-up state', 'wake state']):
        return "pain", "status_update", desc_str
        
    # Hydration
    elif 'hydration' in field_str or 'bottle' in field_str:
        return "hydration", "water", desc_str
        
    # Meals
    elif any(word in field_str for word in ['breakfast', 'lunch', 'dinner', 'meal', 'snack']):
        meal_type = 'breakfast' if 'breakfast' in field_str else ('lunch' if 'lunch' in field_str else 'dinner')
        return "meal", meal_type, desc_str
        
    # Supplements/medications
    elif 'supplement' in field_str or 'medication' in field_str or 'med' in field_str:
        return "supplement", "general", desc_str
        
    # Exercise/therapy
    elif any(word in field_str for word in ['exercise', 'therapy', 'care', 'stretch']):
        return "bodycare", "therapy", desc_str
        
    # Caffeine/coffee
    elif 'caffeine' in field_str or 'coffee' in field_str:
        return "caffeine", "coffee", desc_str
        
    # Stress/meetings
    elif any(word in field_str for word in ['stress', 'meeting', 'work', 'anxiety']):
        return "stress", "meeting" if 'meeting' in field_str else "general", desc_str
        
    # Activity/entertainment
    elif any(word in field_str for word in ['movie', 'activity', 'entertainment']):
        return "activity", "movie" if 'movie' in field_str else "general", desc_str
        
    # Default
    else:
        return "note", "general", f"{field_str}: {desc_str}"

def extract_numeric_values(desc_str, event_type):
    """Extract numeric values from descriptions"""
    if pd.isna(desc_str):
        return None, None
    
    desc_lower = str(desc_str).lower()
    
    if event_type == "pain":
        # Look for pain/fog ratings like "2/10", "fog 3"
        pain_match = re.search(r'(\d+)\s*/\s*10', desc_lower)
        if pain_match:
            return int(pain_match.group(1)), "1-10"
        fog_match = re.search(r'fog\s*(\d+)', desc_lower)
        if fog_match:
            return int(fog_match.group(1)), "1-10"
            
    elif event_type == "hydration":
        # Look for ounces
        oz_matches = re.findall(r'(\d+)\s*oz', desc_lower)
        if oz_matches:
            # Sum all oz mentions
            total_oz = sum(int(oz) for oz in oz_matches)
            return total_oz, "oz"
            
    elif event_type == "caffeine":
        # Look for mg or estimate
        mg_match = re.search(r'(\d+)\s*mg', desc_lower)
        if mg_match:
            return int(mg_match.group(1)), "mg"
        elif 'coffee' in desc_lower:
            return 120, "mg"  # Standard estimate
            
    elif event_type in ["supplement", "med"]:
        # Look for dosages
        dose_match = re.search(r'(\d+(?:\.\d+)?)\s*(mg|g)', desc_lower)
        if dose_match:
            return float(dose_match.group(1)), dose_match.group(2)
    
    return None, None

def parse_sheet_data(sheet_name, df):
    """Parse data from a single sheet into timeline events"""
    
    print(f"\n📋 Processing sheet: {sheet_name}")
    
    # Initialize daily log structure
    daily_log = {
        "Date": sheet_name,
        "TimelineEvents": [],
        "SleepWindow": {"Bed": "", "Wake": ""},
        "CaffeineMg": 0,
        "HydrationOz": 0,
        "StressLevel": None,
        "StressNotes": "",
        "Meals": [],
        "Medications": [],
        "PainEpisodes": [],
        "Weather": {},
        "Reflection": {
            "Accomplishments": "",
            "Bothering": "",
            "TomorrowPlan": ""
        },
        "Notes": ""
    }
    
    # Process each row
    for index, row in df.iterrows():
        if row.isna().all():
            continue
            
        # Get field and description from the row
        field = None
        description = None
        
        # Find the Field column and the data column
        for col in df.columns:
            if 'field' in str(col).lower():
                field = row[col]
            else:
                description = row[col]
        
        if pd.isna(field) and pd.isna(description):
            continue
            
        # Extract times from description
        times = extract_time_from_text(description, sheet_name)
        if not times:
            times = extract_time_from_text(field, sheet_name)
        if not times:
            times = [f"{sheet_name}T12:00"]  # Default time
        
        # Categorize the event
        event_type, subtype, notes = categorize_event(field, description)
        
        # Extract numeric values
        value, units = extract_numeric_values(description, event_type)
        
        # Handle multiple events from complex descriptions
        if event_type == "sleep_note" and "sleep" in str(field).lower():
            # Parse complex sleep descriptions
            sleep_events = parse_complex_sleep(description, sheet_name)
            daily_log["TimelineEvents"].extend(sleep_events)
        else:
            # Create single timeline event
            event = {
                "Time": times[0],
                "Type": event_type,
                "Subtype": subtype,
                "Notes": notes
            }
            
            if value is not None:
                event["Value"] = value
                event["Units"] = units
            
            daily_log["TimelineEvents"].append(event)
    
    # Calculate summary data
    caffeine_total = 0
    hydration_total = 0
    stress_events = []
    meals = []
    medications = []
    pain_episodes = []
    sleep_times = {"Bed": "", "Wake": ""}
    
    for event in daily_log["TimelineEvents"]:
        if event["Type"] == "caffeine" and "Value" in event:
            caffeine_total += event["Value"]
        elif event["Type"] == "hydration" and "Value" in event:
            hydration_total += event["Value"]
        elif event["Type"] == "stress" and "Value" in event:
            stress_events.append(event["Value"])
        elif event["Type"] == "meal":
            time_part = event["Time"].split("T")[1] if "T" in event["Time"] else "12:00"
            meals.append({
                "Time": time_part,
                "Skipped": False,
                "Notes": event["Notes"]
            })
        elif event["Type"] in ["med", "supplement"] and "unisom" in event["Notes"].lower():
            time_part = event["Time"].split("T")[1] if "T" in event["Time"] else "22:00"
            medications.append({
                "Time": time_part,
                "Name": "Unisom",
                "Dose": "12.5 mg"
            })
        elif event["Type"] == "pain" and "Value" in event:
            pain_episodes.append({
                "Start": event["Time"],
                "Peak": event["Time"],
                "End": None,
                "Location": "General",
                "Intensity": [event["Value"]],
                "Notes": event["Notes"]
            })
        elif event["Type"] == "sleep_note":
            if "bedtime" in event["Subtype"] or "bed" in event["Notes"].lower():
                sleep_times["Bed"] = event["Time"].split("T")[1] if "T" in event["Time"] else "22:00"
            elif "wake" in event["Subtype"] or "wake" in event["Notes"].lower():
                sleep_times["Wake"] = event["Time"].split("T")[1] if "T" in event["Time"] else "06:00"
    
    # Update summary fields
    daily_log["CaffeineMg"] = caffeine_total
    daily_log["HydrationOz"] = hydration_total
    daily_log["StressLevel"] = int(sum(stress_events) / len(stress_events)) if stress_events else None
    daily_log["SleepWindow"] = sleep_times
    daily_log["Meals"] = meals
    daily_log["Medications"] = medications
    daily_log["PainEpisodes"] = pain_episodes
    
    # Sort timeline events by time
    daily_log["TimelineEvents"].sort(key=lambda x: x["Time"])
    
    return daily_log

def parse_complex_sleep(description, date):
    """Parse complex sleep descriptions into multiple events"""
    events = []
    desc_str = str(description).lower()
    
    # Extract bedtime
    bedtime_match = re.search(r'in bed.*?(\d{1,2})\s*[:：]\s*(\d{2})', desc_str)
    if bedtime_match:
        hour, minute = bedtime_match.groups()
        events.append({
            "Time": f"{date}T{int(hour):02d}:{int(minute):02d}",
            "Type": "sleep_note",
            "Subtype": "bedtime",
            "Notes": "In bed"
        })
    
    # Extract asleep time
    asleep_match = re.search(r'asleep.*?(\d{1,2})\s*[:：]\s*(\d{2})', desc_str)
    if asleep_match:
        hour, minute = asleep_match.groups()
        events.append({
            "Time": f"{date}T{int(hour):02d}:{int(minute):02d}",
            "Type": "sleep_note",
            "Subtype": "asleep",
            "Notes": "Fell asleep"
        })
    
    # Extract wake times
    wake_matches = re.findall(r'(?:woke|awake|up).*?(\d{1,2})\s*[:：]\s*(\d{2})', desc_str)
    for i, (hour, minute) in enumerate(wake_matches):
        subtype = "restless_awake" if i < len(wake_matches) - 1 else "wake"
        events.append({
            "Time": f"{date}T{int(hour):02d}:{int(minute):02d}",
            "Type": "sleep_note",
            "Subtype": subtype,
            "Notes": "Awake" if subtype == "restless_awake" else "Up for day"
        })
    
    return events

def process_all_sheets():
    """Process all sheets in the Excel file"""
    
    try:
        xl_file = pd.ExcelFile('full_routine_journal.xlsx')
        
        print(f"🗂️ Found {len(xl_file.sheet_names)} sheets to process")
        print(f"📅 Date range: {xl_file.sheet_names[-1]} to {xl_file.sheet_names[0]}")
        
        processed_count = 0
        
        for sheet_name in xl_file.sheet_names:
            try:
                # Skip empty sheets
                df = pd.read_excel('full_routine_journal.xlsx', sheet_name=sheet_name)
                
                if df.empty or df.dropna(how='all').empty:
                    print(f"⏭️ Skipping empty sheet: {sheet_name}")
                    continue
                
                # Process the sheet
                daily_log = parse_sheet_data(sheet_name, df)
                
                # Save to JSON file
                filename = f"dataset/migraine_log_{sheet_name}.json"
                os.makedirs("dataset", exist_ok=True)
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(daily_log, f, indent=2, ensure_ascii=False)
                
                processed_count += 1
                
                print(f"✅ Created: {filename}")
                print(f"   📊 {len(daily_log['TimelineEvents'])} events | "
                      f"☕ {daily_log['CaffeineMg']}mg caffeine | "
                      f"💧 {daily_log['HydrationOz']}oz hydration | "
                      f"🍽️ {len(daily_log['Meals'])} meals")
                
            except Exception as e:
                print(f"❌ Error processing sheet '{sheet_name}': {e}")
                continue
        
        print(f"\n🎉 Successfully processed {processed_count} out of {len(xl_file.sheet_names)} sheets!")
        
        # List all created files
        print(f"\n📁 Created files in dataset/:")
        for sheet_name in xl_file.sheet_names:
            filename = f"migraine_log_{sheet_name}.json"
            if os.path.exists(f"dataset/{filename}"):
                print(f"   ✓ {filename}")
        
    except Exception as e:
        print(f"❌ Error processing Excel file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    process_all_sheets() 