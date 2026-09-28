"""Every user-facing string wrapped in _() must have a Spanish translation."""
import os
import re

from app.i18n import ES

ROOT = os.path.join(os.path.dirname(__file__), "..", "app")
PATTERN = re.compile(r"""_\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*[\)%]""")
DYNAMIC_PREFIXES = ("policy_", "tab_")


def collect_keys():
    keys = set()
    for base, _dirs, files in os.walk(ROOT):
        for f in files:
            if f.endswith((".html", ".py")) and f != "i18n.py":
                text = open(os.path.join(base, f), encoding="utf-8").read()
                for m in PATTERN.finditer(text):
                    k = m.group(1) if m.group(1) is not None else m.group(2)
                    keys.add(k.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n"))
    return keys


def test_all_strings_have_spanish():
    missing = sorted(k for k in collect_keys() if k not in ES and not k.startswith(DYNAMIC_PREFIXES))
    assert not missing, "Missing Spanish translations:\n" + "\n".join(missing)


def test_dynamic_keys_present():
    for k in ["policy_flexible", "policy_moderate", "policy_strict", "tab_overview", "tab_users", "tab_listings", "tab_bookings",
              "flexible", "moderate", "strict", "cleanliness", "accuracy", "communication", "location", "value", "active", "paused"]:
        assert k in ES, k
