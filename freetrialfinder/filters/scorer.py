import re
from typing import List, Optional, Tuple
from freetrialfinder.models import RawDeal, DealItem, ConfidenceLevel, DealCategory

AI_PROVIDERS = {
    "Anthropic": [r"\bclaude\b", r"\banthropic\b", r"\bsonnet\b", r"\bopus\b", r"\bhaiku\b"],
    "OpenAI": [r"\bopenai\b", r"\bchatgpt\b", r"\bgpt-4\b", r"\bgpt-4o\b", r"\bgpt-5\b", r"\bo1\b", r"\bo3\b"],
    "Google": [r"\bgemini\b", r"\bgoogle ai\b", r"\bgoogle cloud\b", r"\bvertex\b"],
    "OpenRouter": [r"\bopenrouter\b"],
    "Together AI": [r"\btogether\.?ai\b", r"\btogether ai\b"],
    "AWS Bedrock": [r"\bbedrock\b", r"\baws activate\b"],
    "Groq": [r"\bgroq\b"],
    "DeepInfra": [r"\bdeepinfra\b"],
    "Perplexity": [r"\bperplexity\b"],
    "Mistral": [r"\bmistral\b", r"\ble chat\b"],
}

IDE_INDICATORS = [
    (r"\bapi\b|\bapi key\b|\bbase_url\b|\bendpoint\b", 25, "mentions_api_endpoints"),
    (r"\bopenai[\s-]compatible\b", 30, "mentions_openai_compatible"),
    (r"\baide\b|\bcursor\b|\bcline\b|\baider\b|\bcontinue\.dev\b|\bvscode\b|\bide\b", 25, "mentions_ide_tools"),
    (r"\bcredits?\b|\btokens?\b|\bgrant\b|\bvoucher\b", 20, "mentions_credits_tokens"),
    (r"\bstartup program\b|\bactivate\b|\bfounders hub\b", 20, "mentions_cloud_startup_program"),
    (r"\bpromo(?:tion)?\b|\bcoupon\b|\bfree trial\b|\bfree tier\b", 15, "mentions_promo_or_trial"),
]

CHATBOT_ONLY_PENALTIES = [
    (r"\bchatbot\b", -20, "penalty_chatbot_wrapper"),
    (r"\bchat (?:on|in) (?:our |my )?website\b", -25, "penalty_website_only"),
    (r"\bweb chat ui only\b|\bchat interface only\b", -30, "penalty_chat_ui_only"),
    (r"\bno api(?: key)?\b", -35, "penalty_explicit_no_api"),
    (r"\bwhatsapp bot\b|\btelegram bot wrapper\b", -25, "penalty_messaging_bot_wrapper"),
    (r"\bcustom gpt\b", -20, "penalty_custom_gpt_wrapper"),
    (r"\bchat in (?:your )?browser\b|\bbrowser[- ]only\b", -25, "penalty_browser_only"),
]

CODE_PATTERNS = [
    r"(?:promo\s+code|coupon\s+code|voucher\s+code|code|promo|coupon|voucher)[:\s]+[\"']?([A-Z0-9_\-]{4,25})[\"']?",
    r"(?:use|enter)\s+(?:promo\s+code|coupon\s+code|code|promo|coupon)\s+[\"']?([A-Z0-9_\-]{4,25})[\"']?",
    r"\b([A-Z0-9]{4,15})\s+(?:for\s+\$?\d+|(?:gives|gets)\s+(?:you\s+)?\$?\d+)",
]

class DealScorer:
    """Evaluates raw deals for developer & IDE usability."""

    def __init__(self, min_score_threshold: int = 40):
        self.min_score_threshold = min_score_threshold

    def evaluate(self, raw: RawDeal) -> DealItem:
        full_text = f"{raw.title} {raw.content}".lower()
        score = 0
        reasons: List[str] = []

        # 1. Identify primary AI Provider
        detected_provider = "AI Provider"
        has_ai_mention = False
        for provider, patterns in AI_PROVIDERS.items():
            for p in patterns:
                if re.search(p, full_text):
                    detected_provider = provider
                    has_ai_mention = True
                    reasons.append(f"mentions_{provider.lower().replace(' ', '_')}")
                    score += 20
                    break
            if has_ai_mention:
                break

        # Check for general LLM / AI keywords if no specific provider matched
        if not has_ai_mention:
            if re.search(r"\b(?:llm|ai|artificial intelligence|language model)\b", full_text):
                has_ai_mention = True
                detected_provider = "General AI"
                score += 15
                reasons.append("mentions_general_ai")

        # If zero AI mention at all, severely cap score
        if not has_ai_mention:
            return DealItem(
                id=raw.id,
                title=raw.title,
                url=raw.url,
                source=raw.source,
                provider="None",
                category=DealCategory.API_CREDITS,
                confidence=ConfidenceLevel.REJECTED,
                score=10,
                reasons=["no_ai_provider_or_llm_detected"],
                summary=raw.content[:150] if raw.content else raw.title,
                discovered_at=raw.discovered_at,
            )

        # 2. Check IDE & API Indicators
        for pattern, points, reason_tag in IDE_INDICATORS:
            if re.search(pattern, full_text):
                score += points
                reasons.append(reason_tag)

        # 3. Check Anti-Chatbot Penalties (Leniently applied)
        for pattern, penalty, reason_tag in CHATBOT_ONLY_PENALTIES:
            if re.search(pattern, full_text):
                score += penalty
                reasons.append(reason_tag)

        # Clamp score to [0, 100]
        score = max(0, min(100, score))

        # 4. Extract Promo Code
        promo_code = self._extract_promo_code(f"{raw.title} {raw.content}")
        if promo_code:
            score = min(100, score + 10)
            reasons.append("has_promo_code")

        # 5. Extract Estimated Value ($ amount or duration)
        estimated_value = self._extract_value(f"{raw.title} {raw.content}")

        # 6. Determine Category
        category = self._categorize(full_text, promo_code)

        # 7. Determine Confidence Level (Carefully respecting user preference)
        if score >= 75:
            confidence = ConfidenceLevel.DIRECT_IDE
        elif score >= self.min_score_threshold:
            confidence = ConfidenceLevel.POTENTIAL
        else:
            confidence = ConfidenceLevel.REJECTED

        # Build clean summary
        summary = raw.content.strip() if raw.content else raw.title

        return DealItem(
            id=raw.id,
            title=raw.title,
            url=raw.url,
            source=raw.source,
            provider=detected_provider,
            category=category,
            confidence=confidence,
            score=score,
            reasons=reasons,
            promo_code=promo_code,
            estimated_value=estimated_value,
            summary=summary[:300],
            discovered_at=raw.discovered_at,
        )

    def _extract_promo_code(self, text: str) -> Optional[str]:
        for pat in CODE_PATTERNS:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                code = match.group(1).strip()
                # Ignore common words matched by accident
                if code.lower() not in {"free", "claude", "openai", "gemini", "online", "credits", "signup", "trial", "code", "coupon", "promo", "voucher"}:
                    return code.upper()
        return None

    def _extract_value(self, text: str) -> Optional[str]:
        val_match = re.search(r"(\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?|\b\d+\s?months?\b|\b\d+\s?days?\b)", text, re.IGNORECASE)
        if val_match:
            return val_match.group(1)
        return None

    def _categorize(self, text: str, promo_code: Optional[str]) -> DealCategory:
        if promo_code or "coupon" in text or "promo code" in text:
            return DealCategory.PROMO_CODE
        if "cloud" in text or "bedrock" in text or "azure" in text or "vertex" in text or "activate" in text:
            return DealCategory.CLOUD_CREDITS
        if "aide" in text or "cursor" in text or "cline" in text or "copilot" in text:
            return DealCategory.IDE_DISCOUNT
        if "free trial" in text or "trial" in text:
            return DealCategory.FREE_TRIAL
        if "openrouter" in text or "gateway" in text:
            return DealCategory.GATEWAY_TIER
        return DealCategory.API_CREDITS
