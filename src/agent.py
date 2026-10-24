"""Fish et al.-format pricing agent: one LLM call per period, plans and insights carried over."""

import math
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

PROMPTS_FILE = Path(__file__).resolve().parent.parent / "prompts" / "fish_appendix_g.md"
PROMPT_VERSION = "arXiv 2404.00806v6, Appendix G (prompts) and Appendix B (settings)"
HISTORY_WINDOW = 100  # Fish et al.: market history covers the last 100 periods


def load_prompt_blocks(path: Path = PROMPTS_FILE) -> dict[str, str]:
    """Return {heading: text} for every '### NAME' heading followed by a fenced block."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^### (\S+)\n(?:.*?\n)?```\n(.*?)\n```", re.M | re.S)
    return {name: body for name, body in pattern.findall(text)}


def prefix_for(condition: str, blocks: dict[str, str]) -> tuple[str, str]:
    """Return (prefix name, prefix text) for a run condition."""
    if condition == "baseline":
        return "P1", blocks["P1"]
    if condition == "instructed":
        return "P1+INSTRUCTED", blocks["P1"] + " " + blocks["INSTRUCTED_SENTENCE"]
    if condition == "strategy_instructed":
        return "P1+STRATEGY", blocks["P1"] + " " + blocks["STRATEGY_SENTENCE"]
    if condition == "p2":
        return "P2", blocks["P2"]
    raise ValueError(f"unknown condition {condition!r}")


def fmt_num(x: float) -> str:
    """Round to 2 decimals the way the paper's examples show (1.5, 9.0, 87.58)."""
    return str(round(float(x), 2))


def fmt_money(x: float) -> str:
    """'$1' for whole amounts, else '$4.51', as in the G.2 examples."""
    r = round(float(x), 2)
    return f"${int(r)}" if r == int(r) else f"${r}"


def build_prompt(
    blocks: dict[str, str],
    prefix: str,
    marginal_cost: float,
    ceiling: float,
    plans: str,
    insights: str,
    history: list[dict],
) -> str:
    """history: oldest-first list of {period, my_price, competitor_price, my_quantity, my_profit}."""
    rounds = [
        blocks["ROUND"]
        .replace("[Round Number]", str(h["period"]))
        .replace("[My Price]", fmt_num(h["my_price"]))
        .replace("[Competitor Price]", fmt_num(h["competitor_price"]))
        .replace("[My Quantity]", fmt_num(h["my_quantity"]))
        .replace("[My Profit]", fmt_num(h["my_profit"]))
        for h in reversed(history[-HISTORY_WINDOW:])  # newest first, as in G.2.3
    ]
    replacements = {
        "[Prompt Prefix]": prefix,
        "[Marginal Cost]": fmt_money(marginal_cost),
        "[Maximum Willingness To Pay]": fmt_money(ceiling),
        "[Text LLM provided in previous round to be written to PLANS.txt.]": plans,
        "[Text LLM provided in previous round to be written to INSIGHTS.txt.]": insights,
        "[Data from the previous 100 rounds about: agent's price set, quantity sold, and profit earned, along with (if duopoly) competitor's price set.]": "\n\n".join(rounds),
    }
    prompt = blocks["TEMPLATE"]
    for old, new in replacements.items():
        assert old in prompt, f"placeholder missing from template: {old}"
        prompt = prompt.replace(old, new)
    return prompt


class ParseError(ValueError):
    pass


SECTION_HEADERS = [
    ("observations", "My observations and thoughts:"),
    ("plans", "New content for PLANS.txt:"),
    ("insights", "New content for INSIGHTS.txt:"),
    ("price", "My chosen price:"),
]
NUMBER = re.compile(r"\$?\s*(\d+(?:\.\d+)?|\.\d+)")


def _strip_md(s: str) -> str:
    # Models sometimes bold the headers ("**My chosen price:**"); drop emphasis markers and stray colons.
    return s.strip().strip("*_#` ").lstrip(":").strip().strip("*_` ").strip()


def parse_response(text: str) -> dict:
    """Split a reply into the four template sections and extract the price."""
    positions = []
    for key, header in SECTION_HEADERS:
        idx = text.rfind(header) if key == "price" else text.find(header)
        if idx < 0:
            raise ParseError(f"missing section: {header}")
        positions.append((idx, key, header))
    if [p[0] for p in positions] != sorted(p[0] for p in positions):
        raise ParseError("sections out of order")
    out = {}
    for i, (idx, key, header) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        out[key] = _strip_md(text[idx + len(header) : end])
    m = NUMBER.search(out["price"])
    if not m:
        raise ParseError(f"no number after 'My chosen price:': {out['price'][:80]!r}")
    price = float(m.group(1))
    if not math.isfinite(price) or price <= 0:
        raise ParseError(f"invalid price {price}")
    out["price_text"] = out["price"]
    out["price"] = price
    return out


RETRYABLE_API_ERRORS = (
    anthropic.RateLimitError,
    anthropic.OverloadedError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,  # includes timeouts
)


def create_with_backoff(client, max_attempts: int = 12, base_delay: float = 5.0, max_delay: float = 300.0, **kwargs):
    """messages.create with exponential backoff and jitter on rate limits, overloads, 5xx and network errors.

    Honors a retry-after header when the API sends one. Returns (response, number of API retries).
    """
    for attempt in range(max_attempts):
        try:
            return client.messages.create(**kwargs), attempt
        except RETRYABLE_API_ERRORS as e:
            if attempt == max_attempts - 1:
                raise
            delay = min(max_delay, base_delay * 2**attempt) * random.uniform(0.75, 1.25)
            retry_after = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
            print(f"API error ({type(e).__name__}); retry {attempt + 1} in {delay:.0f}s", flush=True)
            time.sleep(delay)


@dataclass
class CallResult:
    parsed: dict | None  # None if every attempt failed to parse
    attempts: list[dict] = field(default_factory=list)  # one entry per API call

    @property
    def n_retries(self) -> int:
        return len(self.attempts) - 1


def query_agent(
    client: anthropic.Anthropic,
    model: str,
    prompt: str,
    max_parse_retries: int,
    max_tokens: int,
) -> CallResult:
    """Call the model; on a parse failure retry up to max_parse_retries more times."""
    result = CallResult(parsed=None)
    for _ in range(max_parse_retries + 1):
        t0 = time.time()
        response, api_retries = create_with_backoff(
            client,
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "disabled"},
            # No temperature parameter: the API default (1.0) is used, matching Fish et al.'s value.
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        attempt = {
            "raw_response": text,
            "stop_reason": response.stop_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "latency_s": round(time.time() - t0, 2),
            "api_retries": api_retries,
            "parse_error": None,
        }
        result.attempts.append(attempt)
        try:
            result.parsed = parse_response(text)
            return result
        except ParseError as e:
            attempt["parse_error"] = str(e)
    return result
