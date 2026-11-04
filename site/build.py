#!/usr/bin/env python3
"""Render the campaign wiki from data/wiki.json into a static site.

Usage:
  python3 site/build.py DATA_DIR OUT_DIR [--label TEXT]

DATA_DIR holds wiki.json and media/ as written by the vault's .wiki/extract.py.
OUT_DIR is replaced. --label adds a banner to every page (used for "Preview").
All links are relative, so the site works at any path (/ and /preview/).

Needs markdown-it-py and mdit-py-plugins (site/requirements.txt).
"""
import html
import json
import os
import re
import shutil
import sys
from collections import defaultdict

from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

FORMATS = {1}
HERE = os.path.dirname(os.path.abspath(__file__))
TITLE = "The Chronicles of the Bardians of Thylea"
SUBTITLE = "as chronicled by the famous bard, Yendithas Gyrahaeras"

SECTIONS = [  # (section, nav label, page title)
    ("characters", "Characters", "Characters"),
    ("locations", "Places", "Places"),
    ("items", "Items", "Items"),
    ("quests", "Quests", "Quests"),
    ("oaths", "Oaths", "Oaths"),
    ("lore", "Lore", "Lore"),
    ("sessions", "Sessions", "Sessions"),
]
SECTION_LABEL = {"characters": "Character", "locations": "Place", "items": "Item", "quests": "Quest",
                 "oaths": "Oath", "lore": "Lore", "sessions": "Session", "days": "Day", "arcs": "Arc"}
KIND_ORDER = {
    "character": [("pc", "The party"), ("npc", "People"), ("god", "The Five and other gods"),
                  ("titan", "Titans"), ("dragon", "Dragons"), ("monster", "Monsters"), ("group", "Groups")],
    "location": [("region", "Regions"), ("city", "Cities"), ("settlement", "Settlements"),
                 ("building", "Buildings"), ("dungeon", "Dungeons"), ("landmark", "Landmarks"),
                 ("island", "Islands"), ("sea", "Seas"), ("realm", "Realms")],
    "lore": [("history", "History"), ("race", "Races"), ("memory", "Memories"), ("rumours", "Rumours")],
}
STATUS_ORDER = {
    "quest": [("open", "Open"), ("done", "Done"), ("failed", "Failed"), ("dropped", "Dropped")],
    "oath": [("active", "Active"), ("fulfilled", "Fulfilled"), ("broken", "Broken"), ("ended", "Ended")],
}
HIDDEN_FIELDS = {"summary", "map", "order", "loop", "session", "day", "day_relative", "day_start",
                 "day_end", "day_start_relative", "day_inferred", "day_unsure", "location_unsure",
                 "locations", "sessions", "date", "kind", "status"}


def esc(s):
    return html.escape(str(s), quote=True)


def slugify(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower() or "section"


def plain(md_html):
    t = re.sub(r"</(p|li|h\d|blockquote|td|th|tr)>|<br\s*/?>", " ", md_html)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def excerpt(text, n=150):
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:—-") + "…"


class Site:
    def __init__(self, data, out, label=None):
        self.data, self.out, self.label = data, out, label
        self.notes = {n["id"]: n for n in data["notes"]}
        self.back = defaultdict(set)
        for n in data["notes"]:
            for l in n["links"]:
                self.back[l].add(n["id"])
        self.md = (MarkdownIt("commonmark", {"breaks": True, "typographer": True})
                   .enable(["table", "strikethrough"])
                   .use(tasklists_plugin)
                   .use(anchors_plugin, max_level=4, slug_func=slugify))
        self.by_type = defaultdict(list)
        for n in data["notes"]:
            self.by_type[n["type"]].append(n)
        self.sessions = sorted(self.by_type["session"], key=lambda n: n["fields"].get("session", 0))
        self.days = sorted(self.by_type["day"], key=lambda n: n["fields"].get("day", 0))
        self.arcs = sorted(self.by_type["arc"], key=lambda n: n["fields"].get("order", 0))
        self.session_no = {n["id"]: n["fields"].get("session") for n in self.sessions}
        self.html_cache = {}
        self.children = defaultdict(list)
        for n in self.by_type["location"]:
            p = ref_id(n["fields"].get("parent"))
            if p:
                self.children[p].append(n["id"])

    # -- urls & links ------------------------------------------------------
    def url(self, nid, root):
        n = self.notes[nid]
        return "%s%s/%s.html" % (root, n["section"], nid)

    def link(self, ref, root, cls=""):
        """ref is a {"id", "label"} dict from the extractor, or a note id."""
        if isinstance(ref, str):
            ref = {"id": ref, "label": self.notes[ref]["title"] if ref in self.notes else ref}
        if not isinstance(ref, dict):
            return esc(ref)
        if ref.get("id") and ref["id"] in self.notes:
            return '<a href="%s"%s>%s</a>' % (self.url(ref["id"], root), ' class="%s"' % cls if cls else "",
                                              esc(ref["label"]))
        return '<span class="redlink" title="No page yet">%s</span>' % esc(ref.get("label", ""))

    def links(self, refs, root):
        if not isinstance(refs, list):
            refs = [refs]
        return ", ".join(self.link(r, root) for r in refs)

    def body_html(self, n, root):
        key = (n["id"], root)
        if key in self.html_cache:
            return self.html_cache[key]
        tokens = self.md.parse(n["body"])
        for t in tokens:
            for c in (t.children or []):
                if c.type == "link_open":
                    href = c.attrGet("href") or ""
                    if href.startswith("wiki:"):
                        target, _, anchor = href[5:].partition("#")
                        if target and target in self.notes:
                            c.attrSet("href", self.url(target, root) + ("#" + anchor if anchor else ""))
                        else:
                            c.attrs.pop("href", None)
                            c.attrSet("class", "redlink")
                            c.attrSet("title", "No page yet")
                    elif re.match(r"https?://", href):
                        c.attrSet("rel", "noopener")
                elif c.type == "image":
                    src = c.attrGet("src") or ""
                    if src.startswith("media/"):
                        c.attrSet("src", root + src)
                    c.attrSet("loading", "lazy")
        out = self.md.renderer.render(tokens, self.md.options, {})
        self.html_cache[key] = out
        return out

    def excerpt_of(self, n):
        s = n["fields"].get("summary")
        if s:
            return text_of(s)
        return excerpt(plain(self.body_html(n, "")))

    # -- page shell --------------------------------------------------------
    def page(self, path, title, content, active=None, wide=False, scripts=()):
        depth = path.count("/")
        root = "../" * depth
        nav = ['<a href="%sindex.html"%s>Map</a>' % (root, ' aria-current="page"' if active == "map" else ""),
               '<a href="%stimeline.html"%s>Timeline</a>' % (root, ' aria-current="page"' if active == "timeline" else "")]
        for sec, label, _ in SECTIONS:
            nav.append('<a href="%s%s/index.html"%s>%s</a>' % (root, sec, ' aria-current="page"' if active == sec else "", label))
        banner = ('<div class="banner">%s · built from vault commit %s</div>' % (esc(self.label), esc(self.data.get("source") or "?"))
                  if self.label else "")
        doc = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="robots" content="noindex">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' cy='16' r='13' fill='%23b0812f'/%3E%3Cpath d='M9 19c3-6 11-6 14 0' stroke='%23fff' stroke-width='2.5' fill='none'/%3E%3C/svg%3E">
<link rel="stylesheet" href="{root}assets/site.css">
<script>try{{var t=localStorage.getItem("ootd-theme");if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
</head>
<body data-root="{root}">
{banner}
<header class="top">
  <a class="brand" href="{root}index.html"><span class="display">{site}</span></a>
  <nav class="nav" aria-label="Sections">{nav}</nav>
  <div class="tools">
    <div class="search">
      <input id="q" type="search" placeholder="Search the chronicle…" autocomplete="off" aria-label="Search">
      <div id="results" class="results" role="listbox" hidden></div>
    </div>
    <button id="theme" class="ctl theme" title="Switch light / dark" aria-label="Switch light or dark theme"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="currentColor"/></svg></button>
  </div>
</header>
<main class="{mcls}">
{content}
</main>
<footer class="foot">What the Bardians know, written down by its players. Not the truth, not the whole truth. · <a href="{root}legacy/thylea-voyage-map.html">old map</a></footer>
<script src="{root}assets/site.js"></script>
{scripts}
</body>
</html>
""".format(title=esc(title if title == TITLE else "%s · %s" % (title, "Thylea")), root=root, banner=banner,
           site=esc(TITLE), nav="".join(nav), mcls="wide" if wide else "page", content=content,
           scripts="".join('<script src="%sassets/%s"></script>' % (root, s) for s in scripts))
        dest = os.path.join(self.out, path)
        os.makedirs(os.path.dirname(dest) or self.out, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(doc)

    # -- note pages --------------------------------------------------------
    def chips(self, n):
        f = n["fields"]
        out = ['<span class="chip">%s</span>' % esc(SECTION_LABEL.get(n["section"], n["section"]))]
        if f.get("kind"):
            out.append('<span class="chip">%s</span>' % esc(kind_label(n["type"], f["kind"])))
        if f.get("status"):
            out.append('<span class="chip status-%s">%s</span>' % (esc(f["status"]), esc(f["status"])))
        return "".join(out)

    def infobox(self, n, root):
        f, t, rows = n["fields"], n["type"], []

        def row(label, value):
            if value:
                rows.append("<dt>%s</dt><dd>%s</dd>" % (esc(label), value))

        if n["aliases"]:
            row("Also known as", esc(", ".join(n["aliases"])))
        if t == "character":
            row("Home", self.links(f["home"], root) if f.get("home") else "")
            row("Affiliation", self.links(f["affiliation"], root) if f.get("affiliation") else "")
        elif t == "location":
            row("In", self.link(f["parent"], root) if f.get("parent") else "")
            row("Constellation", esc(f.get("constellation", "")))
            kids = sorted(self.children.get(n["id"], []), key=lambda i: self.notes[i]["title"].lower())
            row("Places here", ", ".join(self.link(k, root) for k in kids))
        elif t == "item":
            row("Holder", self.link(f["holder"], root) if f.get("holder") else "")
        elif t == "lore":
            row("Learned", self.links(f["learned"], root) if f.get("learned") else "")
            row("Source", self.links(f["source"], root) if f.get("source") else "")
        elif t == "quest":
            row("Given by", self.link(f["given_by"], root) if f.get("given_by") else "")
            row("Given in", self.link(f["given"], root) if f.get("given") else "")
            row("Completed in", self.link(f["completed"], root) if f.get("completed") else "")
            row("Part of", self.link(f["part_of"], root) if f.get("part_of") else "")
            subs = [q for q in self.by_type["quest"] if ref_id(q["fields"].get("part_of")) == n["id"]]
            row("Steps", "<br>".join(self.link(q["id"], root) + status_dot(q) for q in subs))
        elif t == "oath":
            row("Sworn by", self.links(f["sworn_by"], root) if f.get("sworn_by") else "")
            row("Sworn to", self.links(f["sworn_to"], root) if f.get("sworn_to") else "")
            row("Sworn in", self.link(f["sworn"], root) if f.get("sworn") else "")
        elif t == "session":
            row("Played", esc(f.get("date", "")))
            d = self.day_note(f.get("day_start"))
            start = self.link(d["id"], root) if d else esc(f.get("day_start", ""))
            if f.get("day_end") and f.get("day_end") != f.get("day_start"):
                e = self.day_note(f["day_end"])
                start += " – " + (self.link(e["id"], root) if e else esc(f["day_end"]))
            row("In-game day", start + (' <span class="muted">(uncertain)</span>' if f.get("day_unsure") else ""))
            row("Arc", ", ".join(self.link(a["id"], root) for a in self.arcs_of_session(n["id"])))
        elif t == "day":
            if f.get("day_relative") is not None:
                row("Relative day", esc(f["day_relative"]))
            row("Where", self.links(f["locations"], root) if f.get("locations") else '<span class="muted">on the road / at sea</span>')
            row("Arc", ", ".join(self.link(a["id"], root) for a in self.arcs_of_day(f.get("day"))))
        elif t == "arc":
            row("Loop", "I · the first voyage" if f.get("loop") == 1 else "II · after the time jump")
            row("Days", self.day_range(f.get("day_start"), f.get("day_end"), root))
            row("Where", self.links(f.get("locations") or [], root))
        for k, v in f.items():
            if k in HIDDEN_FIELDS or k in ("home", "affiliation", "parent", "constellation", "holder", "learned",
                                           "source", "given_by", "given", "completed", "part_of", "sworn_by",
                                           "sworn_to", "sworn"):
                continue
            if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                row(k.replace("_", " ").capitalize(), esc(v))
            elif isinstance(v, (dict, list)):
                row(k.replace("_", " ").capitalize(), self.links(v, root))
        mini = self.minimap(n, root)
        if not rows and not mini:
            return ""
        return '<aside class="infobox">%s%s</aside>' % (mini, "<dl>%s</dl>" % "".join(rows) if rows else "")

    def pin_of(self, nid, seen=()):
        if not nid or nid not in self.notes or nid in seen:
            return None
        n = self.notes[nid]
        if isinstance(n["fields"].get("map"), dict):
            return nid
        if n["type"] == "location":
            return self.pin_of(ref_id(n["fields"].get("parent")), seen + (nid,))
        if n["type"] == "character":
            return self.pin_of(ref_id(n["fields"].get("home")), seen + (nid,))
        return None

    def minimap(self, n, root):
        pid = self.pin_of(n["id"])
        if not pid:
            return ""
        m = self.notes[pid]["fields"]["map"]
        own = pid == n["id"]
        cap = "" if own else '<figcaption>at %s</figcaption>' % self.link(pid, root)
        return ('<figure class="minimap"><a href="%sindex.html#place=%s" title="Open on the map">'
                '<img src="%s%s" alt="Map of Thylea" loading="lazy"><span class="pin %s" style="left:%s%%;top:%s%%"></span>'
                '</a>%s</figure>') % (root, pid, root, self.data["map"]["image"], esc(m.get("layer", "land")),
                                     m.get("x"), m.get("y"), cap)

    def day_note(self, day):
        for d in self.days:
            if d["fields"].get("day") == day:
                return d
        return None

    def day_range(self, a, b, root):
        da, db = self.day_note(a), self.day_note(b)
        s = self.link(da["id"], root) if da else esc(a)
        if b is not None and b != a:
            s += " – " + (self.link(db["id"], root) if db else esc(b))
        return s

    def arcs_of_session(self, sid):
        return [a for a in self.arcs if sid in [ref_id(r) for r in a["fields"].get("sessions", [])]]

    def arcs_of_day(self, day):
        return [a for a in self.arcs if isinstance(day, int)
                and a["fields"].get("day_start", 0) <= day <= a["fields"].get("day_end", -1)]

    def neighbours(self, n, root):
        seq = {"session": self.sessions, "day": self.days, "arc": self.arcs}.get(n["type"])
        if not seq:
            return ""
        i = [x["id"] for x in seq].index(n["id"])
        prev = '<a href="%s" rel="prev">← %s</a>' % (self.url(seq[i - 1]["id"], root), esc(seq[i - 1]["title"])) if i > 0 else "<span></span>"
        nxt = '<a href="%s" rel="next">%s →</a>' % (self.url(seq[i + 1]["id"], root), esc(seq[i + 1]["title"])) if i + 1 < len(seq) else "<span></span>"
        return '<nav class="pager">%s%s</nav>' % (prev, nxt)

    def extra(self, n, root):
        """Type-specific lists under the body."""
        f, out = n["fields"], []
        if n["type"] == "arc":
            items = []
            for r in f.get("sessions", []):
                sid = ref_id(r)
                if sid in self.notes:
                    items.append(self.session_li(self.notes[sid], root))
            out.append("<h2>Sessions</h2><ol class=\"seslist\">%s</ol>" % "".join(items))
        if n["type"] == "day":
            items = [self.session_li(self.notes[ref_id(r)], root) for r in f.get("sessions", []) if ref_id(r) in self.notes]
            if items:
                out.append("<h2>Sessions starting this day</h2><ol class=\"seslist\">%s</ol>" % "".join(items))
        if n["type"] == "location":
            ids = {n["id"]} | set(self.descendants(n["id"]))
            visits = [d for d in self.days if ids & {ref_id(r) for r in d["fields"].get("locations", [])}]
            if visits:
                out.append("<h2>Days we were here</h2><ul class=\"daylist\">%s</ul>" % "".join(self.day_li(d, root) for d in visits))
        return "".join(out)

    def descendants(self, nid):
        for c in self.children.get(nid, []):
            yield c
            yield from self.descendants(c)

    def session_li(self, s, root):
        return '<li><a href="%s" class="sn">S%s</a> %s</li>' % (self.url(s["id"], root), esc(s["fields"].get("session")),
                                                               esc(text_of(s["fields"].get("summary", ""))))

    def day_li(self, d, root):
        f = d["fields"]
        rel = ' <span class="muted">(%s)</span>' % f["day_relative"] if f.get("day_relative") is not None else ""
        return '<li><a href="%s">Day %s</a>%s — %s</li>' % (self.url(d["id"], root), esc(f.get("day")), rel,
                                                         esc(text_of(f.get("summary", ""))))

    def backlinks(self, n, root):
        ids = self.back.get(n["id"], set())
        if not ids:
            return ""
        groups = defaultdict(list)
        for i in ids:
            groups[self.notes[i]["section"]].append(self.notes[i])
        parts = []
        sess = sorted(groups.pop("sessions", []), key=lambda s: s["fields"].get("session", 0))
        if sess:
            parts.append('<div class="bl"><h3>Sessions</h3><p class="snums">%s</p></div>' % " ".join(
                '<a href="%s" title="%s">%s</a>' % (self.url(s["id"], root), esc(text_of(s["fields"].get("summary", ""))),
                                                    esc(s["fields"].get("session"))) for s in sess))
        days = sorted(groups.pop("days", []), key=lambda d: d["fields"].get("day", 0))
        if days:
            parts.append('<div class="bl"><h3>Days</h3><p class="snums">%s</p></div>' % " ".join(
                '<a href="%s" title="%s">%s</a>' % (self.url(d["id"], root), esc(text_of(d["fields"].get("summary", ""))),
                                                    esc(d["fields"].get("day"))) for d in days))
        for sec, label, _ in SECTIONS + [("arcs", "Arcs", "")]:
            if groups.get(sec):
                parts.append('<div class="bl"><h3>%s</h3><p>%s</p></div>' % (label, ", ".join(
                    self.link(x["id"], root) for x in sorted(groups[sec], key=lambda x: x["title"].lower()))))
        return '<section class="backlinks"><h2>Mentioned in</h2>%s</section>' % "".join(parts)

    def note_page(self, n):
        root = "../"
        f = n["fields"]
        summary = text_of(f.get("summary")) if f.get("summary") else ""
        title = n["title"]
        if n["type"] == "session":
            title = "Session %s" % f.get("session")
        content = """<div class="note">
  <article>
    <div class="kicker">{chips}</div>
    <h1 class="display">{title}</h1>
    {summary}
    <div class="prose">{body}</div>
    {extra}
    {pager}
  </article>
  {infobox}
</div>
{back}""".format(chips=self.chips(n), title=esc(title),
                 summary='<p class="lede">%s</p>' % esc(summary) if summary and n["type"] != "day" or (summary and not n["body"]) else "",
                 body=self.body_html(n, root), extra=self.extra(n, root), pager=self.neighbours(n, root),
                 infobox=self.infobox(n, root), back=self.backlinks(n, root))
        self.page("%s/%s.html" % (n["section"], n["id"]), title, content, active=n["section"])

    # -- section pages -----------------------------------------------------
    def card(self, n, root):
        dot = status_dot(n)
        return ('<li class="card"><a href="%s"><span class="ct">%s%s</span><span class="cx">%s</span></a></li>'
                % (self.url(n["id"], root), esc(n["title"]), dot, esc(self.excerpt_of(n))))

    def section_page(self, sec, title):
        root = "../"
        notes = [n for n in self.data["notes"] if n["section"] == sec]
        idx = sorted([n for n in notes if n["type"] == "index"], key=lambda n: n["title"].lower())
        main = [n for n in notes if n["type"] != "index"]
        parts = []
        t = {"characters": "character", "locations": "location", "items": "item", "quests": "quest",
             "oaths": "oath", "lore": "lore", "sessions": "session"}[sec]
        if sec == "sessions":
            rows = "".join('<tr><td><a href="%s">%s</a></td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                self.url(s["id"], root), esc(s["fields"].get("session")), esc(s["fields"].get("date", "")),
                self.link(self.day_note(s["fields"].get("day_start"))["id"], root) if self.day_note(s["fields"].get("day_start")) else "",
                esc(text_of(s["fields"].get("summary", "")))) for s in self.sessions)
            parts.append('<table class="sestable"><thead><tr><th>#</th><th>Played</th><th>Starts on</th><th>What happened</th></tr></thead><tbody>%s</tbody></table>' % rows)
        elif t in KIND_ORDER or t in STATUS_ORDER:
            key, order = ("kind", KIND_ORDER[t]) if t in KIND_ORDER else ("status", STATUS_ORDER[t])
            if t == "location":
                main = [n for n in main if not ref_id(n["fields"].get("parent"))
                        or ref_id(n["fields"].get("parent")) not in self.notes]
            for val, label in order:
                group = sorted([n for n in main if n["fields"].get(key) == val], key=lambda n: n["title"].lower())
                if group:
                    parts.append('<h2>%s</h2><ul class="cards">%s</ul>' % (esc(label), "".join(
                        self.card(n, root) + self.child_cards(n, root) for n in group)))
        else:
            parts.append('<ul class="cards">%s</ul>' % "".join(
                self.card(n, root) for n in sorted(main, key=lambda n: n["title"].lower())))
        if idx:
            parts.append('<p class="muted">Overview notes: %s</p>' % ", ".join(self.link(n["id"], root) for n in idx))
        content = '<h1 class="display">%s</h1>%s' % (esc(title), "".join(parts))
        self.page("%s/index.html" % sec, title, content, active=sec)

    def child_cards(self, n, root):
        kids = sorted(self.children.get(n["id"], []), key=lambda i: self.notes[i]["title"].lower())
        if not kids:
            return ""
        return '<li class="sub"><ul class="cards nested">%s</ul></li>' % "".join(
            self.card(self.notes[k], root) + self.child_cards(self.notes[k], root) for k in kids)

    # -- timeline ----------------------------------------------------------
    def timeline(self):
        root = ""
        parts, last_loop = [], None
        for a in self.arcs:
            f = a["fields"]
            if f.get("loop") != last_loop:
                if f.get("loop") == 2:
                    parts.append('<div class="jump"><b>Khronos turns back the hourglass.</b> We are thrown back to '
                                 'relative day −5, five days before we first gathered at the Sour Vintage. Absolute '
                                 'days keep counting (42, 43, …); the relative day is in brackets.</div>')
                parts.append('<div class="loopHead"><span class="dot"></span><span class="txt label">%s</span><span class="rule"></span></div>'
                             % ("Loop I · The first voyage" if f.get("loop") == 1 else "Loop II · Before the beginning"))
                last_loop = f.get("loop")
            arc_sessions = {ref_id(r) for r in f.get("sessions", [])}
            days = [d for d in self.days if f.get("day_start", 0) <= d["fields"].get("day", 0) <= f.get("day_end", -1)]
            rows = []
            for d in days:
                ses = [self.notes[ref_id(r)] for r in d["fields"].get("sessions", []) if ref_id(r) in arc_sessions]
                rows.append('<li class="tday"><div class="tdn"><a href="%s">%s</a>%s</div><div><p class="tds">%s</p>%s%s</div></li>' % (
                    self.url(d["id"], root), esc(d["fields"].get("day")),
                    "<small>(%s)</small>" % d["fields"]["day_relative"] if d["fields"].get("day_relative") is not None else "",
                    esc(text_of(d["fields"].get("summary", ""))),
                    '<p class="tloc">%s</p>' % self.links(d["fields"]["locations"], root) if d["fields"].get("locations") else "",
                    '<ol class="seslist">%s</ol>' % "".join(self.session_li(s, root) for s in ses) if ses else ""))
            parts.append('<section class="tarc" id="%s"><h2 class="display"><a href="%s">%s</a></h2><p class="lede">%s</p><ol class="tdays">%s</ol></section>' % (
                a["id"], self.url(a["id"], root), esc(a["title"]), esc(text_of(f.get("summary", ""))), "".join(rows)))
        content = '<h1 class="display">Timeline</h1><p class="muted">Every arc, day and session, in the order we lived them.</p>%s' % "".join(parts)
        self.page("timeline.html", "Timeline", content, active="timeline")

    # -- map ---------------------------------------------------------------
    def map_data(self):
        pins = {}
        for n in self.by_type["location"]:
            m = n["fields"].get("map")
            if isinstance(m, dict):
                pins[n["id"]] = {"x": m.get("x"), "y": m.get("y"), "layer": m.get("layer", "land"),
                                 "name": n["title"], "url": "%s/%s.html" % (n["section"], n["id"]),
                                 "kind": kind_label("location", n["fields"].get("kind", ""))}
        arcs = []
        for a in self.arcs:
            f = a["fields"]
            locs = [ref_id(r) for r in f.get("locations", [])]
            pin = next((self.pin_of(l) for l in locs if self.pin_of(l)), None)
            ses = []
            for r in f.get("sessions", []):
                sid = ref_id(r)
                if sid in self.notes:
                    s = self.notes[sid]
                    ses.append({"n": s["fields"].get("session"), "url": "%s/%s.html" % (s["section"], sid),
                                "t": text_of(s["fields"].get("summary", ""))})
            arcs.append({"id": a["id"], "title": a["title"], "url": "%s/%s.html" % (a["section"], a["id"]),
                         "loop": f.get("loop"), "dayStart": f.get("day_start"), "dayEnd": f.get("day_end"),
                         "pin": pin, "region": self.notes[locs[0]]["title"] if locs and locs[0] in self.notes else "",
                         "regionUrl": "%s/%s.html" % ("locations", locs[0]) if locs and locs[0] in self.notes else None,
                         "blurb": text_of(f.get("summary", "")), "ses": ses})
        days = []
        for d in self.days:
            f = d["fields"]
            locs = [ref_id(r) for r in f.get("locations", [])]
            dpins = []
            for l in locs:
                p = self.pin_of(l)
                if p and (not dpins or dpins[-1] != p):
                    dpins.append(p)
            arc = next((i for i, a in enumerate(self.arcs) if f.get("day", 0) >= a["fields"].get("day_start", 0)
                        and f.get("day", 0) <= a["fields"].get("day_end", -1)), None)
            days.append({"day": f.get("day"), "rel": f.get("day_relative"), "loop": 2 if f.get("day_relative") is not None else 1,
                         "url": "%s/%s.html" % (d["section"], d["id"]),
                         "summary": text_of(f.get("summary", "")),
                         "pins": dpins, "places": [self.notes[l]["title"] for l in locs if l in self.notes],
                         "unsure": bool(f.get("location_unsure")), "arc": arc})
        return {"image": self.data["map"]["image"], "width": self.data["map"]["width"],
                "height": self.data["map"]["height"], "pins": pins, "arcs": arcs, "days": days,
                "sessions": len(self.sessions)}

    def map_page(self):
        md = self.map_data()
        with open(os.path.join(self.out, "map.json"), "w", encoding="utf-8") as f:
            json.dump(md, f, ensure_ascii=False, separators=(",", ":"))
        last = self.days[-1]["fields"] if self.days else {}
        content = """<div class="maphead">
  <h1 class="display">{title}</h1>
  <span class="sub">{sub}</span>
  <span class="stat label"><b>{arcs}</b> arcs · <b>{ses}</b> sessions · days <b>1 → {last}</b></span>
</div>
<div class="wrap">
  <section class="mapside">
    <div class="controls">
      <div class="seg" role="group" aria-label="View mode">
        <button data-mode="session" aria-pressed="true">By arc</button>
        <button data-mode="day" aria-pressed="false">By day</button>
      </div>
      <div class="grp">
        <button class="ctl" id="prev" title="Previous" aria-label="Previous">◀</button>
        <button class="ctl primary" id="play" title="Play through">▶ Play</button>
        <button class="ctl" id="next" title="Next" aria-label="Next">▶</button>
      </div>
      <span class="legnum label" id="posReadout"></span>
      <input type="range" id="slider" min="0" max="0" value="0" aria-label="Progress">
      <div class="grp">
        <label class="chk"><input type="checkbox" id="reveal"> reveal as sailed</label>
        <label class="chk"><input type="checkbox" id="showRoute" checked> route</label>
      </div>
      <div class="grp">
        <button class="ctl" id="editBtn" aria-pressed="false" title="Drag pins to reposition">✥ Edit pins</button>
        <button class="ctl" id="copyBtn" title="Copy the frontmatter for moved pins" hidden>⧉ Copy</button>
        <button class="ctl" id="resetBtn" title="Reset pins" hidden>↺ Reset</button>
      </div>
    </div>
    <div class="editHint label" id="editHint"></div>
    <div class="frameOuter">
      <div class="mapFrame" id="mapFrame">
        <img id="mapImg" alt="The lands and islands of Thylea">
        <svg class="route" id="routeSvg" preserveAspectRatio="none"></svg>
        <div class="tip" id="tip"></div>
      </div>
    </div>
    <div class="placecard" id="placecard"></div>
    <textarea id="pinOut" class="pinout" readonly hidden aria-label="Frontmatter for moved pins"></textarea>
  </section>
  <aside class="panel" id="panel"></aside>
</div>""".format(title=esc(TITLE), sub=esc(SUBTITLE), arcs=len(self.arcs), ses=len(self.sessions),
                 last=esc(last.get("day", "?")))
        self.page("index.html", TITLE, content, active="map", wide=True, scripts=("map.js",))

    # -- search ------------------------------------------------------------
    def search_index(self):
        items = []
        for n in self.data["notes"]:
            text = plain(self.body_html(n, ""))
            title = "Session %s" % n["fields"].get("session") if n["type"] == "session" else n["title"]
            items.append({"t": title, "a": n["aliases"], "s": SECTION_LABEL.get(n["section"], ""),
                          "u": "%s/%s.html" % (n["section"], n["id"]),
                          "x": excerpt(self.excerpt_of(n), 110), "b": text[:4000]})
        with open(os.path.join(self.out, "search.json"), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, separators=(",", ":"))

    def build(self, data_dir):
        if os.path.isdir(self.out):
            shutil.rmtree(self.out)
        os.makedirs(self.out)
        shutil.copytree(os.path.join(HERE, "assets"), os.path.join(self.out, "assets"))
        if os.path.isdir(os.path.join(data_dir, "media")):
            shutil.copytree(os.path.join(data_dir, "media"), os.path.join(self.out, "media"))
        legacy = os.path.join(HERE, "..", "legacy")
        if os.path.isdir(legacy):
            shutil.copytree(legacy, os.path.join(self.out, "legacy"))
        for n in self.data["notes"]:
            self.note_page(n)
        for sec, _, title in SECTIONS:
            self.section_page(sec, title)
        self.timeline()
        self.map_page()
        self.search_index()
        open(os.path.join(self.out, ".nojekyll"), "w").close()
        with open(os.path.join(self.out, "robots.txt"), "w") as f:
            f.write("User-agent: *\nDisallow: /\n")
        return len(self.data["notes"])


def ref_id(r):
    if isinstance(r, dict):
        return r.get("id")
    return None


KIND_SINGULAR = {"pc": "Player character", "npc": "Person", "god": "God", "titan": "Titan", "dragon": "Dragon",
                 "monster": "Monster", "group": "Group", "region": "Region", "city": "City",
                 "settlement": "Settlement", "building": "Building", "dungeon": "Dungeon", "landmark": "Landmark",
                 "island": "Island", "sea": "Sea", "realm": "Realm", "history": "History", "race": "Race",
                 "memory": "Memory", "rumours": "Rumours"}


def kind_label(t, k):
    return KIND_SINGULAR.get(k, str(k).capitalize())


def text_of(v):
    """A frontmatter value as plain text: link objects become their label, wikilinks their text."""
    if isinstance(v, dict):
        return str(v.get("label", ""))
    if isinstance(v, list):
        return ", ".join(text_of(x) for x in v)
    return re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", str(v if v is not None else ""))


def status_dot(n):
    s = n["fields"].get("status")
    if not s or n["type"] not in ("character", "quest", "oath", "item"):
        return ""
    return ' <span class="sdot status-%s" title="%s">%s</span>' % (esc(s), esc(s), esc(s))


def main(argv):
    label = None
    if "--label" in argv:
        i = argv.index("--label")
        label = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 2:
        print(__doc__)
        return 2
    data_dir, out = argv
    with open(os.path.join(data_dir, "wiki.json"), encoding="utf-8") as f:
        data = json.load(f)
    if data.get("format") not in FORMATS:
        print("wiki.json has format %r; this renderer understands %s. Update site/build.py first."
              % (data.get("format"), sorted(FORMATS)))
        return 1
    n = Site(data, os.path.abspath(out), label).build(data_dir)
    print("Rendered %d notes to %s" % (n, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
