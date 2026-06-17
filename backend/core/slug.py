"""Simple adjective-noun slug generator (ported from opencode)."""
import random

ADJECTIVES = [
    "brave", "calm", "clever", "cosmic", "crisp", "curious", "eager", "gentle",
    "glowing", "happy", "hidden", "jolly", "kind", "lucky", "mighty", "misty",
    "neon", "nimble", "playful", "proud", "quick", "quiet", "shiny", "silent",
    "stellar", "sunny", "swift", "tidy", "witty",
]

NOUNS = [
    "cabin", "cactus", "canyon", "circuit", "comet", "eagle", "engine", "falcon",
    "forest", "garden", "harbor", "island", "knight", "lagoon", "meadow", "moon",
    "mountain", "nebula", "orchid", "otter", "panda", "pixel", "planet", "river",
    "rocket", "sailor", "squid", "star", "tiger", "wizard", "wolf",
]


def create() -> str:
    """Generate a random adjective-noun slug."""
    return f"{random.choice(ADJECTIVES)}-{random.choice(NOUNS)}"
