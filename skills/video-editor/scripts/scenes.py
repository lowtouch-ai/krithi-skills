"""Panel scenes for the explainer style: animated graphics above the speaker, drawn from templates.

The agent picks a scene type for each point in the talk and fills in its words (clips.json, "scenes"); this module checks the
data, finds the moment each scene and each of its parts is spoken, and builds the HyperFrames page that animates it. The look
(colours, type sizes, window styling) is fixed here and in brand.json, so scenes look the same whoever wrote them.

A scene:  {"type": "terminal", "say": "words that start it", "tag": "TIP 01", "data": {...}}
Every part (a terminal line, a tree row, a flow node, a title item) may carry its own "say"; parts without one are spread
evenly over the scene. A scene stays on screen until the next one starts (or the clip ends).
Types: title, terminal, tree, flow, checklist, bubble, steps, and custom (the fallback for a point no template fits).
"""
import copy
import html
import re
from html.parser import HTMLParser

SCENE_TYPES = ("title", "terminal", "tree", "flow", "checklist", "bubble", "steps", "custom")
MAX_SCENES_PER_MINUTE = 6
LIMITS = {
    "tag": 14, "title": 34, "label": 34, "text": 38, "sub": 24, "name": 24, "icon": 4,
    "terminal_lines": 6, "tree_rows": 6, "flow_nodes": 4, "flow_rows": 2, "title_items": 3,
    "checklist_items": 5, "bubbles": 3, "steps": 4, "bubble": 60, "heading": 14, "toggle": 10, "flag": 2, "step_sub": 40,
}
CTA_MAX_HEIGHT = 400  # a scene that shares the panel with a call-to-action pill may take this much (the pill sits at the bottom)
MAX_HEIGHT = 490  # design px (1080 wide) a scene may take below its top edge: the panel is 768 px and the scene starts at 250
LINE_KINDS = ("cmd", "out", "ok", "dim")
TREE_KINDS = ("dir", "file")


def _s(v):
    return str(v).strip() if v is not None else ""


def _parts(sc):
    """The scene's parts as (list_name, index, part) so a spoken moment can be found for each."""
    d = sc.get("data") or {}
    t = sc.get("type")
    if t == "terminal":
        return [("lines", i, p) for i, p in enumerate(d.get("lines") or [])]
    if t == "tree":
        return [("rows", i, p) for i, p in enumerate(d.get("rows") or [])]
    if t == "flow":
        out = []
        for ri, row in enumerate(_flow_rows(d)):
            out += [(f"row{ri}", ni, n) for ni, n in enumerate(row.get("nodes") or [])]
        return out
    if t == "title":
        return [("items", i, p) for i, p in enumerate(d.get("items") or [])]
    if t == "checklist":
        out = [("items", i, p) for i, p in enumerate(d.get("items") or [])]
        return out + ([("bubble", 0, d["bubble"])] if isinstance(d.get("bubble"), dict) else [])
    if t == "bubble":
        return [("bubbles", i, p) for i, p in enumerate(d.get("bubbles") or [])]
    if t == "steps":
        return [("steps", i, p) for i, p in enumerate(d.get("steps") or [])]
    if t == "custom":
        return [("reveal", i, p) for i, p in enumerate(d.get("anim") or [])]
    return []


def _flow_rows(d):
    if d.get("rows"):
        return d["rows"]
    return [{"label": d.get("label", ""), "nodes": d.get("nodes") or []}]


# ------------------------------------------------------------------ custom scenes (the fallback)
# The agent writes a small piece of HTML and CSS and a list of timed reveals. There is no script: timing comes from preset
# effects, the markup is limited to harmless tags and attributes, nothing is fetched, and the CSS is scoped to the scene.
CUSTOM_LIMITS = {"html": 5000, "css": 3000, "anim": 12}
EFFECTS = ("fade", "rise", "pop", "slide", "wipe")
ALLOWED_TAGS = {"div", "span", "b", "i", "em", "strong", "p", "br", "ul", "li", "svg", "path", "rect", "circle", "ellipse", "line",
                "polyline", "polygon", "g", "text"}
ALLOWED_ATTRS = {"id", "class", "style", "viewbox", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "width", "height",
                 "fill", "stroke", "stroke-width", "points", "transform", "stroke-linecap", "stroke-linejoin", "opacity", "font-size",
                 "text-anchor", "font-family", "xmlns", "preserveaspectratio"}
BAD_STYLE = ("url(", "expression", "position:fixed", "position: fixed", "@import", "javascript", "behavior", "<", "\\")
ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
FONT_OK = {"brand", "mono", "sans-serif", "monospace", "inherit"}


class _Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors, self.ids = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_TAGS:
            self.errors.append(f"tag <{tag}> is not allowed (allowed: {', '.join(sorted(ALLOWED_TAGS))})")
        for k, v in attrs:
            k = k.lower()
            if k not in ALLOWED_ATTRS:
                self.errors.append(f"attribute '{k}' is not allowed")
                continue
            val = (v or "").lower()
            if k == "id":
                if not ID_RE.match(v or ""):
                    self.errors.append(f"id '{v}' must be lower case letters, digits and hyphens, starting with a letter")
                self.ids.append(v)
            if any(b in val for b in BAD_STYLE) and k in ("style", "fill", "stroke", "d", "points", "transform", "font-family"):
                self.errors.append(f"'{k}' may not contain url(), position: fixed or similar")
            if k in ("style", "font-family"):
                for fam in re.findall(r"font-family\s*:\s*([^;]+)", val) + ([val] if k == "font-family" else []):
                    for f in re.split(r",", fam):
                        if f.strip().strip("'\"") not in FONT_OK:
                            self.errors.append(f"font '{f.strip()}' is not available; use Brand or Mono")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def check_custom(sc, tag):
    """Errors for a custom scene: size limits, allowed markup, scoped CSS, and the timed reveals."""
    d = sc.get("data") or {}
    errs = []
    h, c, anim = _s(d.get("html")), _s(d.get("css")), d.get("anim") or []
    if not h:
        return [f"{tag}: a custom scene needs data.html"]
    if len(h) > CUSTOM_LIMITS["html"] or len(c) > CUSTOM_LIMITS["css"]:
        errs.append(f"{tag}: html is at most {CUSTOM_LIMITS['html']} characters and css at most {CUSTOM_LIMITS['css']}")
    if len(anim) > CUSTOM_LIMITS["anim"]:
        errs.append(f"{tag}: at most {CUSTOM_LIMITS['anim']} timed reveals")
    chk = _Checker()
    chk.feed(h)
    chk.close()
    errs += [f"{tag} html: {e}" for e in chk.errors[:5]]
    if len(set(chk.ids)) != len(chk.ids):
        errs.append(f"{tag} html: ids must be unique")
    low = c.lower()
    if c and (any(b in low for b in BAD_STYLE) or "@" in c):
        errs.append(f"{tag} css: no @rules, url(), position: fixed, or angle brackets")
    for fam in re.findall(r"font-family\s*:\s*([^;}]+)", low):
        for f in fam.split(","):
            if f.strip().strip("'\"") not in FONT_OK:
                errs.append(f"{tag} css: font '{f.strip()}' is not available; use Brand or Mono")
    if re.search(r"(^|})\s*(html|body)\b", low):
        errs.append(f"{tag} css: style the scene's own elements, not html or body")
    if c and not re.fullmatch(r"(?:\s*[^{}@]+\{[^{}]*\}\s*)+", c):
        errs.append(f"{tag} css: only plain rules (selector {{ property: value; }}) are allowed")
    for i, a in enumerate(anim, 1):
        if a.get("el") not in chk.ids:
            errs.append(f"{tag} reveal {i}: 'el' must be the id of an element in the html")
        if a.get("effect", "fade") not in EFFECTS:
            errs.append(f"{tag} reveal {i}: effect must be one of {', '.join(EFFECTS)}")
    return errs


def scope_css(css, sid):
    """Prefix every selector with the scene's id so a custom scene can only style itself."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        sels = [x.strip() for x in m.group(1).split(",") if x.strip()]
        out.append(", ".join(f"#{sid} {x}" for x in sels) + " {" + m.group(2) + "}")
    return "\n      ".join(out)


def prefix_ids(markup, sid):
    return re.sub(r'\bid="([a-z][a-z0-9-]*)"', lambda m: f'id="{sid}-{m.group(1)}"', markup)


def est_height(sc):
    """Rough height of a scene in design pixels (1080 wide), tag included, to refuse a scene that would run under the speaker."""
    d = sc.get("data") or {}
    t = sc.get("type")
    h = 62 if _s(sc.get("tag")) else 0
    if t in ("terminal", "tree"):
        h += 60 + max(250, 44 + 50 * len(d.get("lines" if t == "terminal" else "rows") or []))
    elif t == "checklist":
        h += 60 + max(250, 44 + (44 if _s(d.get("heading")) else 0) + 46 * len(d.get("items") or [])) + (88 if isinstance(d.get("bubble"), dict) else 0)
    elif t == "flow":
        h += sum((40 if _s(r.get("label")) else 0) + 100 + 40 for r in _flow_rows(d)) - 40
    elif t == "bubble":
        h += 88 * len(d.get("bubbles") or [])
    elif t == "steps":
        h += (46 if _s(d.get("label")) else 0) + 74 * len(d.get("steps") or [])
    elif t == "title":
        name_lines = -(-len(_s(d.get("name"))) // 13) if _s(d.get("name")) else 0  # the name is set under the icon, 13 characters a line
        h += 60 + 150 + (name_lines * 36 + 14 if name_lines else 0)
    elif t == "custom":
        return float(d.get("measured_height") or 0)  # measured in a browser (render_motion.measure_scene_heights); it includes the tag
    return h


def cta_conflicts(scenes, ctas):
    """Messages for each call-to-action pill that is shown while a scene too tall to share the panel with it is on screen.
    scenes: resolved scenes (`at`, `end`); ctas: resolved pills (`at`, `seconds`), both in source seconds."""
    out = []
    for k, c in enumerate(ctas or [], 1):
        a, b = c["at"], c["at"] + float(c.get("seconds", 4))
        for j, sc in enumerate(scenes or [], 1):
            if sc["at"] < b and sc["end"] > a and est_height(sc) > CTA_MAX_HEIGHT:
                out.append(f"call-to-action {k} is shown while scene {j} ({sc.get('type')}, about {est_height(sc):.0f} px) is on screen; "
                           f"the pill needs the bottom of the panel, so keep that scene under {CTA_MAX_HEIGHT} px (fewer lines, no tag or bubble) or move the pill to another moment")
    return out


PANEL_CENTRE, PANEL_TOP, PANEL_BOTTOM, MAX_FIT = 430, 180, 740, 1.4  # design px at 1080 wide: where scenes are centred, and the room they have


def place(scenes, ctas=()):
    """Scale small scenes up and centre them in the panel, so the panel is not mostly empty.

    scenes: [{type, tag, data, start, end}] in clip seconds; ctas: [{start, end}] in clip seconds. A scene shown while a pill is
    on screen keeps clear of the bottom of the panel. Returns copies with `fit` (a scale from 1 to 1.4) and `top` (design px)."""
    out = []
    for sc in scenes:
        h = est_height(sc)
        bottom = PANEL_BOTTOM
        if any(c["start"] < sc["end"] and c["end"] > sc["start"] for c in ctas or []):
            bottom = PANEL_BOTTOM - 90
        if h <= 0:  # a custom scene that was not measured: leave it where it is
            out.append({**sc, "fit": 1.0, "top": 250})
            continue
        fit = max(1.0, min(MAX_FIT, (bottom - 200) / h))
        hh = h * fit
        out.append({**sc, "fit": round(fit, 3), "top": round(min(max(PANEL_CENTRE - hh / 2, PANEL_TOP), bottom - hh))})
    return out


def check_scene(sc, tag):
    """Structural errors for one scene (type, required fields, counts, text lengths)."""
    errs = []
    t = sc.get("type")
    d = sc.get("data") or {}
    if t not in SCENE_TYPES:
        return [f"{tag}: scene type must be one of {', '.join(SCENE_TYPES)}"]
    if not _s(sc.get("say")):
        errs.append(f"{tag}: 'say' (the words that start the scene) is required")
    if len(_s(sc.get("tag"))) > LIMITS["tag"]:
        errs.append(f"{tag}: tag is longer than {LIMITS['tag']} characters")

    def txt(v, key, what, req=True):
        v = _s(v)
        if req and not v:
            errs.append(f"{tag}: {what} is required")
        if len(v) > LIMITS[key]:
            errs.append(f"{tag}: {what} is longer than {LIMITS[key]} characters")

    if t == "terminal":
        lines = d.get("lines") or []
        if not 1 <= len(lines) <= LIMITS["terminal_lines"]:
            errs.append(f"{tag}: a terminal needs 1 to {LIMITS['terminal_lines']} lines")
        for i, ln in enumerate(lines, 1):
            if ln.get("kind", "out") not in LINE_KINDS:
                errs.append(f"{tag} line {i}: kind must be one of {', '.join(LINE_KINDS)}")
            txt(ln.get("text"), "text", f"line {i} text")
    elif t == "tree":
        rows = d.get("rows") or []
        if not 1 <= len(rows) <= LIMITS["tree_rows"]:
            errs.append(f"{tag}: a tree needs 1 to {LIMITS['tree_rows']} rows")
        for i, r in enumerate(rows, 1):
            if r.get("kind", "file") not in TREE_KINDS:
                errs.append(f"{tag} row {i}: kind must be dir or file")
            txt(r.get("text"), "text", f"row {i} text")
            if not 0 <= int(r.get("depth", 0)) <= 3:
                errs.append(f"{tag} row {i}: depth must be 0 to 3")
    elif t == "flow":
        rows = _flow_rows(d)
        if not 1 <= len(rows) <= LIMITS["flow_rows"]:
            errs.append(f"{tag}: a flow needs 1 to {LIMITS['flow_rows']} rows")
        for ri, row in enumerate(rows, 1):
            nodes = row.get("nodes") or []
            if not 1 <= len(nodes) <= LIMITS["flow_nodes"]:
                errs.append(f"{tag} row {ri}: needs 1 to {LIMITS['flow_nodes']} nodes")
            txt(row.get("label"), "label", f"row {ri} label", req=False)
            for ni, n in enumerate(nodes, 1):
                txt(n.get("title"), "title", f"row {ri} node {ni} title")
                txt(n.get("sub"), "sub", f"row {ri} node {ni} sub", req=False)
    elif t == "custom":
        errs += check_custom(sc, tag)
    elif t == "checklist":
        items = d.get("items") or []
        if not 1 <= len(items) <= LIMITS["checklist_items"]:
            errs.append(f"{tag}: a checklist needs 1 to {LIMITS['checklist_items']} items")
        txt(d.get("heading"), "heading", "heading", req=False)
        txt(d.get("title"), "title", "title", req=False)
        tg = d.get("toggles") or []
        if len(tg) > 3 or any(len(_s(x)) > LIMITS["toggle"] for x in tg):
            errs.append(f"{tag}: at most 3 toggles of {LIMITS['toggle']} characters")
        for i, it in enumerate(items, 1):
            txt(it.get("text"), "text", f"item {i} text")
            txt(it.get("flag"), "flag", f"item {i} flag", req=False)
            if it.get("state", "done") not in ("done", "todo"):
                errs.append(f"{tag} item {i}: state must be done or todo")
        if isinstance(d.get("bubble"), dict):
            txt(d["bubble"].get("text"), "bubble", "bubble text")
    elif t == "bubble":
        bs = d.get("bubbles") or []
        if not 1 <= len(bs) <= LIMITS["bubbles"]:
            errs.append(f"{tag}: needs 1 to {LIMITS['bubbles']} bubbles")
        for i, b in enumerate(bs, 1):
            txt(b.get("text"), "bubble", f"bubble {i} text")
            if b.get("from", "user") not in ("user", "agent"):
                errs.append(f"{tag} bubble {i}: from must be user or agent")
    elif t == "steps":
        sp = d.get("steps") or []
        if not 1 <= len(sp) <= LIMITS["steps"]:
            errs.append(f"{tag}: needs 1 to {LIMITS['steps']} steps")
        txt(d.get("label"), "label", "label", req=False)
        for i, st_ in enumerate(sp, 1):
            txt(st_.get("title"), "title", f"step {i} title")
            txt(st_.get("sub"), "step_sub", f"step {i} sub", req=False)
    elif t == "title":
        txt(d.get("label"), "label", "label", req=False)
        txt(d.get("name"), "name", "name", req=False)
        txt(d.get("icon"), "icon", "icon", req=False)
        if not (_s(d.get("label")) or _s(d.get("name")) or d.get("items")):
            errs.append(f"{tag}: a title scene needs a label, a name or items")
        items = d.get("items") or []
        if len(items) > LIMITS["title_items"]:
            errs.append(f"{tag}: a title scene holds at most {LIMITS['title_items']} items")
        for i, it in enumerate(items, 1):
            txt(it.get("text"), "text", f"item {i} text")
    if not errs and est_height(sc) > MAX_HEIGHT:
        errs.append(f"{tag}: the scene is too tall for the panel (about {est_height(sc)} of {MAX_HEIGHT}); use fewer lines, rows or items, or drop the tag")
    return errs


def resolve_scenes(clip, tag, words, start, end, errors, warnings, find_phrase, keep_map=None):
    """Check a clip's scenes and give each scene and part the second it is spoken (source seconds).

    `find_phrase(words, phrase, after)` is validate_clips.find_phrase. Returns the scenes with `at` (start of the scene),
    `end`, and an `at` on every part that has a `say`."""
    scenes = clip.get("scenes") or []
    out, last = [], None
    minutes = max((end - start) / 60.0, 0.1)
    if len(scenes) > max(2, int(MAX_SCENES_PER_MINUTE * minutes + 1)):
        warnings.append(f"{tag}: {len(scenes)} scenes in {minutes * 60:.0f} s is busy; about one every 10 s reads best")
    for si, sc in enumerate(scenes, 1):
        sc = copy.deepcopy(sc)  # the checks add times to the parts; the clip as written stays as it is
        stag = f"{tag} scene {si}"
        errs = check_scene(sc, stag)
        if errs:
            errors.extend(errs)
            continue
        hit, earlier = find_phrase(words, _s(sc.get("say")), last)
        if hit is None:
            errors.append(f"{stag}: the words \"{sc.get('say')}\" are " + ("only spoken before the previous scene; scenes must be in the order spoken" if earlier else "not spoken in this clip"))
            continue
        at = hit[0]
        last = at
        res_sc = {**sc, "at": round(at, 3)}
        p_last = at
        for name, idx, part in _parts(sc):
            say = _s(part.get("say"))
            if not say:
                continue
            h2, e2 = find_phrase(words, say, p_last)
            if h2 is None:
                errors.append(f"{stag} {name} {idx + 1}: the words \"{say}\" are " + ("spoken before the previous part; parts must be in the order spoken" if e2 else "not spoken in this clip"))
                continue
            p_last = h2[0]
            part["at"] = round(h2[0], 3)
        res_sc["data"] = sc.get("data")
        out.append(res_sc)
    for a, b in zip(out, out[1:]):
        a["end"] = b["at"]
        if b["at"] - a["at"] < 3.0:
            warnings.append(f"{tag}: scene '{a.get('type')}' is replaced {b['at'] - a['at']:.1f} s after it appears; give each scene at least 3 s")
    if out:
        out[-1]["end"] = round(end - 0.3, 3)
    return out


# ------------------------------------------------------------------ the page

MEASURE = ("<script>document.fonts.ready.then(function(){document.querySelectorAll('.scene').forEach(function(el){"
           "el.setAttribute('data-h', String(Math.ceil(el.scrollHeight)));});document.body.setAttribute('data-done','1');});</script>")


def build_page(scenes, colors, fonts, W, panel_h, duration, measure=False):
    """HTML for a transparent overlay covering the panel (W x panel_h), one block per scene.

    scenes: [{type, tag, data, start, end, els}] in overlay seconds; `els` are the times of the parts in order (None = spread).
    colors: {accent, accent2, text, dim, card, border, panel}. fonts: [(family, weight, file)]."""
    e = html.escape
    s = W / 1080.0
    px = lambda v: f"{v * s:.1f}px"
    body, js, css = [], [], []
    X0, Y0 = 70, 250   # content box (design px at 1080 wide)
    CW, CH = 940, 460
    for n, sc in enumerate(scenes, 1):
        start, end = float(sc["start"]), float(sc["end"])
        dur = max(end - start, 0.5)
        sid = f"s{n}"
        fit = float(sc.get("fit", 1.0))
        top = float(sc.get("top", Y0))
        t = sc["type"]
        d = sc.get("data") or {}
        parts = _parts(sc)
        times = sc.get("els") or []
        k_parts = max(len(parts), 1)

        def at(i):  # when part i appears (overlay seconds)
            if i < len(times) and times[i] is not None:
                return max(float(times[i]), start + 0.2)
            return start + 0.45 + i * max(dur - 1.2, 0.6) / k_parts
        inner = ""
        tagh = f'<div class="tag" id="{sid}tag">{e(_s(sc.get("tag")))}</div>' if _s(sc.get("tag")) else ""
        if t == "terminal":
            rows = []
            for i, ln in enumerate(d.get("lines") or []):
                kind = ln.get("kind", "out")
                txt = _s(ln.get("text"))
                pre = {"cmd": "&rsaquo;", "ok": "&#10003;", "out": "", "dim": ""}[kind]
                rows.append(f'<div class="ln {kind}" id="{sid}l{i}"><span class="pr">{pre}</span><span class="tx" id="{sid}t{i}" style="width:{len(txt)}ch">{e(txt)}</span></div>')
                a = at(i)
                js.append(f'tl.fromTo("#{sid}l{i}", {{opacity: 0, x: {-10 * s:.0f}}}, {{opacity: 1, x: 0, duration: 0.25, ease: "power2.out"}}, {a:.3f});')
                if kind == "cmd":
                    js.append(f'tl.fromTo("#{sid}t{i}", {{width: "0ch"}}, {{width: "{len(txt)}ch", duration: {min(1.2, 0.06 * len(txt) + 0.2):.2f}, ease: "steps({max(len(txt), 1)})"}}, {a + 0.1:.3f});')
            inner = (f'<div class="win" id="{sid}w"><div class="bar"><i></i><i></i><i></i><span>{e(_s(d.get("title")))}</span></div>'
                     f'<div class="wb">{"".join(rows)}</div></div>')
        elif t == "tree":
            rows = []
            for i, r in enumerate(d.get("rows") or []):
                depth, kind = int(r.get("depth", 0)), r.get("kind", "file")
                icon = "&#9662;" if kind == "dir" else "&nbsp;"
                hl = " hl" if r.get("hl") else ""
                rows.append(f'<div class="ln tree{hl}" id="{sid}l{i}" style="padding-left:{px(26 + depth * 34)}"><span class="pr">{icon}</span><span class="tx">{e(_s(r.get("text")))}</span></div>')
                js.append(f'tl.fromTo("#{sid}l{i}", {{opacity: 0, x: {-10 * s:.0f}}}, {{opacity: 1, x: 0, duration: 0.25, ease: "power2.out"}}, {at(i):.3f});')
            inner = (f'<div class="win" id="{sid}w"><div class="bar"><i></i><i></i><i></i><span>{e(_s(d.get("title")) or "explorer")}</span></div>'
                     f'<div class="wb">{"".join(rows)}</div></div>')
        elif t == "flow":
            rows_h, idx = [], 0
            for ri, row in enumerate(_flow_rows(d)):
                nodes = row.get("nodes") or []
                longest = max([len(_s(n.get("title"))) for n in nodes] or [1])
                arrow_px = 54 if len(nodes) < 4 else 34
                avail = (CW / fit - (len(nodes) - 1) * (arrow_px + 20)) / max(len(nodes), 1) - 28  # width left for a node's text (the scene is zoomed by `fit`)
                node_fs = int(min(32, max(20, avail / (0.66 * max(longest, 1)))))
                css.append(f"#{sid} .frow:nth-child({ri + 1}) .node b {{ font-size: {px(node_fs)}; }}"
                           f" #{sid} .frow:nth-child({ri + 1}) .arrow {{ width: {px(arrow_px)}; }}")
                cells = []
                for ni, nd in enumerate(nodes):
                    if ni:
                        cells.append(f'<div class="arrow" id="{sid}a{idx}"></div>')
                        js.append(f'tl.fromTo("#{sid}a{idx}", {{opacity: 0, scaleX: 0.2}}, {{opacity: 1, scaleX: 1, duration: 0.25, ease: "power2.out"}}, {at(idx) - 0.15:.3f});')
                    cells.append(f'<div class="node" id="{sid}n{idx}"><b>{e(_s(nd.get("title")))}</b><em>{e(_s(nd.get("sub")))}</em></div>')
                    js.append(f'tl.fromTo("#{sid}n{idx}", {{opacity: 0, y: {18 * s:.0f}}}, {{opacity: 1, y: 0, duration: 0.3, ease: "back.out(1.4)"}}, {at(idx):.3f});')
                    idx += 1
                lab = f'<div class="rl">{e(_s(row.get("label")))}</div>' if _s(row.get("label")) else ""
                rows_h.append(f'<div class="frow">{lab}<div class="cells">{"".join(cells)}</div></div>')
            inner = f'<div class="flow">{"".join(rows_h)}</div>'
        elif t == "custom":
            inner = f'<div class="cust">{prefix_ids(_s(d.get("html")), sid)}</div>'
            if _s(d.get("css")):
                css.append(scope_css(_s(d.get("css")), sid))
            fx = {"fade": ("{opacity: 0}", "{opacity: 1, duration: 0.4, ease: \"power2.out\"}"),
                  "rise": (f"{{opacity: 0, y: {26 * s:.0f}}}", "{opacity: 1, y: 0, duration: 0.4, ease: \"power3.out\"}"),
                  "pop": ("{opacity: 0, scale: 0.85}", "{opacity: 1, scale: 1, duration: 0.35, ease: \"back.out(1.7)\"}"),
                  "slide": (f"{{opacity: 0, x: {-34 * s:.0f}}}", "{opacity: 1, x: 0, duration: 0.4, ease: \"power2.out\"}"),
                  "wipe": ("{clipPath: \"inset(0 100% 0 0)\"}", "{clipPath: \"inset(0 0% 0 0)\", duration: 0.5, ease: \"power2.inOut\"}")}
            for i, a_ in enumerate(d.get("anim") or []):
                frm, to = fx[a_.get("effect", "fade")]
                js.append(f'tl.fromTo("#{sid}-{a_["el"]}", {frm}, {to}, {at(i):.3f});')
        elif t == "checklist":
            tg = d.get("toggles") or []
            act = int(d.get("active", len(tg) - 1)) if tg else -1
            togg = f'<span class="tg">{"".join(f"<b class=on>" + e(_s(x)) + "</b>" if i == act else "<b>" + e(_s(x)) + "</b>" for i, x in enumerate(tg))}</span>' if tg else ""
            hd = f'<div class="hd">{e(_s(d.get("heading")))}</div>' if _s(d.get("heading")) else ""
            rows = []
            for i, it in enumerate(d.get("items") or []):
                done = it.get("state", "done") == "done"
                flag = _s(it.get("flag"))
                rows.append(f'<div class="ln ck{" flagged" if flag else ""}{"" if done else " todo"}" id="{sid}l{i}"><span class="pr">{"&#10003;" if done else "&middot;"}</span>'
                            f'<span class="tx">{i + 1}. {e(_s(it.get("text")))}</span>{f"<span class=bd>{e(flag)}</span>" if flag else ""}</div>')
                js.append(f'tl.fromTo("#{sid}l{i}", {{opacity: 0, x: {-10 * s:.0f}}}, {{opacity: 1, x: 0, duration: 0.25, ease: "power2.out"}}, {at(i):.3f});')
            bub = ""
            if isinstance(d.get("bubble"), dict):
                bi = len(d.get("items") or [])
                bub = f'<div class="bub" id="{sid}b0">{e(_s(d["bubble"].get("text")))}</div>'
                js.append(f'tl.fromTo("#{sid}b0", {{opacity: 0, y: {20 * s:.0f}, scale: 0.92}}, {{opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "back.out(1.6)"}}, {at(bi):.3f});')
            inner = (f'<div class="win" id="{sid}w"><div class="bar"><i></i><i></i><i></i><span>{e(_s(d.get("title")))}</span>{togg}</div>'
                     f'<div class="wb">{hd}{"".join(rows)}</div></div>{bub}')
        elif t == "bubble":
            bl = []
            for i, b in enumerate(d.get("bubbles") or []):
                bl.append(f'<div class="bub {b.get("from", "user")}" id="{sid}b{i}">{e(_s(b.get("text")))}</div>')
                js.append(f'tl.fromTo("#{sid}b{i}", {{opacity: 0, y: {20 * s:.0f}, scale: 0.92}}, {{opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "back.out(1.6)"}}, {at(i):.3f});')
            inner = f'<div class="bubs">{"".join(bl)}</div>'
        elif t == "steps":
            rows = []
            for i, stp in enumerate(d.get("steps") or []):
                sub = f'<em>{e(_s(stp.get("sub")))}</em>' if _s(stp.get("sub")) else ""
                rows.append(f'<div class="sr" id="{sid}r{i}"><span class="num">{i + 1}</span><div><b>{e(_s(stp.get("title")))}</b>{sub}</div></div>')
                js.append(f'tl.fromTo("#{sid}r{i}", {{opacity: 0, x: {-16 * s:.0f}}}, {{opacity: 1, x: 0, duration: 0.3, ease: "power2.out"}}, {at(i):.3f});')
            lab = f'<div class="rl">{e(_s(d.get("label")))}</div>' if _s(d.get("label")) else ""
            inner = f'<div class="stp">{lab}{"".join(rows)}</div>'
        elif t == "title":
            icon = f'<div class="icon" id="{sid}i">{e(_s(d.get("icon")))}</div>' if _s(d.get("icon")) else ""
            name = f'<div class="nm">{e(_s(d.get("name")))}</div>' if _s(d.get("name")) else ""
            lab = f'<div class="rl big">{e(_s(d.get("label")))}</div>' if _s(d.get("label")) else ""
            items = []
            lone = len(d.get("items") or []) == 1  # one point needs no number
            for i, it in enumerate(d.get("items") or []):
                num = "" if lone or not _s(it.get("n")) else f'<span>{e(_s(it.get("n")))}</span>'
                items.append(f'<div class="item" id="{sid}it{i}">{num}{e(_s(it.get("text")))}</div>')
                js.append(f'tl.fromTo("#{sid}it{i}", {{opacity: 0, x: {-16 * s:.0f}}}, {{opacity: 1, x: 0, duration: 0.3, ease: "power2.out"}}, {at(i):.3f});')
            inner = f'<div class="ttl">{lab}<div class="row">{icon}<div class="its">{"".join(items)}</div></div>{name}</div>'
        body.append(f'<div id="{sid}" class="clip scene{" custom" if t == "custom" else ""}" style="top:{px(top)}" data-start="{start:.3f}" data-duration="{dur:.3f}" data-track-index="0">'
                    f'<div class="zf" style="zoom:{fit:.3f}; width:{px(CW / fit)}">{tagh}{inner}</div></div>')
        js.append(f'tl.fromTo("#{sid}", {{opacity: 0, y: {22 * s:.0f}}}, {{opacity: 1, y: 0, duration: 0.35, ease: "power3.out"}}, {start:.3f});')
        js.append(f'tl.fromTo("#{sid}", {{opacity: 1}}, {{opacity: 0, duration: 0.25, ease: "power2.in", immediateRender: false}}, {max(start + 0.4, end - 0.25):.3f});')
    faces = "\n".join(f'@font-face {{ font-family: "{fam}"; font-weight: {wt}; src: url("assets/fonts/{fn}"); }}' for fam, wt, fn in fonts)
    c = colors
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={panel_h}" />
    <script src="assets/gsap.min.js"></script>
    <style>
      {faces}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {panel_h}px; overflow: hidden; background: transparent; }}
      #root {{ position: relative; width: {W}px; height: {panel_h}px; font-family: "Brand", sans-serif; color: {c["text"]}; }}
      .scene {{ position: absolute; left: {px(X0)}; top: {px(Y0)}; width: {px(CW)}; }}
      .tag {{ display: inline-block; font-family: "Mono"; font-weight: 700; font-size: {px(26)}; letter-spacing: .08em; color: {c["accent"]};
              border: {px(3)} solid {c["accent"]}; border-radius: {px(8)}; padding: {px(4)} {px(14)}; margin-bottom: {px(18)}; background: rgba(126,217,87,.08); }}
      .win {{ background: {c["card"]}; border: {px(2)} solid {c["border"]}; border-radius: {px(22)}; overflow: hidden; }}
      .bar {{ display: flex; align-items: center; gap: {px(10)}; padding: {px(16)} {px(22)}; border-bottom: {px(2)} solid {c["border"]};
              font-family: "Mono"; font-size: {px(24)}; color: {c["dim"]}; }}
      .bar i {{ width: {px(14)}; height: {px(14)}; border-radius: 50%; background: {c["border"]}; display: inline-block; }}
      .bar span {{ margin-left: {px(8)}; }}
      .wb {{ padding: {px(20)} {px(18)} {px(24)}; min-height: {px(250)}; }}
      .ln {{ font-family: "Mono"; font-weight: 500; font-size: {px(32)}; line-height: {px(50)}; white-space: nowrap; display: flex; padding-left: {px(8)}; }}
      .ln .pr {{ width: {px(36)}; flex: none; color: {c["accent2"]}; }}
      .ln .tx {{ display: inline-block; overflow: hidden; }}
      .ln.ok .pr, .ln.ok .tx {{ color: {c["accent"]}; }}
      .ln.out .tx, .ln.dim .tx {{ color: {c["dim"]}; }}
      .ln.tree .pr {{ color: {c["dim"]}; width: {px(30)}; }}
      .ln.tree.hl {{ background: rgba(126,217,87,.14); border-radius: {px(8)}; }}
      .ln.tree.hl .tx {{ color: {c["accent"]}; }}
      .flow {{ display: flex; flex-direction: column; gap: {px(40)}; }}
      .rl {{ font-family: "Mono"; font-weight: 500; font-size: {px(24)}; letter-spacing: .14em; color: {c["dim"]}; text-transform: uppercase; margin-bottom: {px(16)}; }}
      .rl.big {{ font-size: {px(26)}; margin-bottom: {px(34)}; }}
      .cells {{ display: flex; align-items: center; gap: {px(10)}; }}
      .node {{ flex: 1; background: {c["card"]}; border: {px(2)} solid {c["border"]}; border-radius: {px(18)}; padding: {px(22)} {px(14)}; text-align: center; min-width: 0; }}
      .node b {{ display: block; font-weight: 600; font-size: {px(32)}; }}
      .node em {{ display: block; font-style: normal; font-family: "Mono"; font-size: {px(21)}; color: {c["dim"]}; margin-top: {px(6)}; }}
      .arrow {{ width: {px(54)}; height: {px(3)}; background: {c["dim"]}; position: relative; flex: none; transform-origin: left; }}
      .arrow:after {{ content: ""; position: absolute; right: -1px; top: {px(-8)}; border-left: {px(14)} solid {c["dim"]}; border-top: {px(9.5)} solid transparent; border-bottom: {px(9.5)} solid transparent; }}
      .cust {{ position: relative; }}
      .scene.custom {{ max-height: {px(MAX_HEIGHT)}; overflow: hidden; }}
      #root {{ --accent: {c["accent"]}; --accent2: {c["accent2"]}; --text: {c["text"]}; --dim: {c["dim"]}; --card: {c["card"]}; --border: {c["border"]}; }}
      .hd {{ font-family: "Mono"; font-weight: 700; font-size: {px(26)}; letter-spacing: .12em; color: {c["accent2"]}; margin: {px(2)} {px(8)} {px(8)}; }}
      .tg {{ margin-left: auto; display: flex; gap: {px(6)}; }}
      .tg b {{ font-family: "Mono"; font-weight: 500; font-size: {px(22)}; padding: {px(4)} {px(16)}; border-radius: 999px; color: {c["text"]}; }}
      .tg b.on {{ background: {c["accent2"]}; }}
      .ln.ck {{ align-items: center; font-size: {px(30)}; line-height: {px(46)}; border-radius: {px(8)}; }}
      .ln.ck .pr {{ color: {c["accent"]}; }}
      .ln.ck.todo .pr {{ color: {c["dim"]}; }}
      .ln.ck.flagged {{ background: rgba(251,71,222,.16); }}
      .ln.ck .bd {{ margin-left: auto; margin-right: {px(10)}; min-width: {px(40)}; text-align: center; border-radius: {px(10)}; background: {c["accent2"]}; font-weight: 700; }}
      .bubs {{ display: flex; flex-direction: column; gap: {px(18)}; }}
      .bub {{ max-width: 82%; width: fit-content; margin: {px(18)} 0 0 auto; padding: {px(16)} {px(28)}; border-radius: {px(28)}; background: {c["accent2"]}; color: #fff; font-weight: 600; font-size: {px(32)}; line-height: 1.25; }}
      .bubs .bub {{ margin-top: 0; }}
      .bub.agent {{ margin: 0 auto 0 0; background: {c["card"]}; border: {px(2)} solid {c["border"]}; }}
      .stp {{ display: flex; flex-direction: column; gap: {px(14)}; }}
      .sr {{ display: flex; align-items: center; gap: {px(24)}; }}
      .num {{ width: {px(60)}; height: {px(60)}; flex: none; border-radius: 50%; border: {px(3)} solid {c["accent"]}; color: {c["accent"]}; font-family: "Mono"; font-weight: 700; font-size: {px(30)}; display: flex; align-items: center; justify-content: center; }}
      .sr b {{ display: block; font-weight: 600; font-size: {px(34)}; }}
      .sr em {{ display: block; font-style: normal; font-family: "Mono"; font-size: {px(20)}; color: {c["dim"]}; margin-top: {px(4)}; }}
      .ttl .row {{ display: flex; align-items: center; gap: {px(34)}; }}
      .icon {{ width: {px(150)}; height: {px(150)}; border-radius: {px(30)}; border: {px(3)} solid {c["accent2"]}; background: {c["card"]};
               display: flex; align-items: center; justify-content: center; font-family: "Mono"; font-weight: 700; font-size: {px(64)}; color: {c["text"]}; }}
      .nm {{ font-weight: 600; font-size: {px(30)}; line-height: {px(36)}; margin: {px(12)} 0 0 {px(-30)}; width: {px(210)}; text-align: center; }}
      .its {{ display: flex; flex-direction: column; gap: {px(14)}; }}
      .item {{ font-weight: 600; font-size: {px(40)}; }}
      .item span {{ font-family: "Mono"; color: {c["accent"]}; margin-right: {px(14)}; }}
      {chr(10).join('      ' + x for x in css).strip()}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}" data-width="{W}" data-height="{panel_h}">
      {"".join(body)}
    </div>
    {MEASURE if measure else ""}
    <script>
      const tl = gsap.timeline({{ paused: true }});
      {chr(10).join("      " + j for j in js).strip()}
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
