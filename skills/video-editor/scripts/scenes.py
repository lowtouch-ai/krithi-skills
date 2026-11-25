"""Panel scenes for the explainer style: animated graphics above the speaker, drawn from templates.

The agent picks a scene type for each point in the talk and fills in its words (clips.json, "scenes"); this module checks the
data, finds the moment each scene and each of its parts is spoken, and builds the HyperFrames page that animates it. The look
(colours, type sizes, window styling) is fixed here and in brand.json, so scenes look the same whoever wrote them.

A scene:  {"type": "terminal", "say": "words that start it", "tag": "TIP 01", "data": {...}}
Every part (a terminal line, a tree row, a flow node, a title item) may carry its own "say"; parts without one are spread
evenly over the scene. A scene stays on screen until the next one starts (or the clip ends).
Types: title, terminal, tree, flow.
"""
import copy
import html
import re

SCENE_TYPES = ("title", "terminal", "tree", "flow")
MAX_SCENES_PER_MINUTE = 6
LIMITS = {
    "tag": 14, "title": 34, "label": 34, "text": 38, "sub": 24, "name": 24, "icon": 4,
    "terminal_lines": 7, "tree_rows": 8, "flow_nodes": 4, "flow_rows": 2, "title_items": 3,
}
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
    return []


def _flow_rows(d):
    if d.get("rows"):
        return d["rows"]
    return [{"label": d.get("label", ""), "nodes": d.get("nodes") or []}]


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

def build_page(scenes, colors, fonts, W, panel_h, duration):
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
                avail = (CW - (len(nodes) - 1) * (arrow_px + 20)) / max(len(nodes), 1) - 28  # width left for a node's text
                node_fs = int(min(32, max(20, avail / (0.60 * max(longest, 1)))))
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
        elif t == "title":
            icon = f'<div class="icon" id="{sid}i">{e(_s(d.get("icon")))}</div>' if _s(d.get("icon")) else ""
            name = f'<div class="nm">{e(_s(d.get("name")))}</div>' if _s(d.get("name")) else ""
            lab = f'<div class="rl big">{e(_s(d.get("label")))}</div>' if _s(d.get("label")) else ""
            items = []
            for i, it in enumerate(d.get("items") or []):
                items.append(f'<div class="item" id="{sid}it{i}"><span>{e(_s(it.get("n")))}</span>{e(_s(it.get("text")))}</div>')
                js.append(f'tl.fromTo("#{sid}it{i}", {{opacity: 0, x: {-16 * s:.0f}}}, {{opacity: 1, x: 0, duration: 0.3, ease: "power2.out"}}, {at(i):.3f});')
            inner = f'<div class="ttl">{lab}<div class="row">{icon}<div class="its">{"".join(items)}</div></div>{name}</div>'
        body.append(f'<div id="{sid}" class="clip scene" data-start="{start:.3f}" data-duration="{dur:.3f}" data-track-index="0">{tagh}{inner}</div>')
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
      .ttl .row {{ display: flex; align-items: center; gap: {px(34)}; }}
      .icon {{ width: {px(150)}; height: {px(150)}; border-radius: {px(30)}; border: {px(3)} solid {c["accent2"]}; background: {c["card"]};
               display: flex; align-items: center; justify-content: center; font-family: "Mono"; font-weight: 700; font-size: {px(64)}; color: {c["text"]}; }}
      .nm {{ font-weight: 600; font-size: {px(30)}; margin-top: {px(12)}; width: {px(150)}; text-align: center; }}
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
    <script>
      const tl = gsap.timeline({{ paused: true }});
      {chr(10).join("      " + j for j in js).strip()}
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
