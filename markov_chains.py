# markov_chains.py
import re
import random
from typing import List, Dict, Any, Optional

_word_split_re = re.compile(r"\s+")
_sentence_split_re = re.compile(r"[.!?]+\s*")

def _clean_token(tok: str) -> str:
    """Normalize token for keys: preserve custom emoji tokens, otherwise strip surrounding punctuation."""
    if not tok:
        return ""
    tok = tok.strip()
    # Preserve Discord custom emoji tokens like <:name:123456789> or <a:name:123...>
    if re.match(r"^<a?:[A-Za-z0-9_~]+:\d+>$", tok):
        return tok  # keep full emoji token unchanged
    # Otherwise only strip surrounding punctuation but keep internal punctuation like apostrophes
    if re.search(r"\w", tok):
        tok = re.sub(r"^[<>()[\]{}:;,\.\"]+|[<>()[\]{}:;,\.\"]+$", "", tok)
    return tok

class MarkovChains:
    def _filter_generated_text(self, text: str) -> str:
        """
        Clean generated text:
         - trim whitespace
         - remove/unwind unmatched parentheses/brackets/braces
         - remove unmatched quotes and markdown markers
         - trim leading/trailing punctuation
        """
        if not isinstance(text, str):
            return ""

        text = text.strip()

        # remove unmatched pairs like (), [], {}
        for a, b in [("(", ")"), ("[", "]"), ("{", "}")]:
            text = self._remove_unclosed_pairs(text, a, b)

        # remove unmatched quotes / markdown markers
        for ch in ('"', "'", "`", "*"):
            text = self._remove_unclosed_quotes(text, ch)

        # remove stray punctuation at start/end while preserving words
        import re
        if re.search(r"\w", text):
            text = re.sub(r'^[\.,;: ]+', '', text)
            text = re.sub(r'[, ]+$', '', text)

        return text

    def _remove_unclosed_quotes(self, text: str, char: str) -> str:
        """Remove the last unmatched quote-like char if count is odd."""
        if not isinstance(text, str) or not char:
            return text
        count = text.count(char)
        if count % 2 != 0:
            idx = text.rfind(char)
            if idx != -1:
                text = text[:idx] + text[idx+1:]
        return text

    def _remove_unclosed_pairs(self, text: str, open_ch: str, close_ch: str) -> str:
        """
        Remove unmatched closing/opening characters by deleting the offending one
        and re-checking until balanced.
        """
        if not isinstance(text, str):
            return text

        count = 0
        for i, ch in enumerate(text):
            if ch == open_ch:
                count += 1
            elif ch == close_ch:
                count -= 1
            if count < 0:
                # remove unmatched closing char and re-run
                text = text[:i] + text[i+1:]
                return self._remove_unclosed_pairs(text, open_ch, close_ch)

        if count > 0:
            # remove the first unmatched opening char and re-run
            for i, ch in enumerate(text):
                if ch == open_ch:
                    text = text[:i] + text[i+1:]
                    return self._remove_unclosed_pairs(text, open_ch, close_ch)

        return text

    """
    2-gram strict Markov chain (keys are pairs of consecutive words).
    word_list: Dict[key: str -> {"original": "<first token of key>", "list": [next_word, ...]}]
    """
    def __init__(self, word_list: Optional[Dict[str, Dict[str, List[str]]]] = None):
        self.word_list: Dict[str, Dict[str, List[str]]] = word_list if isinstance(word_list, dict) else {}

    def generate_dictionary(self, texts: List[Any]) -> None:
        """
        Build dictionary from texts.
        Accepts list[str] (legacy) or list[dict] entries like {"text": "...", "weight": N}.
        For strict 2-gram: keys are "word1 word2" and next is word3.
        """
        self.word_list = {}
        if not texts:
            return

        for item in texts:
            if isinstance(item, str):
                text = item
                weight = 1
            elif isinstance(item, dict):
                text = item.get("text", "") or ""
                try:
                    weight = max(1, int(item.get("weight", 1)))
                except Exception:
                    weight = 1
            else:
                try:
                    text = str(item)
                    weight = 1
                except Exception:
                    continue

            # apply weight by repeating _pick_sentence_words; simple and effective
            for _ in range(weight):
                self._pick_sentence_words(text)

    def generate_chain(self, max_words: int) -> str:
        """
        Generate text up to max_words tokens using strict 2-gram model.
        If model has no keys, returns empty string.
        """
        if not self.word_list:
            return ""

        keys = list(self.word_list.keys())
        if not keys:
            return ""

        # pick a starting key that has an 'original' token
        key = random.choice(keys)
        parts = key.split(" ", 1)
        if len(parts) != 2:
            return ""

        w1, w2 = parts[0], parts[1]
        generated = [w1, w2]

        for _ in range(max(0, int(max_words) - 2)):
            cur_key = f"{generated[-2]} {generated[-1]}"
            entry = self.word_list.get(cur_key)
            if not entry or not entry.get("list"):
                break
            next_word = random.choice(entry["list"])
            generated.append(next_word)

        return self._filter_generated_text(" ".join(generated))

    # ---------------- internal helpers ----------------
    def _pick_sentence_words(self, text: str) -> None:
        """Split text into sentences and feed each sentence to _pick_words_sentence."""
        if not text:
            return
        # naive sentence split but effective for chat-like data
        sentences = _sentence_split_re.split(text)
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            self._pick_words_sentence(s)

    def _pick_words_sentence(self, sentence: str) -> None:
        """Tokenize a sentence and record 2-gram->next_word transitions.
        Uses cleaned tokens for keys but stores original token strings in value lists
        so generated output preserves emojis and original formatting.
        """
        # split into raw tokens first
        raw_tokens = [t for t in _word_split_re.split(sentence.strip()) if t != ""]
        if len(raw_tokens) < 3:
            return  # need at least 3 tokens for a single 2-gram -> next mapping

        # produce cleaned tokens for keying
        cleaned = [_clean_token(t) for t in raw_tokens]
        # filter paired positions where cleaned tokens are empty
        # we still need length >=3 in cleaned to form at least one mapping
        # construct indices of usable tokens (non-empty cleaned)
        usable_indices = [i for i, c in enumerate(cleaned) if c != ""]

        # We require at least 3 usable cleaned tokens sequentially to map k1 k2 -> next
        # Iterate original indices but skip if cleaning removed tokens in between
        for i in range(len(raw_tokens) - 2):
            k1_clean = _clean_token(raw_tokens[i])
            k2_clean = _clean_token(raw_tokens[i + 1])
            nxt_raw = raw_tokens[i + 2]  # preserve raw token (with angle brackets if emoji)
            # must have non-empty cleaned keys to be useful
            if not k1_clean or not k2_clean:
                continue
            key = f"{k1_clean} {k2_clean}"
            if key not in self.word_list:
                # store original as the raw first token (so starts look natural)
                self.word_list[key] = {"original": raw_tokens[i], "list": []}
            # append the raw next-token, not the cleaned one, to preserve emoji and formatting
            self.word_list[key]["list"].append(nxt_raw)
    def _remove_unclosed_quotes(self, text: str, char: str) -> str:
        c = text.count(char)
        if c % 2 != 0:
            # remove last unmatched
            idx = text.rfind(char)
            if idx >= 0:
                text = text[:idx] + text[idx+1:]
        return text

    def _remove_unclosed_pairs(self, text: str, open_ch: str, close_ch: str) -> str:
        count = 0
        for i, ch in enumerate(text):
            if ch == open_ch:
                count += 1
            elif ch == close_ch:
                count -= 1
            if count < 0:
                # remove this unmatched close and restart
                text = text[:i] + text[i+1:]
                return self._remove_unclosed_pairs(text, open_ch, close_ch)
        if count > 0:
            # remove first unmatched open and restart
            for i, ch in enumerate(text):
                if ch == open_ch:
                    text = text[:i] + text[i+1:]
                    return self._remove_unclosed_pairs(text, open_ch, close_ch)
        return text
