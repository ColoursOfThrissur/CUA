"""
Critical Vision Tests: qwen3-vl:8b vs qwen3.5:9b
Tests the desktop automation controller workload - one model at a time
"""

import requests
import json
import time
import base64
from pathlib import Path

OLLAMA_URL = "http://localhost:11434"

def unload_model(model: str):
    """Unload model from memory"""
    print(f"\nUnloading {model}...")
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10
        )
        if response.status_code == 200:
            print(f"  OK - {model} unloaded")
            time.sleep(3)  # Wait for full unload
            return True
    except Exception as e:
        print(f"  FAIL - {e}")
    return False

def create_test_image():
    """Create a simple test image with UI elements"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create 800x600 image with UI elements
        img = Image.new('RGB', (800, 600), color='#f0f0f0')
        draw = ImageDraw.Draw(img)
        
        # Title bar
        draw.rectangle([0, 0, 800, 40], fill='#2c3e50')
        draw.text((20, 12), "Steam - Library", fill='white')
        
        # Navigation buttons
        draw.rectangle([50, 80, 250, 130], fill='#3498db', outline='black', width=2)
        draw.text((120, 95), "Library", fill='white')
        
        draw.rectangle([270, 80, 470, 130], fill='white', outline='black', width=2)
        draw.text((340, 95), "Store", fill='black')
        
        draw.rectangle([490, 80, 690, 130], fill='white', outline='black', width=2)
        draw.text((540, 95), "Community", fill='black')
        
        # Game list
        draw.rectangle([50, 180, 750, 230], fill='white', outline='black', width=1)
        draw.text((60, 195), "Counter-Strike 2", fill='black')
        
        draw.rectangle([50, 250, 750, 300], fill='white', outline='black', width=1)
        draw.text((60, 265), "Dota 2", fill='black')
        
        draw.rectangle([50, 320, 750, 370], fill='white', outline='black', width=1)
        draw.text((60, 335), "Team Fortress 2", fill='black')
        
        # Save
        img_path = Path("test_steam_ui.png")
        img.save(img_path)
        print(f"\nCreated test image: {img_path}")
        return str(img_path)
    except Exception as e:
        print(f"\nERROR: Failed to create test image: {e}")
        print("Install Pillow: pip install pillow")
        return None

def test_vision(model: str, test_name: str, prompt: str, image_path: str, use_format_json: bool = False):
    """Test vision model with image"""
    print(f"\n  Test: {test_name}")
    
    # Load image
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"    ERROR: Failed to load image: {e}")
        return {"success": False, "error": str(e)}
    
    # Official Qwen3.5 parameters for vision+JSON
    options = {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.0,
        "num_ctx": 32768
    }
    
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
        "options": options
    }
    
    if use_format_json:
        payload["format"] = "json"
    
    try:
        start = time.time()
        response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            thinking = data.get("thinking", "")
            response_text = data.get("response", "")
            
            # Determine where the actual content is
            content = response_text if response_text else thinking
            
            # Try to parse as JSON
            is_valid_json = False
            parsed_json = None
            try:
                parsed_json = json.loads(content)
                is_valid_json = True
            except:
                pass
            
            print(f"    Duration: {elapsed*1000:.0f}ms")
            print(f"    Response: {len(response_text)} chars, Thinking: {len(thinking)} chars")
            print(f"    Valid JSON: {is_valid_json}")
            print(f"    Preview: {content[:150]}...")
            
            return {
                "success": True,
                "duration_ms": int(elapsed * 1000),
                "response_length": len(response_text),
                "thinking_length": len(thinking),
                "is_valid_json": is_valid_json,
                "parsed_json": parsed_json,
                "content_preview": content[:300]
            }
        else:
            print(f"    ERROR: HTTP {response.status_code}")
            return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        print(f"    ERROR: {str(e)}")
        return {"success": False, "error": str(e)}

def run_all_tests_for_model(model: str, image_path: str):
    """Run all 4 critical tests for one model"""
    print(f"\n{'='*80}")
    print(f"TESTING MODEL: {model}")
    print(f"{'='*80}")
    
    tests = [
        {
            "name": "1. Vision + JSON Speed (Simple)",
            "prompt": """RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.

Analyze this screenshot and return:
{
  "active_app": "name of active application",
  "visible_elements": ["list", "of", "visible", "UI", "elements"]
}

JSON ONLY. START NOW:""",
            "use_format_json": True
        },
        {
            "name": "2. Screenshot Analysis - UI Element Detection",
            "prompt": """RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.

Detect all interactive UI elements in this screenshot and return:
{
  "buttons": [{"text": "button text", "state": "active/inactive"}],
  "text_fields": ["list of text content"],
  "active_element": "which element is currently active"
}

JSON ONLY. START NOW:""",
            "use_format_json": True
        },
        {
            "name": "3. Complex Vision JSON - Multi-field Structure",
            "prompt": """RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.

Analyze this screenshot comprehensively and return:
{
  "visual_state": {
    "active_window": "window name",
    "layout_type": "description",
    "color_scheme": "light/dark"
  },
  "elements": [
    {
      "type": "button/text/list",
      "text": "content",
      "position": "top/middle/bottom",
      "interactive": true/false
    }
  ],
  "actions_available": ["list", "of", "possible", "actions"],
  "current_focus": "what element has focus"
}

JSON ONLY. START NOW:""",
            "use_format_json": True
        },
        {
            "name": "4. Vision Accuracy - JSON Compliance",
            "prompt": """RETURN ONLY VALID JSON. NO TEXT. NO EXPLANATION.

Find specific elements and return EXACT structure:
{
  "library_button": {"found": true/false, "text": "exact text", "state": "active/inactive"},
  "store_button": {"found": true/false, "text": "exact text", "state": "active/inactive"},
  "game_list": ["exact game names found"],
  "total_games": 0
}

JSON ONLY. START NOW:""",
            "use_format_json": True
        }
    ]
    
    results = {}
    
    for test in tests:
        result = test_vision(model, test['name'], test['prompt'], image_path, test['use_format_json'])
        results[test['name']] = result
        time.sleep(1)  # Brief pause between tests
    
    return results

def main():
    # Create test image
    image_path = create_test_image()
    if not image_path:
        print("\nERROR: Could not create test image. Install Pillow: pip install pillow")
        return
    
    models = ["qwen3-vl:8b", "qwen3.5:9b"]
    all_results = {}
    
    # Test each model completely before switching
    for model in models:
        # Run all tests for this model
        model_results = run_all_tests_for_model(model, image_path)
        all_results[model] = model_results
        
        # Unload this model before next
        unload_model(model)
        time.sleep(2)
    
    # Print comprehensive summary
    print(f"\n\n{'#'*80}")
    print("# CRITICAL VISION TESTS - COMPARISON SUMMARY")
    print(f"{'#'*80}")
    
    test_names = list(next(iter(all_results.values())).keys())
    
    for test_name in test_names:
        print(f"\n{test_name}:")
        print("-" * 80)
        
        for model in models:
            result = all_results[model].get(test_name, {})
            if result.get("success"):
                duration = result['duration_ms']
                valid_json = "VALID JSON" if result.get("is_valid_json") else "INVALID JSON"
                print(f"  {model:20s}: {duration:6d}ms  {valid_json}")
                
                # Show parsed JSON structure if available
                if result.get("parsed_json"):
                    parsed = result['parsed_json']
                    if isinstance(parsed, dict):
                        keys = list(parsed.keys())
                        print(f"                           Keys: {keys}")
            else:
                print(f"  {model:20s}: FAILED - {result.get('error', 'unknown')}")
    
    # Speed comparison
    print(f"\n{'='*80}")
    print("SPEED WINNER PER TEST:")
    print(f"{'='*80}")
    
    total_times = {model: 0 for model in models}
    success_counts = {model: 0 for model in models}
    
    for test_name in test_names:
        print(f"\n{test_name}:")
        
        durations = {}
        for model in models:
            result = all_results[model].get(test_name, {})
            if result.get("success"):
                durations[model] = result['duration_ms']
                total_times[model] += result['duration_ms']
                success_counts[model] += 1
        
        if len(durations) == 2:
            winner = min(durations, key=durations.get)
            loser = max(durations, key=durations.get)
            speedup = durations[loser] / durations[winner]
            print(f"  Winner: {winner} ({durations[winner]}ms)")
            print(f"  {winner} is {speedup:.2f}x faster than {loser}")
    
    # Overall average
    print(f"\n{'='*80}")
    print("OVERALL VISION PERFORMANCE:")
    print(f"{'='*80}")
    
    for model in models:
        if success_counts[model] > 0:
            avg = total_times[model] / success_counts[model]
            print(f"{model:20s}: {avg:6.0f}ms average ({success_counts[model]}/4 tests passed)")
    
    if all(success_counts[m] > 0 for m in models):
        avg_times = {m: total_times[m] / success_counts[m] for m in models}
        winner = min(avg_times, key=avg_times.get)
        loser = max(avg_times, key=avg_times.get)
        speedup = avg_times[loser] / avg_times[winner]
        
        print(f"\n{'='*80}")
        print(f"FINAL VERDICT: {winner} is {speedup:.2f}x faster for vision tasks")
        print(f"{'='*80}")
    
    # JSON compliance summary
    print(f"\n{'='*80}")
    print("JSON COMPLIANCE:")
    print(f"{'='*80}")
    
    for model in models:
        valid_count = sum(1 for test_name in test_names 
                         if all_results[model].get(test_name, {}).get("is_valid_json"))
        print(f"{model:20s}: {valid_count}/4 tests returned valid JSON")
    
    # Save detailed results
    output_file = f"critical_vision_tests_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nDetailed results saved to: {output_file}")

if __name__ == "__main__":
    main()
