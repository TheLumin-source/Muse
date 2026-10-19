"""Starter boards.

Each template is a small builder that lays out cards on a grid. A template can
carry nested sub-boards, so "Game design document" arrives as a hub board with
real boards behind each section rather than one enormous canvas.

Adding one is a function plus an entry in TEMPLATES; nothing else knows about
the specifics.
"""

from __future__ import annotations

from typing import Callable

# Layout grid. Cards are placed in columns 270 apart, rows 190 apart.
COL = 270
ROW = 190
X0, Y0 = 120, 190


def gx(column: int) -> int:
    return X0 + column * COL


def gy(row: int) -> int:
    return Y0 + row * ROW


class Board:
    """Terse builder for one board's worth of cards."""

    def __init__(self, title: str):
        self.title = title
        self.elements: list[dict] = []
        self.connectors: list[dict] = []
        self.children: list[Board] = []

    # -- cards --------------------------------------------------------------

    def _add(self, kind: str, x: int, y: int, w: int, h: int, **rest) -> str:
        key = rest.pop("key", None) or f"k{len(self.elements)}"
        self.elements.append({"key": key, "type": kind, "x": int(x), "y": int(y),
                              "w": int(w), "h": int(h), **rest})
        return key

    def head(self, x: int, y: int, text: str, w: int = 460, h: int = 54) -> str:
        return self._add("text", x, y, w, h, text=text, color="none")

    def note(self, x: int, y: int, title: str = "", text: str = "",
             w: int = 240, h: int = 160, color: str = "white", key: str | None = None) -> str:
        return self._add("note", x, y, w, h, title=title, text=text, color=color, key=key)

    def todo(self, x: int, y: int, title: str, items: list[str],
             w: int = 250, color: str = "white", key: str | None = None) -> str:
        height = max(120, 62 + len(items) * 24)
        rows = [{"id": f"t{i}", "text": text, "done": False} for i, text in enumerate(items)]
        return self._add("todo", x, y, w, height, title=title, items=rows,
                         color=color, key=key)

    def image(self, x: int, y: int, w: int = 240, h: int = 170,
              caption: str = "", key: str | None = None) -> str:
        """An empty image card. Drop a picture straight onto it to fill it."""
        return self._add("image", x, y, w, h, src="", caption=caption, key=key)

    def strip(self, x: int, y: int, count: int, w: int = 175, h: int = 130,
              gap: int = 12, caption: str = "") -> list[str]:
        return [self.image(x + i * (w + gap), y, w, h, caption) for i in range(count)]

    def column(self, x: int, y: int, title: str, cards: list[tuple[str, str]],
               w: int = 260, color: str = "slate") -> str:
        """A column with simple note cards inside it."""
        key = self._add("column", x, y, w, 300, title=title, color=color, children=[])
        children = []
        for index, (card_title, card_text) in enumerate(cards):
            child = self.note(x + 10, y + 40 + index * 90, card_title, card_text,
                              w=w - 20, h=80)
            self.elements[-1]["parent"] = key
            children.append(child)
        for element in self.elements:
            if element["key"] == key:
                element["children"] = children
        return key

    def board(self, x: int, y: int, sub: "Board", w: int = 210, h: int = 150,
              color: str = "white") -> str:
        """A card that opens a nested board built by `sub`."""
        self.children.append(sub)
        return self._add("board", x, y, w, h, title=sub.title, color=color,
                         child=len(self.children) - 1)

    def wire(self, source: str, target: str) -> None:
        self.connectors.append({"from": source, "to": target})

    # -- output -------------------------------------------------------------

    def spec(self) -> dict:
        return {
            "title": self.title,
            "elements": self.elements,
            "connectors": self.connectors,
            "children": [child.spec() for child in self.children],
        }


# --- game design -----------------------------------------------------------


def game_design_document() -> Board:
    b = Board("Game design document")
    b.head(gx(0), 100, "Game design document")
    b.note(gx(0), gy(0), "The pitch", "One sentence a stranger would understand. "
           "Genre, hook, and who it is for.", color="yellow", h=180)
    b.note(gx(1), gy(0), "Pillars", "Three things this game must always be. "
           "Every later decision gets checked against these.", color="orange", h=180)
    b.todo(gx(2), gy(0), "Milestones", [
        "Vertical slice", "Playable loop", "Content complete", "Polish", "Ship"])
    b.board(gx(0), gy(1), game_mechanics(), w=230)
    b.board(gx(0) + 250, gy(1), world_building(), w=230)
    b.board(gx(1) + 230, gy(1), character_profile(), w=230)
    b.board(gx(2) + 210, gy(1), level_design(), w=230)
    b.board(gx(0), gy(2) - 20, game_moodboard(), w=230)
    b.board(gx(0) + 250, gy(2) - 20, game_story_outline(), w=230)
    return b


def game_mechanics() -> Board:
    b = Board("Mechanics")
    b.head(gx(0), 100, "Mechanics and rules")
    b.note(gx(0), gy(0), "Core loop", "What the player does over and over. "
           "Thirty seconds of it, described plainly.", color="yellow", h=180)
    b.note(gx(1), gy(0), "Verbs", "Every action the player can take. "
           "If a verb has no interesting consequence, cut it.", h=180)
    b.note(gx(2), gy(0), "Progression", "What opens up over time, and what the "
           "player earns for the effort.", color="green", h=180)
    b.column(gx(0), gy(1), "Systems", [
        ("System", "What it does and what feeds it"),
        ("System", "What it does and what feeds it"),
    ])
    b.column(gx(1), gy(1), "Open questions", [
        ("Question", "The thing you are not sure about yet"),
        ("Question", "The thing you are not sure about yet"),
    ])
    b.note(gx(2), gy(1), "Cut list", "Ideas parked on purpose, with the reason. "
           "Saves relitigating them in month four.", color="slate", h=180)
    return b


def world_building() -> Board:
    b = Board("World building")
    b.head(gx(0), 100, "The world")
    b.note(gx(0), gy(0), "Premise", "Where and when this is, and the one rule "
           "that makes it different from ours.", color="purple", h=180)
    b.note(gx(1), gy(0), "History", "The three events everyone in this world "
           "knows about.", h=180)
    b.note(gx(2), gy(0), "Factions", "Who wants what, and who is in their way.", h=180)
    b.head(gx(0), gy(1) - 40, "Look and feel", w=300)
    b.strip(gx(0), gy(1), 4, caption="Reference")
    b.note(gx(0), gy(2), "Rules of the world", "What is possible here, what is "
           "forbidden, and what it costs.", w=380, h=160, color="teal")
    return b


def character_profile() -> Board:
    b = Board("Characters")
    b.head(gx(0), 100, "Characters")
    for index in range(3):
        x = gx(index)
        b.image(x, gy(0), 240, 190, "Portrait")
        b.note(x, gy(0) + 205, "Name", "Role in the story. What they want, and "
               "what they are afraid of.", h=170, color=["yellow", "blue", "green"][index])
    b.note(gx(0), gy(2) + 40, "Relationships", "Who trusts who, who owes who, "
           "and where that breaks. Join the cards above with arrows.",
           w=380, h=150, color="slate")
    return b


def character_relationships() -> Board:
    b = Board("Character relationships")
    b.head(gx(0), 100, "Who is tied to who")
    a = b.note(gx(1), gy(0), "Protagonist", "What they want", color="yellow")
    c = b.note(gx(0), gy(1), "Ally", "What they want from the protagonist", color="green")
    d = b.note(gx(2), gy(1), "Antagonist", "What they want instead", color="pink")
    e = b.note(gx(1), gy(2), "Wildcard", "Loyal to neither, useful to both", color="purple")
    for target in (c, d, e):
        b.wire(a, target)
    b.wire(c, d)
    return b


def game_story_outline() -> Board:
    b = Board("Story outline")
    b.head(gx(0), 100, "Story outline")
    beats = [
        ("Opening", "The ordinary state of things, and the crack in it"),
        ("Inciting incident", "What forces the player to act"),
        ("Rising action", "The complications, in order"),
        ("Midpoint", "The turn where the goal changes shape"),
        ("Climax", "The hardest version of the central problem"),
        ("Resolution", "What the world looks like afterwards"),
    ]
    previous = None
    for index, (title, text) in enumerate(beats):
        key = b.note(gx(index % 3), gy(index // 3), title, text, color="white")
        if previous:
            b.wire(previous, key)
        previous = key
    return b


def game_moodboard() -> Board:
    b = Board("Moodboard")
    b.head(gx(0), 100, "Look, feel, palette")
    b.strip(gx(0), gy(0), 4, w=200, h=150, caption="Reference")
    b.strip(gx(0), gy(0) + 165, 4, w=200, h=150, caption="Reference")
    b.note(gx(0), gy(2), "In three words", "The feeling a screenshot should "
           "give someone who knows nothing about it.", w=280, h=140, color="yellow")
    b.note(gx(0) + 300, gy(2), "Palette", "Drop images here and pull the colours "
           "you keep coming back to.", w=280, h=140, color="teal")
    b.note(gx(0) + 600, gy(2), "Not this", "References for what it must never "
           "look like. As useful as the yes pile.", w=280, h=140, color="slate")
    return b


def game_brainstorm() -> Board:
    b = Board("Game brainstorm")
    b.head(gx(0), 100, "Everything on the table")
    b.note(gx(0), gy(0), "Mechanics", "", color="yellow", h=170)
    b.note(gx(1), gy(0), "Setting", "", color="purple", h=170)
    b.note(gx(2), gy(0), "Characters", "", color="blue", h=170)
    b.note(gx(0), gy(1), "Art direction", "", color="pink", h=170)
    b.note(gx(1), gy(1), "Sound", "", color="teal", h=170)
    b.note(gx(2), gy(1), "Things I loved in other games", "", color="green", h=170)
    b.note(gx(0), gy(2), "Nothing gets judged on this board. Sort it later, "
           "fill it now.", w=380, h=110, color="slate")
    return b


def level_design() -> Board:
    b = Board("Level design")
    b.head(gx(0), 100, "Level design")
    b.image(gx(0), gy(0), 500, 300, "Layout sketch")
    b.todo(gx(2) + 30, gy(0), "Beats", [
        "Teach the mechanic safely",
        "Test it with a small cost",
        "Combine it with something known",
        "Raise the stakes",
        "Pay it off",
    ])
    b.column(gx(0), gy(2) - 40, "Encounters", [
        ("Encounter", "What the player meets, and what it teaches"),
        ("Encounter", "What the player meets, and what it teaches"),
    ])
    b.note(gx(1), gy(2) - 40, "Pacing", "Where it goes loud, where it goes quiet. "
           "Players need the quiet to notice the loud.", h=180)
    b.note(gx(2), gy(2) - 40, "Ways through", "Every route a player might take, "
           "including the one you did not intend.", h=180, color="orange")
    return b


def game_flow_chart() -> Board:
    b = Board("Game flow")
    b.head(gx(0), 100, "Flow from launch to credits")
    boot = b.note(gx(0), gy(0), "Boot", "Splash, then straight in", w=200, h=110, color="slate")
    menu = b.note(gx(1), gy(0), "Main menu", "New, continue, options", w=200, h=110)
    play = b.note(gx(2), gy(0), "Core loop", "Where the game actually lives",
                  w=200, h=110, color="yellow")
    pause = b.note(gx(1), gy(1), "Pause", "What can be changed mid-run", w=200, h=110)
    over = b.note(gx(2), gy(1), "Run ends", "What carries over to the next one",
                  w=200, h=110, color="pink")
    b.wire(boot, menu)
    b.wire(menu, play)
    b.wire(play, pause)
    b.wire(play, over)
    b.wire(over, menu)
    return b


def game_storyboard() -> Board:
    b = Board("Storyboard")
    b.head(gx(0), 100, "Shot by shot")
    for row in range(2):
        frames = b.strip(gx(0), gy(row) + row * 40, 4, w=200, h=150, caption="Frame")
        for index, frame in enumerate(frames):
            b.note(gx(0) + index * 212, gy(row) + row * 40 + 158, "", "What happens, "
                   "and what the player hears", w=200, h=90, color="white")
    return b


def game_marketing() -> Board:
    b = Board("Launch plan")
    b.head(gx(0), 100, "Getting it in front of people")
    b.note(gx(0), gy(0), "The one line", "How you describe it in a tweet without "
           "using the word 'unique'.", color="yellow", h=170)
    b.note(gx(1), gy(0), "Who it is for", "The player who will love this, "
           "specifically. Not 'everyone'.", h=170)
    b.note(gx(2), gy(0), "Where they are", "Communities, creators and press who "
           "already cover this kind of thing.", h=170)
    b.todo(gx(0), gy(1), "Before launch", [
        "Store page up", "Trailer cut", "Press kit ready",
        "Wishlist push", "Demo or playtest",
    ])
    b.todo(gx(1), gy(1), "Launch week", [
        "Post everywhere at once", "Reply to everything",
        "Watch the first streams", "Patch what breaks",
    ])
    b.column(gx(2), gy(1), "Assets", [
        ("Trailer", "Length, beats, music"),
        ("Screenshots", "The five that sell it"),
    ])
    return b


# --- graphic design and branding -------------------------------------------


def design_brief() -> Board:
    b = Board("Design brief")
    b.head(gx(0), 100, "Design brief")
    b.note(gx(0), gy(0), "Client", "Who they are and what they actually sell.",
           color="slate", h=170)
    b.note(gx(1), gy(0), "The job", "What is being made, in one sentence, with "
           "the deliverables named.", color="yellow", h=170)
    b.note(gx(2), gy(0), "Audience", "Who has to respond to this, and what they "
           "already think.", h=170)
    b.note(gx(0), gy(1), "Must haves", "Non-negotiables: sizes, formats, "
           "wordmarks, legal.", color="orange", h=170)
    b.note(gx(1), gy(1), "Tone", "Five adjectives. Then the five it must not be.", h=170)
    b.todo(gx(2), gy(1), "Deliverables", [
        "Concepts presented", "Revisions agreed", "Final files",
        "Source files handed over",
    ])
    b.note(gx(0), gy(2), "Budget and dates", "What was quoted, what is due when, "
           "and what pushes the date.", w=380, h=150, color="pink")
    return b


def design_project_plan() -> Board:
    b = Board("Project plan")
    b.head(gx(0), 100, "Project plan")
    b.column(gx(0), gy(0), "This week", [("Task", "")], color="slate")
    b.column(gx(1), gy(0), "In progress", [("Task", "")], color="blue")
    b.column(gx(2), gy(0), "Waiting on client", [("Task", "")], color="orange")
    b.column(gx(3), gy(0), "Done", [("Task", "")], color="green")
    b.note(gx(0), gy(2) + 60, "Dates that matter", "Kick-off, first presentation, "
           "sign-off, delivery.", w=380, h=140, color="yellow")
    return b


def moodboard() -> Board:
    b = Board("Moodboard")
    b.head(gx(0), 100, "Moodboard")
    b.strip(gx(0), gy(0), 5, w=200, h=150, caption="Reference")
    b.strip(gx(0), gy(0) + 165, 5, w=200, h=150, caption="Reference")
    b.note(gx(0), gy(2), "Direction", "What these images have in common, said "
           "out loud. This is the bit clients actually read.",
           w=430, h=150, color="yellow")
    b.note(gx(0) + 450, gy(2), "Type and colour", "Faces and palettes pulled from "
           "the references above.", w=430, h=150, color="teal")
    return b


def brand_strategy() -> Board:
    b = Board("Brand strategy")
    b.head(gx(0), 100, "Brand strategy")
    b.note(gx(0), gy(0), "Purpose", "Why this exists beyond making money.",
           color="yellow", h=170)
    b.note(gx(1), gy(0), "Positioning", "For [audience] who [need], this is the "
           "[category] that [difference].", color="orange", h=170)
    b.note(gx(2), gy(0), "Values", "Three, and each one has to be a thing you "
           "could plausibly not believe.", h=170)
    b.note(gx(0), gy(1), "Voice", "How it talks. Two examples of right, one of "
           "wrong.", color="purple", h=170)
    b.note(gx(1), gy(1), "Competitors", "Who else is in this space and what they "
           "have already claimed.", h=170)
    b.note(gx(2), gy(1), "Proof", "The evidence that any of the above is true.",
           color="green", h=170)
    return b


def brand_assets() -> Board:
    b = Board("Brand assets")
    b.head(gx(0), 100, "Brand assets")
    b.image(gx(0), gy(0), 340, 220, "Primary logo")
    b.image(gx(0) + 355, gy(0), 165, 105, "Mark")
    b.image(gx(0) + 355, gy(0) + 115, 165, 105, "Reversed")
    b.note(gx(2) + 60, gy(0), "Colour", "Hex values, and where each one is "
           "allowed to be used.", h=220, color="teal")
    b.note(gx(0), gy(1) + 60, "Type", "Families, weights, and the sizes that "
           "actually get used.", h=170, color="slate")
    b.note(gx(1), gy(1) + 60, "Clear space", "The minimum breathing room, and "
           "the smallest size it still reads at.", h=170)
    b.todo(gx(2), gy(1) + 60, "Files handed over", [
        "SVG", "PNG on transparent", "Favicon set", "Social avatars", "Print PDF",
    ])
    return b


def logo_design() -> Board:
    b = Board("Logo design")
    b.head(gx(0), 100, "Logo design")
    b.note(gx(0), gy(0), "Brief", "What it has to say, where it has to work, "
           "and what it must never look like.", color="yellow", h=180)
    b.note(gx(1), gy(0), "Words", "Everything the brand is about, written out. "
           "Marks come from words.", h=180)
    b.note(gx(2), gy(0), "References", "Marks you admire, and the reason, which "
           "matters more than the mark.", h=180)
    b.head(gx(0), gy(1) - 30, "Concepts", w=300)
    b.strip(gx(0), gy(1) + 20, 4, w=200, h=200, caption="Concept")
    b.note(gx(0), gy(2) + 60, "Where it has to survive", "Favicon, embroidery, "
           "one colour, on a photograph, at 16px.", w=430, h=140, color="orange")
    return b


def concept_presentation() -> Board:
    b = Board("Concept presentation")
    b.head(gx(0), 100, "Presentation")
    b.note(gx(0), gy(0), "The problem", "In the client's own words, so they know "
           "they were heard.", color="slate", h=170)
    b.note(gx(1), gy(0), "The approach", "The thinking, before any picture. "
           "This is what you are actually selling.", color="yellow", h=170)
    b.image(gx(2), gy(0), 300, 220, "Hero image")
    b.head(gx(0), gy(1) + 40, "Concepts", w=300)
    for index in range(3):
        b.image(gx(index), gy(1) + 90, 240, 180, f"Concept {index + 1}")
        b.note(gx(index), gy(1) + 280, "Why this works", "One paragraph tying it "
               "back to the brief.", h=140)
    return b


def customer_persona() -> Board:
    b = Board("Persona")
    b.head(gx(0), 100, "Who we are designing for")
    b.image(gx(0), gy(0), 240, 220, "Photo")
    b.note(gx(1), gy(0), "Who they are", "Name, role, the shape of their day.",
           color="yellow", h=220)
    b.note(gx(2), gy(0), "What they need", "The job they are trying to get done.",
           h=220)
    b.note(gx(0), gy(1) + 60, "Frustrations", "What currently makes this hard "
           "or annoying for them.", color="pink", h=170)
    b.note(gx(1), gy(1) + 60, "Where they look", "Which channels they actually "
           "trust when deciding.", h=170)
    b.note(gx(2), gy(1) + 60, "What would win them", "The thing that makes them "
           "choose this over the alternative.", color="green", h=170)
    return b


def project_handover() -> Board:
    b = Board("Handover")
    b.head(gx(0), 100, "Handover pack")
    b.todo(gx(0), gy(0), "Files", [
        "Source files, organised", "Exports in every format agreed",
        "Fonts and licences", "Links to anything hosted",
    ])
    b.todo(gx(1), gy(0), "Documentation", [
        "How to use it", "What not to do to it", "Who to call",
    ])
    b.note(gx(2), gy(0), "Licence", "What the client may do with this, and what "
           "stays yours.", color="orange", h=180)
    b.note(gx(0), gy(1) + 20, "Sign-off", "Who approved what, and when. Worth "
           "its weight the day someone forgets.", w=380, h=150, color="slate")
    return b


def sitemap() -> Board:
    b = Board("Sitemap")
    b.head(gx(0), 100, "Sitemap")
    home = b.note(gx(1), gy(0), "Home", "What it has to do in five seconds",
                  w=200, h=110, color="yellow")
    pages = ["Work", "About", "Services", "Contact"]
    for index, name in enumerate(pages):
        key = b.note(gx(index % 4) - 60 + index * 40, gy(1), name, "",
                     w=190, h=100)
        b.wire(home, key)
    b.note(gx(0), gy(2), "Every page needs a job and a next step. If it has "
           "neither, it is a paragraph on another page.",
           w=380, h=130, color="slate")
    return b


def user_flow() -> Board:
    b = Board("User flow")
    b.head(gx(0), 100, "One task, start to finish")
    steps = [
        ("Arrives", "Where from, and what they expect"),
        ("Looks", "What they need to see to keep going"),
        ("Decides", "The moment of doubt"),
        ("Acts", "The thing you wanted them to do"),
        ("After", "What confirms it worked"),
    ]
    previous = None
    for index, (title, text) in enumerate(steps):
        key = b.note(gx(index % 3), gy(index // 3), title, text, w=220, h=140,
                     color="blue" if index % 2 else "white")
        if previous:
            b.wire(previous, key)
        previous = key
    b.note(gx(2), gy(1), "Where they leave", "The step people abandon, and the "
           "reason. Fix this one first.", w=220, h=140, color="pink")
    return b


def motion_style_frames() -> Board:
    b = Board("Style frames")
    b.head(gx(0), 100, "Style frames")
    b.strip(gx(0), gy(0), 3, w=280, h=170, caption="Frame")
    b.strip(gx(0), gy(0) + 190, 3, w=280, h=170, caption="Frame")
    b.note(gx(0), gy(2) + 40, "Motion notes", "How things enter and leave, how "
           "fast, and what the easing feels like.", w=430, h=150, color="purple")
    b.note(gx(0) + 450, gy(2) + 40, "Sound", "What the cut sounds like. Half of "
           "motion is audio.", w=430, h=150, color="teal")
    return b


def storyboard() -> Board:
    b = Board("Storyboard")
    b.head(gx(0), 100, "Storyboard")
    for row in range(2):
        top = gy(row) + row * 60
        for index in range(4):
            x = gx(0) + index * 220
            b.image(x, top, 205, 150, f"Shot {row * 4 + index + 1}")
            b.note(x, top + 158, "", "Action, camera, and how long it holds",
                   w=205, h=95)
    return b


def blank_with_prompt() -> Board:
    b = Board("New board")
    b.head(gx(0), 120, "What is this board for?")
    b.note(gx(0), gy(0) - 20, "Start here", "Delete this and go. Or drag a tool "
           "in from the left rail.", color="yellow", h=140)
    return b


# --- registry --------------------------------------------------------------

Template = Callable[[], Board]

TEMPLATES: list[dict] = [
    # game design
    {"id": "game-design-document", "name": "Game design document", "category": "Game design",
     "blurb": "Hub board with mechanics, world, characters and levels behind it",
     "build": game_design_document},
    {"id": "game-brainstorm", "name": "Game brainstorm", "category": "Game design",
     "blurb": "Six buckets, nothing judged", "build": game_brainstorm},
    {"id": "game-moodboard", "name": "Game moodboard", "category": "Game design",
     "blurb": "Look, feel, palette, and a not-this pile", "build": game_moodboard},
    {"id": "game-mechanics", "name": "Mechanics", "category": "Game design",
     "blurb": "Core loop, verbs, progression, cut list", "build": game_mechanics},
    {"id": "game-world", "name": "World building", "category": "Game design",
     "blurb": "Premise, history, factions, rules", "build": world_building},
    {"id": "game-characters", "name": "Character profiles", "category": "Game design",
     "blurb": "Three characters with portraits and wants", "build": character_profile},
    {"id": "game-relationships", "name": "Character relationships", "category": "Game design",
     "blurb": "Who is tied to who, drawn with arrows", "build": character_relationships},
    {"id": "game-story", "name": "Story outline", "category": "Game design",
     "blurb": "Six beats, connected in order", "build": game_story_outline},
    {"id": "game-levels", "name": "Level design", "category": "Game design",
     "blurb": "Layout, beats, encounters, pacing", "build": level_design},
    {"id": "game-flow", "name": "Game flow chart", "category": "Game design",
     "blurb": "Boot to credits, wired up", "build": game_flow_chart},
    {"id": "game-storyboard", "name": "Game storyboard", "category": "Game design",
     "blurb": "Eight frames with notes underneath", "build": game_storyboard},
    {"id": "game-marketing", "name": "Launch plan", "category": "Game design",
     "blurb": "Positioning, channels, launch week checklist", "build": game_marketing},

    # graphic design
    {"id": "design-brief", "name": "Design brief", "category": "Graphic design",
     "blurb": "Client, job, audience, tone, deliverables", "build": design_brief},
    {"id": "design-plan", "name": "Project plan", "category": "Graphic design",
     "blurb": "Four columns and the dates that matter", "build": design_project_plan},
    {"id": "moodboard", "name": "Moodboard", "category": "Graphic design",
     "blurb": "Ten image slots, direction, type and colour", "build": moodboard},
    {"id": "concept-presentation", "name": "Concept presentation", "category": "Graphic design",
     "blurb": "Problem, approach, three concepts with rationale",
     "build": concept_presentation},
    {"id": "storyboard", "name": "Storyboard", "category": "Graphic design",
     "blurb": "Eight shots with action and timing", "build": storyboard},
    {"id": "handover", "name": "Handover pack", "category": "Graphic design",
     "blurb": "Files, docs, licence, sign-off", "build": project_handover},

    # branding
    {"id": "brand-strategy", "name": "Brand strategy", "category": "Branding",
     "blurb": "Purpose, positioning, values, voice, proof", "build": brand_strategy},
    {"id": "brand-assets", "name": "Brand assets", "category": "Branding",
     "blurb": "Logo lockups, colour, type, export checklist", "build": brand_assets},
    {"id": "logo-design", "name": "Logo design", "category": "Branding",
     "blurb": "Brief, words, four concepts, survival tests", "build": logo_design},

    # web, ux, motion
    {"id": "persona", "name": "Customer persona", "category": "Web and UX",
     "blurb": "Who they are, what they need, what wins them", "build": customer_persona},
    {"id": "sitemap", "name": "Sitemap", "category": "Web and UX",
     "blurb": "Home wired to the pages under it", "build": sitemap},
    {"id": "user-flow", "name": "User flow", "category": "Web and UX",
     "blurb": "One task start to finish, with the drop-off", "build": user_flow},
    {"id": "style-frames", "name": "Style frames", "category": "Motion",
     "blurb": "Six frames, motion notes, sound", "build": motion_style_frames},

    {"id": "blank", "name": "Blank board", "category": "Start simple",
     "blurb": "Nothing on it but a prompt", "build": blank_with_prompt},
]


def catalogue() -> list[dict]:
    """Everything the picker needs, without building any boards."""
    return [{k: t[k] for k in ("id", "name", "category", "blurb")} for t in TEMPLATES]


def build(template_id: str) -> dict | None:
    for template in TEMPLATES:
        if template["id"] == template_id:
            return template["build"]().spec()
    return None
