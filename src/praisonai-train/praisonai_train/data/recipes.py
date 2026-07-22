"""Built-in generation recipes (pluggable Recipe implementations).

A recipe crosses diversity axes (task x topic x style x audience x variant) into
teacher prompts, so large runs stay diverse. Add a language/domain by registering
another class, or define one inline in YAML via ``CustomRecipe``.
"""
from __future__ import annotations

from praisonai_train.data.registry import recipes


class _AxisRecipe:
    """Shared fan-out over axes (first two axes are the task x topic grid)."""

    name = ""
    system = ""
    template = ""
    axes: dict = {}

    def prompts(self, n: int, start: int = 0) -> list[dict]:
        names = list(self.axes)
        grid = [(a, b) for a in self.axes[names[0]] for b in self.axes[names[1]]]
        styles = self.axes.get("style", [""])
        auds = self.axes.get("audience", [""])
        specs = []
        for i in range(start, start + n):
            task, topic = grid[i % len(grid)]
            specs.append({
                "system": self.system,
                "user": self.template.format(
                    task=task, topic=topic,
                    style=styles[i % len(styles)],
                    audience=auds[(i // max(len(styles), 1)) % len(auds)],
                    variant=i // len(grid),
                ),
            })
        return specs


@recipes.register
class Tamil(_AxisRecipe):
    name = "tamil"
    system = (
        "நீங்கள் உயர்தரமான தமிழ் மொழி பயிற்சித் தரவை உருவாக்கும் உதவியாளர். "
        "எப்போதும் இயல்பான, இலக்கணப் பிழையற்ற, தூய தமிழில் எழுதுங்கள். "
        "மொழிபெயர்ப்புப் பணிகளைத் தவிர வேறு எதிலும் ஆங்கிலம் கலக்காதீர்கள்."
    )
    template = (
        "பின்வரும் வகையிலான ஒரு தனித்துவமான தமிழ் பயிற்சி உதாரணத்தை உருவாக்குங்கள்.\n"
        "பணி வகை: {task}\nதலைப்பு: {topic}\nநடை: {style}\nஇலக்கு வாசகர்: {audience}\n"
        "மாறுபாடு எண்: {variant} — முந்தையவற்றிலிருந்து முற்றிலும் வேறுபட்ட புதிய உள்ளடக்கம்.\n\n"
        'வெளியீட்டை சரியாக இந்த JSON வடிவத்தில் மட்டும் தரவும்: '
        '{{"instruction": "...", "input": "", "output": "..."}}'
    )
    axes = {
        "task": ["ஒரு பொதுவான கேள்வி-பதில்", "ஒரு விளக்கம்", "ஒரு சுருக்கம்",
                 "ஆங்கிலத்திலிருந்து தமிழுக்கு மொழிபெயர்ப்பு", "படைப்பாக்க எழுத்து",
                 "நடைமுறை அறிவுரை", "பகுத்தறிவு/கணிதப் problem", "குறியீட்டு கேள்வி",
                 "கருத்து பகுப்பாய்வு", "படிப்படியான வழிகாட்டி"],
        "topic": ["தமிழ் இலக்கியம்", "வரலாறு", "அறிவியல்", "உடல்நலம்", "விவசாயம்",
                  "பொருளாதாரம்", "சினிமா", "உணவு", "கல்வி", "அன்றாட வாழ்க்கை",
                  "விளையாட்டு", "அரசியல்", "பயணம்", "மெய்யியல்", "தகவல் தொழில்நுட்பம்"],
        "style": ["எளிமையான", "விரிவான", "நடைமுறை சார்ந்த", "ஆழமான",
                  "உரையாடல் பாணி", "கதை வடிவ", "படிப்படியான", "கேள்வி-பதில் பாணி"],
        "audience": ["மாணவர்களுக்கு", "தொடக்கநிலையாளர்களுக்கு", "நிபுணர்களுக்கு",
                     "குழந்தைகளுக்கு", "பொது வாசகர்களுக்கு", "தொழில் வல்லுநர்களுக்கு"],
    }


class CustomRecipe(_AxisRecipe):
    """Build a recipe from a plain dict (e.g. loaded from YAML ``recipe:`` block)."""

    def __init__(self, spec: dict):
        self.name = spec.get("name", "custom")
        self.system = spec["system"]
        self.template = spec["template"]
        self.axes = spec["axes"]


def resolve(recipe) -> _AxisRecipe:
    """A recipe name (registered) or an inline dict -> a Recipe instance."""
    if isinstance(recipe, str):
        return recipes.get(recipe)
    if isinstance(recipe, dict):
        return CustomRecipe(recipe)
    return recipe
