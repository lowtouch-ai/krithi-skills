"""Exact text widths from a TrueType font file (stdlib only), for sizing pills, boxes and lower thirds.

Usage as a module: Font(path).width("Domain knowledge", ass_size) -> pixels as libass draws it.
libass treats the ASS font size as the line height (the font's OS/2 win ascent + descent), not the em size, so letters are smaller
than the number suggests; Font.em(ass_size) converts.
"""
import struct
from pathlib import Path


class Font:
    def __init__(self, path):
        d = Path(path).read_bytes()
        n = struct.unpack(">H", d[4:6])[0]
        t = {}
        for i in range(n):
            tag, _, off, ln = struct.unpack(">4sIII", d[12 + 16 * i: 28 + 16 * i])
            t[tag.decode("latin1")] = (off, ln)
        self.upm = struct.unpack(">H", d[t["head"][0] + 18: t["head"][0] + 20])[0]
        h = t["hhea"][0]
        self.asc, self.desc = struct.unpack(">hh", d[h + 4: h + 8])
        o2 = t["OS/2"][0]
        win_a, win_d = struct.unpack(">HH", d[o2 + 74: o2 + 78])
        self.win = win_a + win_d  # libass scales the ASS size by this, not by hhea
        self.nh = struct.unpack(">H", d[h + 34: h + 36])[0]
        m = t["hmtx"][0]
        self.adv = [struct.unpack(">H", d[m + 4 * i: m + 4 * i + 2])[0] for i in range(self.nh)]
        self.cmap = self._cmap(d, t["cmap"][0])

    def _cmap(self, d, off):
        nt = struct.unpack(">H", d[off + 2: off + 4])[0]
        sub = None
        for i in range(nt):
            pid, eid, o = struct.unpack(">HHI", d[off + 4 + 8 * i: off + 12 + 8 * i])
            if (pid, eid) in ((3, 1), (0, 3), (0, 4)) and struct.unpack(">H", d[off + o: off + o + 2])[0] == 4:
                sub = off + o
        mp = {}
        if sub is None:
            return mp
        segx2 = struct.unpack(">H", d[sub + 6: sub + 8])[0]
        sc = segx2 // 2
        ends = struct.unpack(">%dH" % sc, d[sub + 14: sub + 14 + segx2])
        starts = struct.unpack(">%dH" % sc, d[sub + 16 + segx2: sub + 16 + 2 * segx2])
        deltas = struct.unpack(">%dh" % sc, d[sub + 16 + 2 * segx2: sub + 16 + 3 * segx2])
        ro_pos = sub + 16 + 3 * segx2
        ros = struct.unpack(">%dH" % sc, d[ro_pos: ro_pos + segx2])
        for s in range(sc):
            for c in range(starts[s], ends[s] + 1):
                if c == 0xFFFF:
                    continue
                if ros[s] == 0:
                    g = (c + deltas[s]) & 0xFFFF
                else:
                    p = ro_pos + 2 * s + ros[s] + 2 * (c - starts[s])
                    g = struct.unpack(">H", d[p: p + 2])[0]
                    g = (g + deltas[s]) & 0xFFFF if g else 0
                mp[c] = g
        return mp

    def _adv(self, ch):
        g = self.cmap.get(ord(ch), 0)
        return self.adv[min(g, self.nh - 1)]

    def em(self, ass_size):
        """Pixels per em when libass draws the given ASS font size."""
        return ass_size * self.upm / float(self.win or (self.asc - self.desc))

    def width(self, text, ass_size):
        return sum(self._adv(c) for c in text) * self.em(ass_size) / self.upm
