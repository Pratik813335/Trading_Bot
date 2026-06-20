import json

from ai.prompts import build_gemini_validation_prompt
from config import GEMINI_MODEL_NAME, GOOGLE_API_KEY

try:
    import google.generativeai as genai
except Exception:
    genai = None


class AIExplanationService:
    def __init__(self):
        self.provider = "gemini"
        self.model_name = GEMINI_MODEL_NAME
        self.model = None
        self.enabled = False
        self.disabled_reason = ""

        if not GOOGLE_API_KEY or GOOGLE_API_KEY == "YOUR_GEMINI_API_KEY":
            self.disabled_reason = "GOOGLE_API_KEY is not configured"
            return

        if genai is None:
            self.disabled_reason = "google-generativeai package is not installed"
            return

        try:
            genai.configure(api_key=GOOGLE_API_KEY)
            self.model = genai.GenerativeModel(self.model_name)
            self.enabled = True
        except Exception as exc:
            self.disabled_reason = f"Gemini initialization failed: {exc}"

    def _fallback_response(self, signal):
        risks = list(signal.warnings)
        if signal.chart_sync < 99:
            risks.append("Chart sync is below 99%")
        if signal.structure.get("phase") == "consolidation":
            risks.append("Structure is consolidating, which may reduce follow-through")

        confidence_adjustment = 0
        if signal.chart_sync < 99:
            confidence_adjustment -= 15
        if signal.structure.get("strength", 0) < 0.5:
            confidence_adjustment -= 5

        explanation = (
            f"{signal.signal} on {signal.symbol} {signal.timeframe} is based on "
            f"{', '.join(signal.reasons[:3]) if signal.reasons else 'limited confirmations'}."
        )
        status = "disabled" if not self.enabled else "fallback"
        warnings = []

        return {
            "provider": self.provider,
            "model": self.model_name,
            "enabled": self.enabled,
            "status": status,
            "validation_passed": False if status == "disabled" else True,
            "explanation": explanation,
            "summary": explanation,
            "warnings": warnings,
            "risks": risks[:5],
            "confidence_adjustment": confidence_adjustment,
        }

    def _extract_json(self, raw_text):
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            start = cleaned.find("```json") + len("```json")
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end if end != -1 else None].strip()
        elif cleaned.startswith("```"):
            start = cleaned.find("```") + 3
            end = cleaned.find("```", start)
            cleaned = cleaned[start:end if end != -1 else None].strip()
        return json.loads(cleaned)

    def explain(self, signal, trade_payload=None, candles=None, sync_status=None):
        fallback = self._fallback_response(signal)
        if not self.enabled or self.model is None or trade_payload is None or candles is None or sync_status is None:
            return fallback

        prompt = build_gemini_validation_prompt(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            trade_payload=trade_payload,
            candles=candles,
            sync_status=sync_status,
        )
        raw_text = ""
        try:
            full_prompt = f"{prompt['system']}\n\n{json.dumps(prompt['user'])}"
            response = self.model.generate_content(full_prompt)
            raw_text = getattr(response, "text", "") or ""
            payload = self._extract_json(raw_text)
            status = payload.get("status", "validated")
            validation_passed = bool(payload.get("validation_passed", status != "rejected"))
            explanation = payload.get("summary") or fallback["explanation"]
            return {
                "provider": self.provider,
                "model": self.model_name,
                "enabled": True,
                "status": status,
                "validation_passed": validation_passed,
                "explanation": explanation,
                "summary": explanation,
                "warnings": list(payload.get("warnings") or []),
                "risks": list(payload.get("risks") or [])[:5],
                "confidence_adjustment": int(payload.get("confidence_adjustment", 0)),
                "raw_response": raw_text,
            }
        except Exception as exc:
            fallback["status"] = "error"
            fallback["warnings"] = list(fallback.get("warnings") or []) + [f"Gemini validation failed: {exc}"]
            if raw_text:
                fallback["warnings"].append(f"Gemini raw response: {raw_text[:500]}")
            return fallback
