event_extractor_system_message = (
    "You are a precise financial-news research assistant. You only use the "
    "articles you are given, you never invent or modify a URL, and you always "
    "reply with one JSON object and nothing else."
)

event_extractor_user_message = """Below are recent "{event_type}" news articles. Find the SINGLE clearest,
most newsworthy {event_type} incident among them (one specific company, one specific event —
not a roundup or trend piece). If none of the articles describe a concrete incident, say so.

For the incident you pick, identify:
- the company it happened to directly (relation "direct")
- up to {max_knock_on_companies} other companies the market might react to because of it
  (competitors, suppliers, customers — relation "competitor" | "supplier" | "customer" | "other")
- for every company, your best guess of whether its stock would move "up", "down", or "unclear",
  made BEFORE knowing what actually happened to the price, with a one-line reason

Reply with exactly this JSON shape, nothing else:

{{
  "event_found": true,
  "headline": "one-line headline for the incident",
  "summary": "one plain-English sentence describing what happened",
  "event_date": "YYYY-MM-DD, the date the news broke",
  "source_url": "the URL of the article this is based on, copied EXACTLY as given below",
  "companies": [
    {{"company_name": "...", "relation": "direct", "expected_direction": "down", "reason": "..."}}
  ]
}}

If nothing in these articles describes a concrete incident, reply with exactly:
{{"event_found": false}}

Articles:
{article_block}
"""
