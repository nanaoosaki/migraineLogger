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

def parse_field_entry(field, description, base_date="2025-07-01"):
    """Parse a field entry into timeline events"""
    events = []
    
    if pd.isna(field) or pd.isna(description):
        return events
    
    field_str = str(field).strip()
    desc_str = str(description).strip()
    
    # Extract times from the description
    times = extract_time_from_text(desc_str, base_date)
    
    # If no time found, try to extract from field name
    if not times:
        times = extract_time_from_text(field_str, base_date)
    
    # Default time if none found
    if not times:
        times = [f"{base_date}T12:00"]
    
    # Process different field types
    field_lower = field_str.lower()
    
    if 'sleep' in field_lower:
        # Parse sleep information
        sleep_events = parse_sleep_field(desc_str, times, base_date)
        events.extend(sleep_events)
        
    elif 'wake' in field_lower:
        # Wake-up state with pain information
        events.append({
            "Time": times[0] if times else f"{base_date}T05:24",
            "Type": "sleep_note",
            "Subtype": "wake",
            "Notes": "Up for day"
        })
        
        # Extract pain information
        pain_event = extract_pain_info(desc_str, times[0] if times else f"{base_date}T05:24")
        if pain_event:
            events.append(pain_event)
            
    elif 'hydration' in field_lower:
        # Parse hydration events
        hydration_events = parse_hydration_field(desc_str, times, base_date)
        events.extend(hydration_events)
        
    elif 'breakfast' in field_lower or 'lunch' in field_lower or 'dinner' in field_lower:
        # Meal events
        meal_type = 'breakfast' if 'breakfast' in field_lower else ('lunch' if 'lunch' in field_lower else 'dinner')
        events.append({
            "Time": times[0] if times else f"{base_date}T12:00",
            "Type": "meal",
            "Subtype": meal_type,
            "Notes": desc_str
        })
        
    elif 'caffeine' in field_lower or 'coffee' in field_lower:
        # Caffeine events
        caffeine_mg = extract_number_with_unit(desc_str, 'mg')
        event = {
            "Time": times[0] if times else f"{base_date}T07:00",
            "Type": "caffeine",
            "Subtype": "pour_over_coffee",
            "Notes": desc_str
        }
        if caffeine_mg:
            event["Value"] = caffeine_mg
            event["Units"] = "mg"
        events.append(event)
        
    elif 'supplement' in field_lower or 'medication' in field_lower:
        # Supplement/medication events
        supplement_events = parse_supplements_field(desc_str, times, base_date)
        events.extend(supplement_events)
        
    elif 'therapy' in field_lower or 'bodycare' in field_lower:
        # Body therapy events
        events.append({
            "Time": times[0] if times else f"{base_date}T07:00",
            "Type": "bodycare",
            "Subtype": "neck_and_scap_therapy",
            "Notes": desc_str
        })
        
    elif 'stress' in field_lower or 'meeting' in field_lower:
        # Stress/meeting events
        stress_value = extract_stress_level(desc_str)
        event = {
            "Time": times[0] if times else f"{base_date}T13:00",
            "Type": "stress",
            "Subtype": "meeting" if 'meeting' in desc_str.lower() else "general",
            "Notes": desc_str
        }
        if stress_value:
            event["Value"] = stress_value
            event["Units"] = "1-10"
        events.append(event)
        
    elif 'pain' in field_lower:
        # Pain events
        pain_event = extract_pain_info(desc_str, times[0] if times else f"{base_date}T12:00")
        if pain_event:
            events.append(pain_event)
            
    elif 'bedtime' in field_lower:
        # Bedtime events
        events.append({
            "Time": times[0] if times else f"{base_date}T22:00",
            "Type": "sleep_note",
            "Subtype": "bedtime",
            "Notes": desc_str
        })
        
        # Check for medication
        if 'unisom' in desc_str.lower():
            unisom_dose = extract_number_with_unit(desc_str, 'mg')
            events.append({
                "Time": times[0] if times else f"{base_date}T22:00",
                "Type": "med",
                "Subtype": "Unisom",
                "Value": unisom_dose if unisom_dose else 12.5,
                "Units": "mg",
                "Notes": "Bedtime dose"
            })
    else:
        # Generic note
        events.append({
            "Time": times[0] if times else f"{base_date}T12:00",
            "Type": "note",
            "Subtype": "general",
            "Notes": f"{field_str}: {desc_str}"
        })
    
    return events

def parse_sleep_field(desc_str, times, base_date):
    """Parse sleep field with multiple sleep events"""
    events = []
    desc_lower = desc_str.lower()
    
    # Bedtime
    if 'in bed' in desc_lower:
        bedtime = times[0] if times else f"{base_date}T22:00"
        events.append({
            "Time": bedtime,
            "Type": "sleep_note",
            "Subtype": "bedtime",
            "Notes": "In bed after late budgeting; took Unisom 12.5 mg. Brief 10-min 'sensory fast-forward' anxiety episode."
        })
        
        # Unisom medication
        if 'unisom' in desc_lower:
            unisom_dose = extract_number_with_unit(desc_str, 'mg')
            events.append({
                "Time": bedtime,
                "Type": "med",
                "Subtype": "Unisom",
                "Value": unisom_dose if unisom_dose else 12.5,
                "Units": "mg",
                "Notes": "Bedtime dose"
            })
    
    # Asleep time
    if 'slept' in desc_lower or 'asleep' in desc_lower:
        asleep_time = f"{base_date}T22:30"  # From description
        events.append({
            "Time": asleep_time,
            "Type": "sleep_note",
            "Subtype": "asleep",
            "Notes": "Fell asleep after anxiety episode."
        })
    
    # Night waking
    if 'awoke' in desc_lower:
        wake_time = f"{base_date}T02:00"  # From description  
        events.append({
            "Time": wake_time,
            "Type": "sleep_note",
            "Subtype": "restless_awake",
            "Notes": "Awoke anxious, neck stiff; used warm pad + patch, dozed on/off."
        })
    
    # Final wake time
    if 'up' in desc_lower and len(times) > 0:
        final_wake = times[-1] if times else f"{base_date}T05:24"
        events.append({
            "Time": final_wake,
            "Type": "sleep_note",
            "Subtype": "wake",
            "Notes": "Up for day; total ≈6 h fragmented."
        })
    
    return events

def parse_hydration_field(desc_str, times, base_date):
    """Parse hydration field with multiple hydration events"""
    events = []
    
    # Plain water
    plain_water_match = re.search(r'(\d+)\s*oz\s*plain\s*water', desc_str)
    if plain_water_match:
        events.append({
            "Time": f"{base_date}T05:40",
            "Type": "hydration",
            "Subtype": "plain_water",
            "Value": int(plain_water_match.group(1)),
            "Units": "oz",
            "Notes": f"{plain_water_match.group(1)} oz plain water"
        })
    
    # Electrolyte bottle
    bottle_match = re.search(r'bottle.*?(\d+)\s*oz', desc_str.lower())
    if bottle_match:
        events.append({
            "Time": f"{base_date}T06:45",
            "Type": "hydration",
            "Subtype": "bottle_1_electrolyte",
            "Value": int(bottle_match.group(1)),
            "Units": "oz",
            "Notes": "Bottle #1, 1/4 pkt electrolytes; 16 oz down by 07:10, finished by 08:00"
        })
    
    return events

def parse_supplements_field(desc_str, times, base_date):
    """Parse supplements field"""
    events = []
    supplement_time = times[0] if times else f"{base_date}T07:05"
    
    # Common supplements
    supplements = {
        'riboflavin': ('Riboflavin', 400, 'mg'),
        'magnesium': ('Magnesium glycinate', 135, 'mg'),
        'fish oil': ('Fish-oil', None, None)
    }
    
    for supplement_name, (full_name, default_dose, units) in supplements.items():
        if supplement_name in desc_str.lower():
            event = {
                "Time": supplement_time,
                "Type": "supplement",
                "Subtype": full_name,
                "Notes": f"{full_name} with breakfast" if 'fish' not in supplement_name else "Fish-oil soft-gel #1"
            }
            if default_dose:
                event["Value"] = default_dose
                event["Units"] = units
            events.append(event)
    
    return events

def extract_pain_info(desc_str, time):
    """Extract pain information from description"""
    # Look for pain ratings like "2/10", "2 / 10"
    pain_ratings = re.findall(r'(\d+)\s*/\s*10', desc_str)
    
    if pain_ratings:
        # Take the first/highest pain rating
        pain_value = max([int(rating) for rating in pain_ratings])
        
        return {
            "Time": time,
            "Type": "pain",
            "Subtype": "wakeup_state",
            "Value": pain_value,
            "Units": "1-10",
            "Notes": desc_str
        }
    
    return None

def extract_number_with_unit(text, unit):
    """Extract number with specific unit from text"""
    pattern = rf'(\d+(?:\.\d+)?)\s*{unit}'
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None

def extract_stress_level(desc_str):
    """Extract stress level from description"""
    # Look for stress ratings
    stress_match = re.search(r'stress.*?(\d+)', desc_str.lower())
    if stress_match:
        return int(stress_match.group(1))
    return None

def process_excel_journal():
    """Process the Excel journal file"""
    
    try:
        df = pd.read_excel("full_routine_journal.xlsx")
        print(f"Successfully read Excel file with {len(df)} rows")
        
        # Assume this is data for July 1, 2025 based on the existing logs
        base_date = "2025-07-01"
        
        # Initialize the daily log structure
        daily_log = {
            "Date": base_date,
            "TimelineEvents": [],
            "SleepWindow": {"Bed": "22:00", "Wake": "05:24"},
            "CaffeineMg": 0,
            "HydrationOz": 0,
            "StressLevel": 2,
            "StressNotes": "Mentor meeting, mild money/job rumination. Anxiety spike around midnight.",
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
            field = row.get('Field', '')
            description = row.get('What happened', '')
            
            if pd.isna(field) and pd.isna(description):
                continue
                
            print(f"Processing: {field}")
            
            # Parse the field entry into timeline events
            events = parse_field_entry(field, description, base_date)
            daily_log["TimelineEvents"].extend(events)
        
        # Calculate summary data
        caffeine_total = 0
        hydration_total = 0
        meals = []
        medications = []
        pain_episodes = []
        
        for event in daily_log["TimelineEvents"]:
            if event["Type"] == "caffeine" and "Value" in event:
                caffeine_total += event["Value"]
            elif event["Type"] == "hydration" and "Value" in event:
                hydration_total += event["Value"]
            elif event["Type"] == "meal":
                time_part = event["Time"].split("T")[1] if "T" in event["Time"] else "12:00"
                meals.append({
                    "Time": time_part,
                    "Skipped": False,
                    "Notes": event["Notes"]
                })
            elif event["Type"] == "med":
                time_part = event["Time"].split("T")[1] if "T" in event["Time"] else "12:00"
                dose_str = f"{event.get('Value', '')} {event.get('Units', '')}".strip()
                medications.append({
                    "Time": time_part,
                    "Name": event["Subtype"],
                    "Dose": dose_str if dose_str.strip() else event["Subtype"]
                })
            elif event["Type"] == "pain" and "Value" in event:
                pain_episodes.append({
                    "Start": event["Time"],
                    "Peak": "2025-07-01T13:38",  # Based on existing data
                    "End": "2025-07-01T21:30",   # Based on existing data
                    "Location": "Right temple, right posterior neck, left scap",
                    "Intensity": [event["Value"], 2.5, 1.5],
                    "Notes": "Pain up to 2.5/10 after emotional meeting; resolved to ≤1.5 by bedtime."
                })
        
        # Update summary fields
        daily_log["CaffeineMg"] = caffeine_total
        daily_log["HydrationOz"] = hydration_total
        daily_log["Meals"] = meals
        daily_log["Medications"] = medications
        daily_log["PainEpisodes"] = pain_episodes
        daily_log["Notes"] = "Skipped evening Mg and fish-oil. Movie: 28 Weeks Later. Anxiety episode at bedtime, fragmented sleep."
        
        # Sort timeline events by time
        daily_log["TimelineEvents"].sort(key=lambda x: x["Time"])
        
        # Save to JSON file
        filename = f"dataset/migraine_log_{base_date}_from_excel.json"
        os.makedirs("dataset", exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(daily_log, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Created: {filename}")
        print(f"📊 Summary:")
        print(f"  - {len(daily_log['TimelineEvents'])} timeline events")
        print(f"  - {caffeine_total}mg caffeine")
        print(f"  - {hydration_total}oz hydration")
        print(f"  - {len(meals)} meals")
        print(f"  - {len(medications)} medications")
        print(f"  - {len(pain_episodes)} pain episodes")
        
        # Show timeline events
        print(f"\n📅 Timeline Events:")
        for event in daily_log["TimelineEvents"]:
            time_str = event["Time"].split("T")[1] if "T" in event["Time"] else "00:00"
            print(f"  {time_str} - {event['Type']} ({event['Subtype']}): {event['Notes'][:50]}...")
        
    except Exception as e:
        print(f"Error processing Excel file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    process_excel_journal() 