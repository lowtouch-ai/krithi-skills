"""One layout for the keyword cards, shared by the built-in ffmpeg cards and the HyperFrames cards.

The panel is sized from the card's own text (label, terms, number of terms) and sits inside a box that starts below the
captions and ends above the platform buttons, so a card can never reach the captions. When the terms do not fit, the type
is made smaller (down to `min_scale`), and only then does the panel grow past the box. The proportions come from brand.json
(`shorts.cards`), measured from the reference reel; the defaults below are those measurements for a 1080 px wide frame.
"""

DEFAULTS = {
    "label_px": 30,        # label type size (em, px at 1080 wide)
    "pill_px": 44,         # term type size
    "pill_height": 1.55,   # pill height, in em of the term type
    "pill_pad_x": 0.75,    # pill side padding, in em
    "gap_px": 14,          # space between pills
    "pad_x": 40,           # panel side padding
    "pad_y": 30,           # panel top and bottom padding
    "width_min": 0.54,     # panel width as a share of the frame, smallest and largest
    "width_max": 0.86,
    "box_top": None,       # the card box, as shares of the frame height: starts below the captions (CAPTION_Y + CAPTION_CLEAR) ...
    "box_bottom": 0.925,   # ... and above the platform buttons
    "min_scale": 0.7,      # smallest the type is made to fit many terms
}
CAPTION_Y = 0.715      # where the captions are centred (share of the height); render_shorts.py draws them here
CAPTION_CLEAR = 0.055  # from there to the top of the card box: half a caption line plus a margin
LABEL_SPACING = 0.10  # letter spacing of the label, in em (both renderers)


def settings(brand):
    cfg = {**DEFAULTS, **(brand.get("shorts", {}).get("cards") or {})}
    if cfg["box_top"] is None:
        cfg["box_top"] = CAPTION_Y + CAPTION_CLEAR
    return cfg


def layout(card, W, H, F, cfg):  # cfg from settings()
    """Geometry of one card in output pixels. F is the (semibold) fontmetrics.Font used for the text."""
    items, n = card["items"], len(card["items"])
    s0 = W / 1080.0
    box_h = (cfg["box_bottom"] - cfg["box_top"]) * H
    scale = 1.0
    while True:
        label_em, pill_em = cfg["label_px"] * s0 * scale, cfg["pill_px"] * s0 * scale
        ph = cfg["pill_height"] * pill_em
        pad_pill = cfg["pill_pad_x"] * pill_em
        gap = cfg["gap_px"] * s0 * scale
        arrow_h = 0.5 * pill_em if card.get("chain") else 0.0
        pad_x, pad_y = cfg["pad_x"] * s0, cfg["pad_y"] * s0 * scale
        label_band = label_em * 2.2
        pill_w = [F.width(it["text"], pill_em / F.em(1)) + 2 * pad_pill for it in items]
        label_w = F.width(card["label"], label_em / F.em(1)) + LABEL_SPACING * label_em * len(card["label"])
        panel_h = pad_y + label_band + n * ph + (n - 1) * (gap + arrow_h) + pad_y * 0.9
        if panel_h <= box_h or scale <= cfg["min_scale"] + 1e-9:
            break
        scale = max(cfg["min_scale"], scale - 0.04)
    panel_w = min(cfg["width_max"] * W, max(cfg["width_min"] * W, max(max(pill_w), label_w) + 2 * pad_x))
    bottom = cfg["box_bottom"] * H
    if panel_h > box_h:  # even the smallest type does not fit: grow downward, but keep clear of the screen edge
        bottom = min(0.95 * H, cfg["box_top"] * H + panel_h)
    return {"scale": scale, "label_em": label_em, "pill_em": pill_em, "ph": ph, "pad_pill": pad_pill, "gap": gap,
            "arrow_h": arrow_h, "pad_x": pad_x, "pad_y": pad_y, "label_band": label_band, "pill_w": pill_w,
            "panel_w": panel_w, "panel_h": panel_h, "bottom": bottom, "top": bottom - panel_h}
