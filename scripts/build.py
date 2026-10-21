#!/usr/bin/env python3
"""Builds every image in assets/ (dark + light) and the generated blocks of README.md.

    python3 scripts/build.py                # static images + live GitHub stats (needs GH_TOKEN)
    python3 scripts/build.py --placeholder  # static images + "first run pending" stats
    python3 scripts/build.py --sample       # static images + made-up stats (local preview only)

Standard library only (Python 3.11+), so the workflow needs no installs.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import random
import re
import sys
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"

THEMES = {
    "dark": dict(
        bg="#0f1621", bg2="#141d2b", border="#223044", text="#e6edf3", muted="#9aa7b8",
        dim="#617084", grid="#1c2838", amber="#f5a524", teal="#2dd4bf", coral="#fb7185",
    ),
    "light": dict(
        bg="#ffffff", bg2="#f6f8fa", border="#d8dee4", text="#1f2328", muted="#57606a",
        dim="#8c959f", grid="#e6eaef", amber="#b45309", teal="#0f766e", coral="#be123c",
    ),
}
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
BASE_CSS = (
    f".s{{font-family:{SANS}}}.m{{font-family:{MONO}}}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
)

esc = lambda s: html.escape(str(s), quote=True)


# ── text measuring (approximate; SVG has no layout engine) ──────────────────
NARROW = set("iljtfr.,:;'!|()[]I ")
WIDE = set("mwMW@%")


def text_w(s: str, size: float, mono=False, bold=False) -> float:
    if mono:
        return len(s) * 0.6 * size
    w = 0.0
    for c in s:
        if c in NARROW:
            w += 0.29
        elif c in WIDE:
            w += 0.84
        elif c.isupper():
            w += 0.68
        elif c.isdigit():
            w += 0.58
        else:
            w += 0.56
    return w * size * (1.06 if bold else 1.0)


def wrap(s: str, size: float, max_w: float, max_lines=3) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if text_w(trial, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:") + "…"
    return lines


def svg(w, h, body, css, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'fill="none" role="img" aria-labelledby="title"><title id="title">{esc(title)}</title>'
        f"<style>{BASE_CSS}{css}</style>{body}</svg>"
    )


def card_frame(w, h, t, r=16, uid="c"):
    """Rounded card background + clip path id."""
    return (
        f'<defs><clipPath id="{uid}"><rect width="{w}" height="{h}" rx="{r}"/></clipPath></defs>'
        f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{r}" fill="{t["bg"]}" stroke="{t["border"]}"/>'
    )


# ── header ──────────────────────────────────────────────────────────────────
def header(cfg, t):
    W, H = 1000, 300
    u = cfg["user"]
    rnd = random.Random(7)

    # neural net on the right
    layers = [3, 5, 5, 2]
    x0, x1, cy, gap = 655, 925, 160, 36
    nodes = [
        [(x0 + (x1 - x0) * li / (len(layers) - 1), cy + (k - (n - 1) / 2) * gap) for k in range(n)]
        for li, n in enumerate(layers)
    ]
    edges = [(a, b) for li in range(len(layers) - 1) for a in nodes[li] for b in nodes[li + 1]]
    net = [f'<g stroke="{t["border"]}" stroke-width="1">']
    net += [f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}"/>' for a, b in edges]
    net.append("</g>")
    for i, ei in enumerate(rnd.sample(range(len(edges)), 14)):
        (ax, ay), (bx, by) = edges[ei]
        col = t["amber"] if i % 2 == 0 else t["teal"]
        net.append(
            f'<line class="pulse" x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" pathLength="100" '
            f'stroke="{col}" stroke-width="2.2" stroke-linecap="round" '
            f'style="animation-delay:{i * 0.37:.2f}s;animation-duration:{2.8 + rnd.random() * 1.6:.2f}s"/>'
        )
    for li, layer in enumerate(nodes):
        for k, (x, y) in enumerate(layer):
            col = [t["amber"], t["teal"], t["teal"], t["coral"]][li]
            d = rnd.random() * 3
            net.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{t["bg"]}" stroke="{col}" stroke-width="1.6"/>'
                f'<circle class="fire" cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{col}" style="animation-delay:{d:.2f}s"/>'
            )

    # chips
    chips, cx = [], 56
    for i, label in enumerate(u.get("chips", [])):
        w = text_w(label, 13, mono=True) + 26
        col = t["amber"] if i == 0 else t["border"]
        txt = t["amber"] if i == 0 else t["muted"]
        chips.append(
            f'<g class="rise" style="animation-delay:{0.55 + i * 0.08:.2f}s">'
            f'<rect x="{cx}" y="222" width="{w:.1f}" height="30" rx="15" fill="{t["bg2"]}" stroke="{col}"/>'
            f'<text class="m" x="{cx + w / 2:.1f}" y="241.5" font-size="13" fill="{txt}" text-anchor="middle">{esc(label)}</text></g>'
        )
        cx += w + 10

    css = (
        "@keyframes drift{0%,100%{transform:translate(0,0)}50%{transform:translate(46px,22px)}}"
        "@keyframes drift2{0%,100%{transform:translate(0,0)}50%{transform:translate(-40px,-18px)}}"
        ".g1{animation:drift 14s ease-in-out infinite}.g2{animation:drift2 17s ease-in-out infinite}"
        "@keyframes flow{0%{stroke-dashoffset:8}62%,100%{stroke-dashoffset:-100}}"
        ".pulse{stroke-dasharray:8 220;stroke-dashoffset:-100;animation:flow 3s linear infinite}"
        "@keyframes fire{0%,100%{opacity:.25}50%{opacity:1}}.fire{animation:fire 3.2s ease-in-out infinite}"
        "@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}"
        ".rise{animation:rise .9s cubic-bezier(.2,.7,.2,1) both}"
        "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}.cur{animation:blink 1.1s steps(1) infinite}"
    )
    gw = text_w(u.get("greeting", ""), 15, mono=True)
    body = (
        card_frame(W, H, t, r=20, uid="hc")
        + f'<defs><pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="2" cy="2" r="1.1" fill="{t["grid"]}"/></pattern>'
        f'<radialGradient id="ga"><stop offset="0" stop-color="{t["amber"]}" stop-opacity=".22"/>'
        f'<stop offset="1" stop-color="{t["amber"]}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="gt"><stop offset="0" stop-color="{t["teal"]}" stop-opacity=".18"/>'
        f'<stop offset="1" stop-color="{t["teal"]}" stop-opacity="0"/></radialGradient></defs>'
        f'<g clip-path="url(#hc)"><rect width="{W}" height="{H}" fill="url(#dots)"/>'
        f'<circle class="g1" cx="140" cy="40" r="300" fill="url(#ga)"/>'
        f'<circle class="g2" cx="860" cy="270" r="280" fill="url(#gt)"/></g>'
        + "".join(net)
        + f'<text class="m rise" x="56" y="84" font-size="15" fill="{t["dim"]}">{esc(u.get("greeting", ""))}</text>'
        f'<rect class="cur" x="{56 + gw + 6:.1f}" y="72" width="8" height="16" fill="{t["amber"]}"/>'
        f'<text class="s rise" x="54" y="148" font-size="56" font-weight="700" letter-spacing="-1.2" '
        f'fill="{t["text"]}" style="animation-delay:.12s">{esc(u["name"])}</text>'
        f'<text class="s rise" x="56" y="190" font-size="19" fill="{t["muted"]}" style="animation-delay:.3s">'
        f'{esc(u.get("headline", ""))}</text>'
        + "".join(chips)
        + (
            f'<text class="m" x="{W - 30}" y="{H - 22}" font-size="12" fill="{t["dim"]}" text-anchor="end">'
            f'◉ {esc(u["location"])}</text>'
            if u.get("location")
            else ""
        )
    )
    return svg(W, H, body, css, f'{u["name"]} — {u.get("headline", "")}')


# ── typing banner (SMIL, discrete frames → no font-dependent drift) ─────────
def typing(cfg, t):
    W, H, size = 1000, 56, 21
    cw = size * 0.6
    lines = cfg["typing"]["lines"]
    type_t, hold, erase_t, gap = 0.055, 2.0, 0.02, 0.4
    spans, s = [], 0.0
    for ln in lines:
        n = len(ln)
        spans.append((s, n))
        s += n * type_t + hold + n * erase_t + gap
    total = s
    parts = []
    for i, ((start, n), ln) in enumerate(zip(spans, lines)):
        x0 = W / 2 - n * cw / 2
        frames = [(0.0, 0)]
        for k in range(1, n + 1):
            frames.append((start + k * type_t, k))
        e0 = start + n * type_t + hold
        for k in range(n - 1, -1, -1):
            frames.append((e0 + (n - k) * erase_t, k))
        frames = sorted({round(f[0] / total, 5): f[1] for f in frames}.items())
        kt = ";".join(f"{a:.5f}" for a, _ in frames)
        wv = ";".join(f"{k * cw:.1f}" for _, k in frames)
        xv = ";".join(f"{x0 + k * cw + 2:.1f}" for _, k in frames)
        on_end = e0 + n * erase_t
        vis = [(0.0, 0), (round(start / total, 5), 1), (round(on_end / total, 5), 0)]
        vis = sorted(dict(vis).items())
        vkt = ";".join(f"{a:.5f}" for a, _ in vis)
        vv = ";".join(str(v) for _, v in vis)
        anim = f'dur="{total:.2f}s" repeatCount="indefinite" calcMode="discrete"'
        parts.append(
            f'<clipPath id="c{i}"><rect x="{x0:.1f}" y="0" width="0" height="{H}">'
            f'<animate attributeName="width" values="{wv}" keyTimes="{kt}" {anim}/></rect></clipPath>'
            f'<text class="m" x="{x0:.1f}" y="35" font-size="{size}" textLength="{n * cw:.1f}" '
            f'lengthAdjust="spacing" fill="{t["teal"]}" clip-path="url(#c{i})">{esc(ln)}</text>'
            f'<g opacity="{1 if i == 0 else 0}"><animate attributeName="opacity" values="{vv}" keyTimes="{vkt}" {anim}/>'
            f'<rect class="cur" x="{x0:.1f}" y="15" width="11" height="25" rx="1.5" fill="{t["amber"]}">'
            f'<animate attributeName="x" values="{xv}" keyTimes="{kt}" {anim}/></rect></g>'
        )
    css = "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}.cur{animation:blink 1s steps(1) infinite}"
    return svg(W, H, "".join(parts), css, " · ".join(lines))


# ── project cards ───────────────────────────────────────────────────────────
def icon(kind, x, y, col, t):
    cx, cy = x + 22, y + 22
    if kind == "voice":
        hs = [8, 16, 22, 14, 9]
        return "".join(
            f'<rect class="eq" x="{cx - 12 + i * 5.5:.1f}" y="{cy - h / 2:.1f}" width="3" height="{h}" rx="1.5" '
            f'fill="{col}" style="animation-delay:{i * 0.13:.2f}s"/>'
            for i, h in enumerate(hs)
        )
    if kind == "shield":
        return (
            f'<path d="M{cx},{cy - 12} l10,4 v6 c0,7 -4.5,11 -10,13 c-5.5,-2 -10,-6 -10,-13 v-6 z" '
            f'stroke="{col}" stroke-width="2" stroke-linejoin="round"/>'
            f'<path class="tick" d="M{cx - 4.5},{cy + 0.5} l3.2,3.2 l6,-6.5" stroke="{col}" stroke-width="2.2" '
            f'stroke-linecap="round" stroke-linejoin="round" pathLength="1"/>'
        )
    if kind == "orbit":
        return (
            f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="{col}"/>'
            f'<g class="spin" style="transform-origin:{cx}px {cy}px">'
            f'<ellipse cx="{cx}" cy="{cy}" rx="13" ry="5.5" stroke="{col}" stroke-width="1.6" transform="rotate(-25 {cx} {cy})"/>'
            f'<circle cx="{cx + 11.8:.1f}" cy="{cy - 5.4:.1f}" r="2.2" fill="{col}"/></g>'
        )
    if kind == "chart":
        hs = [8, 14, 11, 20]
        return "".join(
            f'<rect class="bar" x="{cx - 11 + i * 6:.1f}" y="{cy + 10 - h:.1f}" width="4" height="{h}" rx="1.2" '
            f'fill="{col}" style="animation-delay:{0.2 + i * 0.12:.2f}s"/>'
            for i, h in enumerate(hs)
        )
    # spark (default)
    return (
        f'<path class="spin" style="transform-origin:{cx}px {cy}px" d="M{cx},{cy - 12} L{cx + 3},{cy - 3} L{cx + 12},{cy} '
        f'L{cx + 3},{cy + 3} L{cx},{cy + 12} L{cx - 3},{cy + 3} L{cx - 12},{cy} L{cx - 3},{cy - 3} Z" fill="{col}"/>'
    )


def project_card(p, t):
    W, H = 480, 240
    col = t.get(p.get("accent", "amber"), t["amber"])
    badge = p.get("badge", "")
    bw = text_w(badge, 11.5, mono=True) + 18
    desc = wrap(p["description"], 14.5, W - 60, 3)
    chips, cx = [], 24
    for s in p.get("stack", []):
        w = text_w(s, 12, mono=True) + 20
        if cx + w > W - 24:
            break
        chips.append(
            f'<rect x="{cx}" y="{H - 50}" width="{w:.1f}" height="26" rx="13" fill="{t["bg2"]}" stroke="{t["border"]}"/>'
            f'<text class="m" x="{cx + w / 2:.1f}" y="{H - 32.5}" font-size="12" fill="{t["muted"]}" text-anchor="middle">{esc(s)}</text>'
        )
        cx += w + 8
    live = ""
    if p.get("live"):
        live = (
            f'<circle class="ping" cx="{W - 70}" cy="40" r="4" fill="{t["teal"]}" style="transform-origin:{W - 70}px 40px"/>'
            f'<circle cx="{W - 70}" cy="40" r="4" fill="{t["teal"]}"/>'
            f'<text class="m" x="{W - 24}" y="44.5" font-size="12.5" fill="{t["teal"]}" text-anchor="end">live</text>'
        )
    css = (
        "@keyframes sweep{from{transform:translateX(-200px)}to{transform:translateX(680px)}}"
        ".sw{animation:sweep 5s cubic-bezier(.45,0,.55,1) infinite}"
        "@keyframes eq{0%,100%{transform:scaleY(.45)}50%{transform:scaleY(1)}}"
        ".eq{transform-box:fill-box;transform-origin:center;animation:eq 1.1s ease-in-out infinite}"
        "@keyframes tick{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
        ".tick{stroke-dasharray:1;animation:tick 1.2s .4s ease-out both}"
        "@keyframes spin{to{transform:rotate(360deg)}}.spin{animation:spin 9s linear infinite}"
        "@keyframes bar{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
        ".bar{transform-box:fill-box;transform-origin:bottom;animation:bar .8s cubic-bezier(.2,.7,.2,1) both}"
        "@keyframes ping{0%{transform:scale(1);opacity:.7}100%{transform:scale(3.2);opacity:0}}"
        ".ping{animation:ping 1.8s ease-out infinite}"
    )
    body = (
        card_frame(W, H, t, uid="pc")
        + f'<defs><linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="{col}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{col}"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>'
        f'<g clip-path="url(#pc)"><rect class="sw" x="0" y="0" width="200" height="2.5" fill="url(#sg)"/></g>'
        f'<rect x="24" y="24" width="44" height="44" rx="12" fill="{col}" fill-opacity=".12" stroke="{col}" stroke-opacity=".35"/>'
        + icon(p.get("icon", "spark"), 24, 24, col, t)
        + f'<text class="s" x="84" y="44" font-size="20" font-weight="700" fill="{t["text"]}">{esc(p["name"])}</text>'
        f'<rect x="84" y="53" width="{bw:.1f}" height="20" rx="10" fill="{col}" fill-opacity=".12"/>'
        f'<text class="m" x="{84 + bw / 2:.1f}" y="67" font-size="11.5" fill="{col}" text-anchor="middle">{esc(badge)}</text>'
        + live
        + "".join(
            f'<text class="s" x="24" y="{110 + i * 22}" font-size="14.5" fill="{t["muted"]}">{esc(line)}</text>'
            for i, line in enumerate(desc)
        )
        + "".join(chips)
    )
    return svg(W, H, body, css, f'{p["name"]}: {p["description"]}')


# ── timeline ────────────────────────────────────────────────────────────────
def timeline(cfg, t):
    items = cfg["timeline"]
    n = len(items)
    W, H, ly = 1000, 214, 76
    xs = [110 + i * (780 / max(n - 1, 1)) for i in range(n)]
    last_done = max([i for i, it in enumerate(items) if it.get("status") != "next"], default=0)
    css = (
        "@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
        ".draw{stroke-dasharray:1;animation:draw 1.6s cubic-bezier(.4,0,.2,1) both}"
        "@keyframes pop{from{opacity:0;transform:scale(.3)}to{opacity:1;transform:none}}"
        ".pop{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.3,1.6,.5,1) both}"
        "@keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
        ".fade{animation:fade .6s ease-out both}"
        "@keyframes halo{0%{transform:scale(1);opacity:.6}100%{transform:scale(2.6);opacity:0}}"
        ".halo{transform-box:fill-box;transform-origin:center;animation:halo 2s ease-out infinite}"
    )
    parts = [
        f'<line x1="{xs[0]}" y1="{ly}" x2="{xs[-1]}" y2="{ly}" stroke="{t["border"]}" stroke-width="2" stroke-dasharray="4 6"/>',
        f'<line class="draw" x1="{xs[0]}" y1="{ly}" x2="{xs[last_done]}" y2="{ly}" stroke="{t["amber"]}" '
        f'stroke-width="2.5" stroke-linecap="round" pathLength="1"/>',
    ]
    for i, (x, it) in enumerate(zip(xs, items)):
        nxt = it.get("status") == "next"
        col = t["coral"] if nxt else t["amber"]
        d = 0.35 + i * 0.28
        if nxt:
            parts.append(f'<circle class="halo" cx="{x:.1f}" cy="{ly}" r="9" fill="{col}" style="animation-delay:{d + .5:.2f}s"/>')
        parts.append(
            f'<g class="pop" style="animation-delay:{d:.2f}s">'
            f'<circle cx="{x:.1f}" cy="{ly}" r="10" fill="{t["bg"]}" stroke="{col}" stroke-width="2.4"'
            + (' stroke-dasharray="3 3"' if nxt else "")
            + f'/><circle cx="{x:.1f}" cy="{ly}" r="{3.5 if nxt else 4.5}" fill="{col}"/></g>'
        )
        sub = wrap(it.get("detail", ""), 13, 178, 3)
        parts.append(
            f'<g class="fade" style="animation-delay:{d + .1:.2f}s">'
            f'<text class="m" x="{x:.1f}" y="{ly - 30}" font-size="12.5" fill="{col}" text-anchor="middle">{esc(it["when"])}</text>'
            f'<text class="s" x="{x:.1f}" y="{ly + 42}" font-size="15" font-weight="650" fill="{t["text"]}" text-anchor="middle">{esc(it["title"])}</text>'
            + "".join(
                f'<text class="s" x="{x:.1f}" y="{ly + 64 + k * 18}" font-size="13" fill="{t["muted"]}" text-anchor="middle">{esc(s)}</text>'
                for k, s in enumerate(sub)
            )
            + "</g>"
        )
    return svg(W, H, "".join(parts), css, "Timeline: " + "; ".join(f'{i["when"]} {i["title"]}' for i in items))


# ── footer ──────────────────────────────────────────────────────────────────
def footer(cfg, t):
    W, H = 1000, 120

    def wave(base, amp, period, phase):
        return [(x, base + amp * math.sin(2 * math.pi * x / period + phase)) for x in range(0, 2001, 10)]

    def line_d(pts):
        return "M" + " L".join(f"{x},{y:.1f}" for x, y in pts)

    layers = [
        (t["amber"], wave(68, 11, 500, 0.0), 18),
        (t["teal"], wave(80, 9, 500, 1.6), 13),
        (t["coral"], wave(92, 6, 250, 2.8), 9),
    ]
    css = "@keyframes slide{to{transform:translateX(-1000px)}}" + "".join(
        f".w{i}{{animation:slide {d}s linear infinite}}" for i, (_, _, d) in enumerate(layers)
    )
    waves = "".join(
        f'<g class="w{i}"><path d="{line_d(p)} L2000,{H} L0,{H} Z" fill="{c}" fill-opacity=".06"/>'
        f'<path d="{line_d(p)}" stroke="{c}" stroke-opacity=".7" stroke-width="1.6"/></g>'
        for i, (c, p, _) in enumerate(layers)
    )
    body = (
        '<defs><linearGradient id="fx"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".18" stop-color="#fff"/><stop offset=".82" stop-color="#fff"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        '<linearGradient id="fy" x1="0" y1="0" x2="0" y2="1"><stop offset=".55" stop-color="#fff"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="mx"><rect width="{W}" height="{H}" fill="url(#fx)"/></mask>'
        f'<mask id="my"><rect width="{W}" height="{H}" fill="url(#fy)"/></mask></defs>'
        f'<g mask="url(#mx)"><g mask="url(#my)">{waves}</g></g>'
        f'<text class="m" x="{W / 2}" y="30" font-size="13" fill="{t["dim"]}" text-anchor="middle">'
        "thanks for stopping by · let's build something</text>"
    )
    return svg(W, H, body, css, "Thanks for stopping by")


# ── live stats ──────────────────────────────────────────────────────────────
GQL_MAIN = """
query($login:String!){ user(login:$login){
  createdAt
  pullRequests{ totalCount }
  repositories(ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC, first:100){
    totalCount
    nodes{ languages(first:10, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name color } } } }
  }
  contributionsCollection{
    totalCommitContributions
    contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
  }
}}"""
GQL_YEAR = """
query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
  contributionsCollection(from:$from, to:$to){
    contributionCalendar{ weeks{ contributionDays{ date contributionCount } } }
  }
}}"""


def gql(query, variables, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-build"},
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.load(r)
    if data.get("errors"):
        raise RuntimeError(data["errors"])
    return data["data"]["user"]


def days_of(cal):
    return {d["date"]: d["contributionCount"] for w in cal["weeks"] for d in w["contributionDays"]}


def fetch_stats(cfg, token):
    login = cfg["user"]["login"]
    u = gql(GQL_MAIN, {"login": login}, token)
    cal = u["contributionsCollection"]["contributionCalendar"]
    last_year = days_of(cal)

    # every day since the account was created, for the longest streak
    all_days = dict(last_year)
    created = dt.datetime.fromisoformat(u["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    for year in range(created.year, now.year + 1):
        start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        end = min(now, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
        y = gql(GQL_YEAR, {"login": login, "from": start.isoformat(), "to": end.isoformat()}, token)
        all_days.update(days_of(y["contributionsCollection"]["contributionCalendar"]))

    langs = {}
    excl = set(cfg.get("stats", {}).get("exclude_languages", []))
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            if name in excl:
                continue
            size, color = langs.get(name, (0, e["node"]["color"] or "#8c959f"))
            langs[name] = (size + e["size"], color)

    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    week_starts = [w["contributionDays"][0]["date"] for w in cal["weeks"]]
    return dict(
        past_year=cal["totalContributions"],
        active_days=sum(1 for c in last_year.values() if c > 0),
        longest=longest_streak(all_days),
        commits=u["contributionsCollection"]["totalCommitContributions"],
        prs=u["pullRequests"]["totalCount"],
        repos=u["repositories"]["totalCount"],
        langs=langs,
        weeks=weeks,
        week_starts=week_starts,
    )


def longest_streak(days: dict) -> int:
    best = run = 0
    prev = None
    for date in sorted(days):
        d = dt.date.fromisoformat(date)
        if days[date] > 0:
            run = run + 1 if prev and (d - prev).days == 1 and run else 1
            best = max(best, run)
        else:
            run = 0
        prev = d
    return best


def sample_stats():
    rnd = random.Random(42)
    today = dt.date(2026, 10, 18)
    starts = [(today - dt.timedelta(weeks=52 - i)).isoformat() for i in range(53)]
    weeks = []
    for i in range(53):
        base = 2 if i < 20 else 6 if i < 40 else 14
        burst = 30 if i in (44, 45, 49, 50) else 0
        weeks.append(max(0, int(base + rnd.gauss(0, base * 0.6)) + burst))
    return dict(
        past_year=sum(weeks), active_days=118, longest=17, commits=sum(weeks) - 40, prs=23, repos=9,
        langs={"Python": (520_000, "#3572A5"), "JavaScript": (310_000, "#f1e05a"), "TypeScript": (150_000, "#3178c6"),
               "HTML": (90_000, "#e34c26"), "CSS": (60_000, "#663399"), "PLpgSQL": (20_000, "#336790")},
        weeks=weeks, week_starts=starts,
    )


def fmt(n: int) -> str:
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 10_000 else f"{n:,}"


def stats_card(st, t, updated):
    W, H = 480, 240
    cells = [
        (fmt(st["past_year"]), "contributions", "past year", t["amber"]),
        (fmt(st["active_days"]), "active days", "past year", t["teal"]),
        (f'{st["longest"]}d', "longest streak", "all time", t["coral"]),
        (fmt(st["commits"]), "commits", "past year", t["amber"]),
        (fmt(st["prs"]), "pull requests", "all time", t["teal"]),
        (fmt(st["repos"]), "public repos", "owned", t["coral"]),
    ]
    parts = [
        card_frame(W, H, t, uid="sc"),
        f'<text class="s" x="24" y="40" font-size="16" font-weight="700" fill="{t["text"]}">GitHub at a glance</text>',
        f'<text class="m" x="{W - 24}" y="40" font-size="11" fill="{t["dim"]}" text-anchor="end">updated {esc(updated)}</text>',
        f'<line x1="24" y1="58" x2="{W - 24}" y2="58" stroke="{t["border"]}"/>',
    ]
    for i, (val, label, sub, col) in enumerate(cells):
        x, y = 24 + (i % 3) * 148, 102 + (i // 3) * 80
        parts.append(
            f'<g class="up" style="animation-delay:{0.1 + i * 0.09:.2f}s">'
            f'<rect x="{x}" y="{y - 25}" width="3" height="60" rx="1.5" fill="{col}"/>'
            f'<text class="s" x="{x + 14}" y="{y}" font-size="28" font-weight="700" fill="{t["text"]}">{esc(val)}</text>'
            f'<text class="s" x="{x + 14}" y="{y + 19}" font-size="12.5" fill="{t["muted"]}">{esc(label)}</text>'
            f'<text class="m" x="{x + 14}" y="{y + 34}" font-size="10.5" fill="{t["dim"]}">{esc(sub)}</text></g>'
        )
    css = "@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}.up{animation:up .6s ease-out both}"
    return svg(W, H, "".join(parts), css, f'GitHub stats: {st["past_year"]} contributions in the past year')


def languages_card(st, t):
    W, H = 480, 240
    items = sorted(st["langs"].items(), key=lambda kv: -kv[1][0])
    total = sum(s for s, _ in st["langs"].values()) or 1
    top = items[:5]
    rest = sum(s for _, (s, _) in items[5:])
    rows = [(n, s / total, c) for n, (s, c) in top] + ([("Other", rest / total, t["dim"])] if rest else [])
    bx, bw, by = 24, W - 48, 78
    segs, x = [], bx
    for _, frac, c in rows:
        w = bw * frac
        segs.append(f'<rect x="{x:.2f}" y="{by}" width="{max(w, 0):.2f}" height="12" fill="{c}"/>')
        x += w
    legend = []
    for i, (name, frac, c) in enumerate(rows):
        lx, ly = 24 + (i % 2) * 224, 128 + (i // 2) * 32
        legend.append(
            f'<g class="up" style="animation-delay:{0.5 + i * 0.07:.2f}s">'
            f'<circle cx="{lx + 6}" cy="{ly - 4.5}" r="5.5" fill="{c}"/>'
            f'<text class="s" x="{lx + 20}" y="{ly}" font-size="13.5" fill="{t["text"]}">{esc(name)}</text>'
            f'<text class="m" x="{lx + 200}" y="{ly}" font-size="12.5" fill="{t["muted"]}" text-anchor="end">{frac * 100:.1f}%</text></g>'
        )
    css = (
        "@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
        f".grow{{transform-origin:{bx}px {by}px;animation:grow 1.2s cubic-bezier(.2,.7,.2,1) both}}"
        "@keyframes up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}.up{animation:up .5s ease-out both}"
    )
    body = (
        card_frame(W, H, t, uid="lc")
        + f'<defs><clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6"/></clipPath></defs>'
        f'<text class="s" x="24" y="40" font-size="16" font-weight="700" fill="{t["text"]}">Languages</text>'
        f'<text class="m" x="{W - 24}" y="40" font-size="11" fill="{t["dim"]}" text-anchor="end">public repos · by code size</text>'
        f'<line x1="24" y1="58" x2="{W - 24}" y2="58" stroke="{t["border"]}"/>'
        f'<rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6" fill="{t["bg2"]}"/>'
        f'<g clip-path="url(#bar)"><g class="grow">{"".join(segs)}</g></g>'
        + "".join(legend)
    )
    return svg(W, H, body, css, "Languages: " + ", ".join(f"{n} {f * 100:.0f}%" for n, f, _ in rows))


def monotone_path(pts):
    if len(pts) < 2:
        return f"M{pts[0][0]},{pts[0][1]}" if pts else ""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    n = len(pts)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [(d[i - 1] + d[i]) / 2 if d[i - 1] * d[i] > 0 else 0 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9:
                k = 3 / math.sqrt(s)
                m[i], m[i + 1] = k * a * d[i], k * b * d[i]
    out = f"M{xs[0]:.1f},{ys[0]:.1f}"
    for i in range(n - 1):
        h = xs[i + 1] - xs[i]
        out += (
            f" C{xs[i] + h / 3:.1f},{ys[i] + m[i] * h / 3:.1f} "
            f"{xs[i + 1] - h / 3:.1f},{ys[i + 1] - m[i + 1] * h / 3:.1f} {xs[i + 1]:.1f},{ys[i + 1]:.1f}"
        )
    return out


def activity_card(st, t):
    W, H = 1000, 300
    weeks, starts = st["weeks"], st["week_starts"]
    x0, x1, y0, y1 = 64, 968, 108, 250
    peak = max(weeks) if weeks else 0
    top = max(4, math.ceil(peak * 1.15 / 4) * 4)
    n = len(weeks)
    pts = [(x0 + (x1 - x0) * i / max(n - 1, 1), y1 - (y1 - y0) * v / top) for i, v in enumerate(weeks)]
    line = monotone_path(pts)
    area = f"{line} L{pts[-1][0]:.1f},{y1} L{pts[0][0]:.1f},{y1} Z" if pts else ""
    grid = []
    for k in range(3):
        v = top * k / 2
        y = y1 - (y1 - y0) * k / 2
        grid.append(
            f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{t["grid"]}" '
            + ('' if k == 0 else 'stroke-dasharray="3 5"')
            + f'/><text class="m" x="{x0 - 12}" y="{y + 4:.1f}" font-size="11" fill="{t["dim"]}" text-anchor="end">{int(v)}</text>'
        )
    months, last = [], None
    for i, s in enumerate(starts):
        mo = dt.date.fromisoformat(s).strftime("%b")
        if mo != last and i > 0:
            months.append(f'<text class="m" x="{pts[i][0]:.1f}" y="{y1 + 24}" font-size="11" fill="{t["dim"]}" text-anchor="middle">{mo}</text>')
        last = mo
    peak_mark = ""
    if peak:
        pi = weeks.index(peak)
        px, py = pts[pi]
        anchor = "end" if px > x1 - 80 else "middle"
        peak_mark = (
            f'<g class="pop" style="animation-delay:2s"><circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{t["bg"]}" '
            f'stroke="{t["amber"]}" stroke-width="2.4"/>'
            f'<text class="m" x="{px:.1f}" y="{py - 13:.1f}" font-size="11.5" fill="{t["amber"]}" text-anchor="{anchor}">'
            f"peak · {peak}/wk</text></g>"
        )
    css = (
        "@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
        ".ln{stroke-dasharray:1;animation:draw 2.4s cubic-bezier(.4,0,.2,1) both}"
        "@keyframes fade{from{opacity:0}to{opacity:1}}.ar{animation:fade 1.4s 1s ease-out both}"
        "@keyframes pop{from{opacity:0;transform:scale(.2)}to{opacity:1;transform:none}}"
        ".pop{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.3,1.6,.5,1) both}"
    )
    body = (
        card_frame(W, H, t, uid="ac")
        + f'<defs><linearGradient id="af" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["amber"]}" stop-opacity=".32"/>'
        f'<stop offset="1" stop-color="{t["amber"]}" stop-opacity="0"/></linearGradient></defs>'
        f'<text class="s" x="32" y="46" font-size="18" font-weight="700" fill="{t["text"]}">Contribution activity</text>'
        f'<text class="s" x="32" y="70" font-size="13" fill="{t["muted"]}">weekly contributions · last 12 months</text>'
        f'<text class="s" x="{W - 32}" y="50" font-size="30" font-weight="700" fill="{t["amber"]}" text-anchor="end">{fmt(st["past_year"])}</text>'
        f'<text class="s" x="{W - 32}" y="70" font-size="12.5" fill="{t["muted"]}" text-anchor="end">contributions in the past year</text>'
        + "".join(grid)
        + f'<path class="ar" d="{area}" fill="url(#af)"/>'
        f'<path class="ln" d="{line}" stroke="{t["amber"]}" stroke-width="2.5" stroke-linejoin="round" pathLength="1"/>'
        + peak_mark
        + "".join(months)
    )
    return svg(W, H, body, css, f'{st["past_year"]} contributions in the past year, peak {peak} in one week')


def placeholder(W, H, title, t):
    body = card_frame(W, H, t, uid="ph") + (
        f'<text class="s" x="24" y="40" font-size="16" font-weight="700" fill="{t["text"]}">{esc(title)}</text>'
        f'<text class="m" x="{W / 2}" y="{H / 2 + 14}" font-size="12.5" fill="{t["dim"]}" text-anchor="middle">'
        "generating · appears after the first workflow run</text>"
    )
    return svg(W, H, body, "", f"{title} (pending first run)")


# ── README blocks ───────────────────────────────────────────────────────────
def picture(name, alt, width="100%"):
    return (
        f'<picture><source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">'
        f'<source media="(prefers-color-scheme: light)" srcset="assets/{name}-light.svg">'
        f'<img alt="{esc(alt)}" src="assets/{name}-dark.svg" width="{width}"></picture>'
    )


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def shield(link):
    def part(s):
        return urllib.parse.quote(s.replace("-", "--").replace("_", "__").replace(" ", "_"))

    url = (
        f'https://img.shields.io/badge/{part(link["label"])}-{part(link["message"])}-{link.get("color", "f5a524")}'
        "?style=flat-square&labelColor=161b22"
    )
    return f'<a href="{esc(link["url"])}"><img alt="{esc(link["label"])}" src="{url}"></a>'


def readme_blocks(cfg):
    projects = cfg.get("projects", [])
    cards = [
        f'<a href="https://github.com/{p["repo"]}">{picture("card-" + slug(p["name"]), p["name"] + " — " + p["description"], "49%")}</a>'
        for p in projects
    ]
    rows = ["\n".join(cards[i:i + 2]) for i in range(0, len(cards), 2)]
    live = [f'<a href="{esc(p["live"])}">{esc(p["name"])}</a>' for p in projects if p.get("live")]
    proj = "\n".join(f'<p align="center">\n{r}\n</p>' for r in rows)
    if live:
        proj += f'\n<p align="center"><sub>live demos → {" · ".join(live)}</sub></p>'

    st = cfg["stack"]
    icons = ",".join(st["icons"])
    per = st.get("perline", 10)
    stack = (
        '<p align="center"><a href="https://skillicons.dev"><picture>'
        f'<source media="(prefers-color-scheme: dark)" srcset="https://skillicons.dev/icons?i={icons}&perline={per}&theme=dark">'
        f'<source media="(prefers-color-scheme: light)" srcset="https://skillicons.dev/icons?i={icons}&perline={per}&theme=light">'
        f'<img alt="Tech stack" src="https://skillicons.dev/icons?i={icons}&perline={per}&theme=dark">'
        "</picture></a></p>"
    )
    links = '<p align="center">\n' + "\n".join(shield(l) for l in cfg.get("links", [])) + "\n</p>"
    return {"LINKS": links, "PROJECTS": proj, "STACK": stack}


def update_readme(cfg):
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    for key, block in readme_blocks(cfg).items():
        text = re.sub(
            rf"(<!--{key}:START-->).*?(<!--{key}:END-->)",
            lambda m: f"{m.group(1)}\n{block}\n{m.group(2)}",
            text,
            flags=re.S,
        )
    README.write_text(text, encoding="utf-8")


# ── main ────────────────────────────────────────────────────────────────────
def write(name, theme, content):
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / f"{name}-{theme}.svg").write_text(content, encoding="utf-8")


def main():
    cfg = tomllib.loads((ROOT / "profile.toml").read_text(encoding="utf-8"))
    mode = "sample" if "--sample" in sys.argv else "placeholder" if "--placeholder" in sys.argv else "live"

    for theme, t in THEMES.items():
        write("header", theme, header(cfg, t))
        write("typing", theme, typing(cfg, t))
        write("timeline", theme, timeline(cfg, t))
        write("footer", theme, footer(cfg, t))
        for p in cfg.get("projects", []):
            write("card-" + slug(p["name"]), theme, project_card(p, t))
    update_readme(cfg)

    stats = None
    if mode == "sample":
        stats = sample_stats()
    elif mode == "live":
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("::warning::No GH_TOKEN set; stats images left unchanged.")
        else:
            try:
                stats = fetch_stats(cfg, token)
            except Exception as exc:  # keep the last good images rather than failing the run
                print(f"::warning::Could not fetch GitHub stats ({exc}); stats images left unchanged.")

    updated = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%d %b %Y")
    for theme, t in THEMES.items():
        if stats:
            write("stats", theme, stats_card(stats, t, updated))
            write("languages", theme, languages_card(stats, t))
            write("activity", theme, activity_card(stats, t))
        elif mode == "placeholder":
            write("stats", theme, placeholder(480, 240, "GitHub at a glance", t))
            write("languages", theme, placeholder(480, 240, "Languages", t))
            write("activity", theme, placeholder(1000, 300, "Contribution activity", t))
            write("snake", theme, placeholder(1000, 200, "Contribution snake", t))
    print(f"built assets ({mode})")


if __name__ == "__main__":
    main()
