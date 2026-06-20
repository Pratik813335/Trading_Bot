import google.generativeai as genai
import json
import os

from ai.prompts import build_ohlcv_analysis_prompt
from core.signal_schema import build_signal_result
from config import GOOGLE_API_KEY

# Configure Gemini API
GEMINI_MODEL = None
if GOOGLE_API_KEY and GOOGLE_API_KEY != "YOUR_GEMINI_API_KEY":
    genai.configure(api_key=GOOGLE_API_KEY)
    GEMINI_MODEL = genai.GenerativeModel('gemini-pro')
else:
    print("WARNING: GOOGLE_API_KEY not found or is default. AI analysis will be disabled.")


def analyze_with_ai(symbol, timeframe, candles, rule_signal):
    if not GEMINI_MODEL:
        # Return the rule-based signal with AI disabled warnings
        return {
            "enabled": False,
            "provider": "gemini_disabled",
            "result": build_signal_result(
                # Pass all original fields from rule_signal
                **rule_signal,
                    reasons=rule_signal.get("reasons", []),
                    warnings=rule_signal.get("warnings", []),
                    analysis_mode="rule_based",
            ),
        }

    ai_analysis_raw = None
    ai_warnings = []
    ai_reasons = []
    ai_raw_text = ""

    try:
        prompt_payload = build_ohlcv_analysis_prompt(symbol, timeframe, rule_signal, candles)
        system_instruction = prompt_payload["system"]
        user_prompt_json_str = json.dumps(prompt_payload["user"], default=str) # Send user content as JSON string

        # Combine system instruction and user prompt for generate_content
        full_prompt_text = f"{system_instruction}\n\n{user_prompt_json_str}"
        response = GEMINI_MODEL.generate_content(full_prompt_text)
        ai_raw_text = response.text

        # Attempt to extract JSON from the raw text
        # Gemini often wraps JSON in markdown code blocks
        if '```json' in ai_raw_text:
            json_start = ai_raw_text.find('```json') + len('```json')
            json_end = ai_raw_text.find('```', json_start)
            if json_end != -1:
                json_str = ai_raw_text[json_start:json_end].strip()
            else:
                json_str = ai_raw_text[json_start:].strip() # Fallback if closing ``` is missing
        elif '```' in ai_raw_text:
            json_start = ai_raw_text.find('```') + 3
            json_end = ai_raw_text.find('```', json_start)
            if json_end != -1:
                json_str = ai_raw_text[json_start:json_end].strip()
            else:
                json_str = ai_raw_text[json_start:].strip()
        else:
            json_str = ai_raw_text.strip() # Assume it's just JSON

        ai_analysis_raw = json.loads(json_str)
        ai_reasons.append("AI analysis successfully retrieved.")

    except Exception as e:
        ai_warnings.append(f"AI analysis failed: {e}")
        ai_warnings.append(f"AI raw response (if any): {ai_raw_text if ai_raw_text else 'N/A'}")

    # Merge AI analysis with rule-based signal
    final_signal_result = rule_signal.copy() # Start with the rule-based signal
    final_signal_result["ai_raw_output"] = ai_analysis_raw # Store raw AI output for debugging/display

    # Add AI-generated reasons and warnings
    final_signal_result["reasons"].extend(ai_reasons)
    final_signal_result["warnings"].extend(ai_warnings)

    if ai_analysis_raw:
        # Update signal result with AI's insights, prioritizing AI for certain fields if confident
        # This is a simple merge; a more sophisticated approach might involve confidence thresholds
        final_signal_result["signal"] = ai_analysis_raw.get("signal", final_signal_result["signal"])
        final_signal_result["confidence"] = max(final_signal_result["confidence"], ai_analysis_raw.get("confidence", 0))
        final_signal_result["entry"] = ai_analysis_raw.get("entry", final_signal_result["entry"])
        final_signal_result["stop_loss"] = ai_analysis_raw.get("stop_loss", final_signal_result["stop_loss"])
        final_signal_result["take_profit"] = ai_analysis_raw.get("take_profit", final_signal_result["take_profit"])
        final_signal_result["risk_reward"] = ai_analysis_raw.get("risk_reward", final_signal_result["risk_reward"])
        final_signal_result["trend"] = ai_analysis_raw.get("trend", final_signal_result["trend"])
        final_signal_result["explanation"] = ai_analysis_raw.get("explanation", "")

        # Add AI's explanation and risk warning to reasons/warnings
        if ai_analysis_raw.get("explanation"):
            final_signal_result["reasons"].append(f"AI Explanation: {ai_analysis_raw['explanation']}")
        if ai_analysis_raw.get("risk_warning"):
            final_signal_result["warnings"].append(f"AI Risk Warning: {ai_analysis_raw['risk_warning']}")

        # Update data source to reflect AI involvement
        final_signal_result["data_source"] = "ai_validated_rule_engine"
        final_signal_result["analysis_mode"] = "ai_assisted"
    else:
        final_signal_result["warnings"].append("AI analysis could not be integrated due to errors or empty response.")

    return {
        "enabled": True, # AI module is enabled, even if analysis failed
        "provider": "gemini",
        "result": final_signal_result,
    }
