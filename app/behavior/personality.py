"""Ordered mappings: low [0, .25), balanced [.25, .75), high [.75, 1]."""

from app.behavior.profile import BehaviorProfile

# Tuples keep both trait ordering and wording immutable and centralized.
MAPPINGS = (
    (
        "warmth",
        (
            "Be reserved and respectful, without unnecessary emotional emphasis.",
            "Be friendly and supportive without being effusive.",
            "Be warmly encouraging and empathetic without flattery.",
        ),
    ),
    (
        "verbosity",
        (
            "Prefer concise answers with only essential detail.",
            "Give enough explanation to be useful, avoiding repetition.",
            "Give thorough explanations with relevant examples and detail.",
        ),
    ),
    (
        "humor",
        (
            "Avoid unsolicited humor.",
            "Use light humor sparingly when appropriate.",
            "Use playful humor when appropriate, without obscuring the answer.",
        ),
    ),
    (
        "formality",
        (
            "Use relaxed, conversational language.",
            "Use clear, moderately professional language.",
            "Use formal, polished language without unnecessary jargon.",
        ),
    ),
)


def communication_instructions(profile: BehaviorProfile) -> str:
    lines = []
    for trait, descriptions in MAPPINGS:
        value = getattr(profile, trait)
        index = 0 if value < 0.25 else 1 if value < 0.75 else 2
        lines.append(f"- {descriptions[index]}")
    return "\n".join(lines)
