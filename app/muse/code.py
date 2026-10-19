"""Syntax highlighting for code cards, via Pygments.

Highlighting happens here rather than in the browser so the export gets it for
free and we do not have to vendor a JavaScript highlighter. Results are cached
by content hash: a board full of code cards re-renders without re-parsing.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

from pygments import format as _format
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.style import Style
from pygments.token import (Comment, Error, Generic, Keyword, Name, Number,
                            Operator, Punctuation, String, Text, Whitespace)
from pygments.util import ClassNotFound

# The languages worth putting in a picker, in the order they appear there.
LANGUAGES = [
    ("auto", "Detect"),
    ("python", "Python"),
    ("javascript", "JavaScript"),
    ("typescript", "TypeScript"),
    ("html", "HTML"),
    ("css", "CSS"),
    ("json", "JSON"),
    ("glsl", "GLSL"),
    ("hlsl", "HLSL"),
    ("c", "C"),
    ("cpp", "C++"),
    ("csharp", "C#"),
    ("rust", "Rust"),
    ("go", "Go"),
    ("java", "Java"),
    ("kotlin", "Kotlin"),
    ("swift", "Swift"),
    ("lua", "Lua"),
    ("ruby", "Ruby"),
    ("php", "PHP"),
    ("sql", "SQL"),
    ("bash", "Shell"),
    ("powershell", "PowerShell"),
    ("yaml", "YAML"),
    ("toml", "TOML"),
    ("xml", "XML"),
    ("markdown", "Markdown"),
    ("diff", "Diff"),
    ("text", "Plain text"),
]

class VSCodeDark(Style):
    """The VS Code "Dark+" palette, so code cards read like the editor Martin
    writes in. Token-based (Pygments has no semantic analyser), so a few things
    an editor tints from meaning - a class name used bare - stay identifier blue,
    but the overall look matches."""

    name = "vscode-dark"
    background_color = "#1e1e1e"
    highlight_color = "#264f78"

    styles = {
        Text:                "#d4d4d4",
        Whitespace:          "#d4d4d4",
        Error:               "#f44747",

        Comment:             "italic #6a9955",
        Comment.Preproc:     "#c586c0",       # #include / #define
        Comment.PreprocFile: "#ce9178",       # the <header> or "header" after it

        Keyword:             "#c586c0",        # control flow: if/for/return/using
        Keyword.Type:        "#569cd6",        # int, char, void, bool
        Keyword.Declaration: "#569cd6",        # class, struct, const, static
        Keyword.Reserved:    "#569cd6",
        Keyword.Constant:    "#569cd6",        # true, false, nullptr
        Keyword.Namespace:   "#569cd6",        # namespace

        Operator:            "#d4d4d4",
        Operator.Word:       "#569cd6",        # and, or, not
        Punctuation:         "#d4d4d4",

        Name:                "#9cdcfe",        # identifiers / variables
        Name.Builtin:        "#4ec9b0",
        Name.Builtin.Pseudo: "#569cd6",        # this, self
        Name.Function:       "#dcdcaa",        # function definitions/calls
        Name.Function.Magic: "#dcdcaa",
        Name.Class:          "#4ec9b0",
        Name.Namespace:      "#4ec9b0",        # std
        Name.Exception:      "#4ec9b0",
        Name.Decorator:      "#dcdcaa",
        Name.Variable:       "#9cdcfe",
        Name.Variable.Magic: "#9cdcfe",
        Name.Attribute:      "#9cdcfe",
        Name.Constant:       "#4fc1ff",
        Name.Label:          "#c8c8c8",
        Name.Tag:            "#569cd6",         # HTML/XML tags
        Name.Entity:         "#569cd6",

        String:              "#ce9178",
        String.Char:         "#ce9178",
        String.Doc:          "italic #6a9955",
        String.Escape:       "#d7ba7d",
        String.Interpol:     "#569cd6",
        String.Regex:        "#d16969",
        String.Symbol:       "#569cd6",

        Number:              "#b5cea8",

        Generic.Deleted:     "#f44747",
        Generic.Inserted:    "#6a9955",
        Generic.Heading:     "bold #569cd6",
        Generic.Subheading:  "bold #4ec9b0",
        Generic.Emph:        "italic",
        Generic.Strong:      "bold",
        Generic.Prompt:      "#6a9955",
    }


# Code cards are a dark surface in both app themes, so both paths highlight dark.
DARK_STYLE = VSCodeDark
LIGHT_STYLE = VSCodeDark


def _formatter(dark: bool) -> HtmlFormatter:
    # nowrap: we supply our own <pre>, so Pygments emits spans only.
    return HtmlFormatter(style=DARK_STYLE if dark else LIGHT_STYLE, nowrap=True)


def _promote_function_calls(tokens):
    """Colour function calls like an editor does. Pygments has no semantic
    analyser, so it tags a call - get(...), holds_alternative<...>(...), foo(...)
    - as a plain Name (identifier blue). Retag any Name that is immediately
    followed by '(' as a function (yellow), allowing a <...> template list in
    between. A name followed by a type or ';' (e.g. std::vector<int> v) is left
    alone, so types stay as they are."""
    toks = list(tokens)
    n = len(toks)

    def skip_ws(j):
        while j < n and not toks[j][1].strip():
            j += 1
        return j

    for i in range(n):
        tt, val = toks[i]
        if tt is not Name:                       # only plain identifiers
            continue
        j = skip_ws(i + 1)
        if j < n and toks[j][1].strip() == "<":  # skip a balanced template list
            depth = 0
            while j < n:
                depth += toks[j][1].count("<") - toks[j][1].count(">")
                j += 1
                if depth <= 0:
                    break
            j = skip_ws(j)
        if j < n and toks[j][1].lstrip().startswith("("):
            toks[i] = (Name.Function, val)
    return toks


@lru_cache(maxsize=256)
def _render(code: str, lang: str, dark: bool) -> tuple[str, str]:
    lexer = None
    resolved = lang
    if lang and lang != "auto":
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            lexer = None
    if lexer is None:
        try:
            lexer = guess_lexer(code)
            resolved = (lexer.aliases or [lexer.name])[0]
        except (ClassNotFound, ValueError):
            lexer = get_lexer_by_name("text")
            resolved = "text"
    tokens = _promote_function_calls(lexer.get_tokens(code))
    return _format(tokens, _formatter(dark)).rstrip("\n"), resolved


def highlight(code: str, lang: str = "auto", dark: bool = True) -> dict:
    if not code:
        return {"html": "", "lang": lang, "hash": ""}
    html, resolved = _render(code, lang or "auto", bool(dark))
    digest = hashlib.sha1(f"{lang}|{dark}|{code}".encode("utf-8", "replace")).hexdigest()[:16]
    return {"html": html, "lang": resolved, "hash": digest}


@lru_cache(maxsize=2)
def stylesheet(dark: bool) -> str:
    """Pygments' colour rules, scoped so both themes can coexist."""
    scope = ".hl.dark" if dark else ".hl.light"
    return _formatter(dark).get_style_defs(scope)


def languages() -> list[dict]:
    return [{"id": code, "name": name} for code, name in LANGUAGES]
