#!/usr/bin/env python3
"""Build the Downlink Desk Operator's Manual from its XML data modules.

Reads source/publication.xml and every data module it lists, checks them, and writes:
  site/index.html        title page, contents and list of effective data modules
  site/dm/<code>.html    one page per data module
  site/manual.html       the whole manual as one page, for printing to PDF

Standard library only. Exits non-zero if any check fails, so a broken manual is never published.
Usage: python3 tools/build.py [--check]   (--check validates without writing anything)
"""
import html
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source"
OUT = ROOT / "site"
PDF_NAME = "downlink-desk-operators-manual.pdf"

TYPES = {"descript": "Descriptive", "proced": "Procedural", "fault": "Fault isolation"}
QA = {"unverified": "Unverified", "tabletop": "First verification: table-top", "onObject": "First verification: on object"}
# Business rule: a warning means a risk of injury or death (S1000D). Nothing in this product can
# cause either, so the project allows cautions and notes only. A warning in the source fails the build.
FORBIDDEN = {"warning": "warnings are for risk of injury or death; use <caution> or <note>"}


def title_of(root):
    """S1000D data module title: technical name - information name."""
    return root.findtext("dmTitle/techName", "") + " – " + root.findtext("dmTitle/infoName", "")
# Every element the profile allows. Anything else is a build error, so typos can't slip through.
ALLOWED = {
    "dmodule", "dmTitle", "techName", "infoName", "status", "title", "applic", "content", "levelledPara", "para", "randomList", "listItem",
    "emphasis", "ui", "cmd", "note", "notePara", "caution", "warningAndCautionPara",
    "table", "row", "entry", "figure", "graphic", "dmRef", "preliminaryRqmts", "reqCondGroup",
    "reqCond", "reqPersons", "person", "estimatedTime", "reqSupportEquips", "supportEquipDescr",
    "noSupportEquips", "reqSupplies", "noSupplies", "reqSpares", "noSpares", "reqSafety", "noSafety",
    "mainProcedure", "proceduralStep", "closeRqmts", "faultIsolation", "faultDescr",
    "isolationMainProcedure", "isolationStep", "action", "isolationStepQuestion",
    "isolationStepAnswer", "yesNoAnswer", "yesAnswer", "noAnswer", "isolationProcedureEnd",
}

errors = []


def err(where, msg):
    errors.append(f"{where}: {msg}")


# ---------------------------------------------------------------- loading and checks

def load():
    pm = ET.parse(SRC / "publication.xml").getroot()
    groups, order = [], []
    for e in pm.findall("entry"):
        codes = [r.get("target") for r in e.findall("dmRef")]
        groups.append((e.get("title"), codes))
        order += codes
    dms = {}
    for f in sorted(SRC.glob("DMC-*.xml")):
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError as x:
            err(f.name, f"not well-formed XML ({x})")
            continue
        code = root.get("code")
        if code != f.stem:
            err(f.name, f"code attribute '{code}' does not match the file name")
        for a in ("code", "type", "issue", "date"):
            if not root.get(a):
                err(f.name, f"missing attribute '{a}'")
        if root.get("type") not in TYPES:
            err(f.name, f"type must be one of {', '.join(TYPES)}")
        if not (root.findtext("dmTitle/techName") or "").strip() or not (root.findtext("dmTitle/infoName") or "").strip():
            err(f.name, "dmTitle needs a techName and an infoName")
        st = root.find("status")
        if st is None:
            err(f.name, "missing <status>")
        else:
            for a in ("security", "rpc", "originator", "qa"):
                if not st.get(a):
                    err(f.name, f"<status> missing '{a}'")
            if st.get("qa") not in QA:
                err(f.name, f"qa must be one of {', '.join(QA)}")
        info = code.split("-")[-2][:3] if code else ""
        kind = root.get("type")
        if kind == "fault" and not info.startswith("4"):
            err(f.name, "fault isolation modules need a 4xx information code")
        if kind == "proced" and info[:1] not in "123456789":
            err(f.name, "procedural modules need a procedural information code (100 to 999)")
        if kind in ("proced", "fault"):
            pr = root.find(".//preliminaryRqmts")
            if pr is None:
                err(f.name, "missing <preliminaryRqmts>")
            else:
                for r in ("reqCondGroup", "reqPersons", "reqSupportEquips", "reqSupplies", "reqSpares", "reqSafety"):
                    if pr.find(r) is None:
                        err(f.name, f"<preliminaryRqmts> missing <{r}> (state none explicitly)")
            if root.find(".//closeRqmts/reqCondGroup") is None:
                err(f.name, "missing <closeRqmts><reqCondGroup>")
        for el in root.iter():
            if el.tag in FORBIDDEN:
                err(f.name, f"<{el.tag}> not allowed: {FORBIDDEN[el.tag]}")
            elif el.tag not in ALLOWED:
                err(f.name, f"element <{el.tag}> is not in the profile")
        dms[code] = root
    for c in order:
        if c not in dms:
            err("publication.xml", f"lists {c}, which has no data module file")
    for c in dms:
        if c not in order:
            err(c, "is not listed in publication.xml")
    if len(set(order)) != len(order):
        err("publication.xml", "lists a data module more than once")
    for c, root in dms.items():
        for r in root.iter("dmRef"):
            if r.get("target") not in dms:
                err(c, f"refers to missing data module {r.get('target')}")
            if r.get("target") == c:
                err(c, "refers to itself")
        for g in root.iter("graphic"):
            if not (SRC / g.get("src", "")).is_file():
                err(c, f"graphic {g.get('src')} not found")
            if not g.get("alt"):
                err(c, f"graphic {g.get('src')} has no alt text")
        ids = [e.get("id") for e in root.iter() if e.get("id")]
        if len(ids) != len(set(ids)):
            err(c, "has duplicate ids")
        if root.get("type") == "fault":
            targets = {e.get("id") for e in root.iter() if e.tag in ("isolationStep", "isolationProcedureEnd")}
            reached = set()
            for s in root.iter("isolationStep"):
                for ans in ("yesAnswer", "noAnswer"):
                    a = s.find(f"isolationStepAnswer/yesNoAnswer/{ans}")
                    if a is None:
                        err(c, f"step {s.get('id')} has no <{ans}>")
                    elif a.get("nextActionRefId") not in targets:
                        err(c, f"step {s.get('id')} {ans} goes to unknown '{a.get('nextActionRefId')}'")
                    else:
                        reached.add(a.get("nextActionRefId"))
            first = root.find(".//isolationStep")
            for t in targets - reached - {first.get("id") if first is not None else None}:
                err(c, f"'{t}' can never be reached")
    return pm, groups, order, dms


# ---------------------------------------------------------------- rendering

def esc(s):
    return html.escape(s or "", quote=True)


class Renderer:
    def __init__(self, dms, single):
        self.dms, self.single = dms, single
        self.fig = 0

    def href(self, code):
        return f"#{code}" if self.single else f"{code}.html"

    def inline(self, el):
        """Text and inline children of an element."""
        out = [esc(el.text)]
        for ch in el:
            t = ch.tag
            if t == "emphasis":
                out.append(f"<strong>{self.inline(ch)}</strong>")
            elif t == "ui":
                out.append(f'<span class="ui">{self.inline(ch)}</span>')
            elif t == "cmd":
                out.append(f"<code>{self.inline(ch)}</code>")
            elif t == "dmRef":
                code = ch.get("target")
                title = title_of(self.dms[code]) if code in self.dms else code
                out.append(f'<a class="dmref" href="{self.href(code)}">{esc(title)}</a> '
                           f'<span class="dmc">({esc(code)})</span>')
            else:
                out.append(self.block(ch))
            out.append(esc(ch.tail))
        return "".join(out)

    def notice(self, el, kind, label):
        paras = "".join(f"<p>{self.inline(p)}</p>" for p in el)
        return f'<div class="{kind}" role="note"><div class="nl">{label}</div>{paras}</div>'

    def table(self, el):
        rows = el.findall("row")
        head = [r for r in rows if r.get("head") == "yes"]
        body = [r for r in rows if r.get("head") != "yes"]
        h = "".join("<tr>" + "".join(f"<th>{self.inline(c)}</th>" for c in r) + "</tr>" for r in head)
        b = "".join("<tr>" + "".join(f"<td>{self.inline(c)}</td>" for c in r) + "</tr>" for r in body)
        return f'<div class="tw"><table>{"<thead>" + h + "</thead>" if h else ""}<tbody>{b}</tbody></table></div>'

    def block(self, el, depth=2):
        t = el.tag
        if t == "para":
            return f"<p>{self.inline(el)}</p>"
        if t == "randomList":
            return "<ul>" + "".join(f"<li>{''.join(self.block(p) for p in li)}</li>" for li in el) + "</ul>"
        if t == "note":
            return self.notice(el, "note", "Note")
        if t == "caution":
            return self.notice(el, "caution", "Caution")
        if t == "table":
            return self.table(el)
        if t == "figure":
            self.fig += 1
            g = el.find("graphic")
            return (f'<figure><img src="{"" if self.single else "../"}{esc(g.get("src"))}" alt="{esc(g.get("alt"))}">'
                    f'<figcaption>Figure {self.fig} {esc(el.findtext("title"))}</figcaption></figure>')
        if t == "levelledPara":
            h = min(depth + 1, 4)
            inner = "".join(self.block(c, depth + 1) for c in el if c.tag != "title")
            return f'<section><h{h}>{esc(el.findtext("title"))}</h{h}>{inner}</section>'
        return ""

    # procedures
    def steps(self, parent, prefix=""):
        items = []
        for i, s in enumerate(parent.findall("proceduralStep"), 1):
            n = f"{prefix}{i}"
            body = "".join(self.block(c) for c in s if c.tag != "proceduralStep")
            sub = self.steps(s, n + ".") if s.find("proceduralStep") is not None else ""
            items.append(f'<li><span class="sn">{n}</span><div class="sb">{body}{sub}</div></li>')
        return f'<ol class="steps">{"".join(items)}</ol>'

    def prelim(self, pr):
        """Preliminary requirements in the S1000D order, stating "None" where nothing is needed."""
        def items(el, child):
            got = el.findall(child) if el is not None else []
            return "<ul>" + "".join(f"<li>{self.inline(c)}</li>" for c in got) + "</ul>" if got else "<p>None</p>"
        out = ["<section><h3>Preliminary requirements</h3>"]
        out.append("<h4>Required conditions</h4>" + items(pr.find("reqCondGroup"), "reqCond"))
        rp = pr.find("reqPersons")
        people = ", ".join(f'{p.get("count", "1")} × {esc(p.text)}' for p in rp.findall("person"))
        out.append(f"<h4>Required persons</h4><p>{people}. Estimated time: {esc(rp.findtext('estimatedTime'))}</p>")
        out.append("<h4>Support equipment</h4>" + items(pr.find("reqSupportEquips"), "supportEquipDescr"))
        out.append("<h4>Supplies</h4><p>None</p><h4>Spares</h4><p>None</p>")
        sf = pr.find("reqSafety")
        safety = "".join(self.block(c) for c in sf if c.tag != "noSafety")
        out.append("<h4>Safety conditions</h4>" + (safety or "<p>None</p>"))
        out.append("</section>")
        return "".join(out)

    def close(self, cr):
        conds = cr.findall("reqCondGroup/reqCond")
        return ("<section><h3>Requirements after job completion</h3><ul>" +
                "".join(f"<li>{self.inline(c)}</li>" for c in conds) + "</ul></section>")

    def procedure(self, content):
        return (self.prelim(content.find("preliminaryRqmts")) +
                f'<section><h3>Procedure</h3>{self.steps(content.find("mainProcedure"))}</section>' +
                self.close(content.find("closeRqmts")))

    # fault isolation
    def fault(self, content):
        fi = content.find("faultIsolation")
        main = fi.find("isolationMainProcedure")
        steps = main.findall("isolationStep")
        ends = main.findall("isolationProcedureEnd")
        label = {s.get("id"): f"Step {i}" for i, s in enumerate(steps, 1)}
        label.update({e.get("id"): f"Result {chr(64 + i)}" for i, e in enumerate(ends, 1)})

        def go(s, ans):
            t = s.find(f"isolationStepAnswer/yesNoAnswer/{ans}").get("nextActionRefId")
            return f'<a href="#{self.cur}-{t}">go to {label[t]}</a>'

        out = [f'<section><h3>Fault description</h3>{"".join(self.block(c) for c in fi.find("faultDescr"))}</section>',
               self.prelim(fi.find("preliminaryRqmts")), "<section><h3>Isolation procedure</h3>"]
        for s in steps:
            out.append(
                f'<div class="istep" id="{self.cur}-{s.get("id")}"><div class="il">{label[s.get("id")]}</div>'
                f'<p>{self.inline(s.find("action"))}</p>'
                f'<p class="q">{self.inline(s.find("isolationStepQuestion"))}</p>'
                f'<p class="ans"><span class="yes">Yes</span> {go(s, "yesAnswer")}'
                f'<span class="no">No</span> {go(s, "noAnswer")}</p></div>')
        out.append("</section><section><h3>Results</h3>")
        for e in ends:
            out.append(f'<div class="iend" id="{self.cur}-{e.get("id")}"><div class="il">{label[e.get("id")]}</div>'
                       f'<p>{self.inline(e.find("action"))}</p></div>')
        out.append("</section>")
        out.append(self.close(fi.find("closeRqmts")))
        return "".join(out)

    def dm(self, code):
        self.cur = code
        root = self.dms[code]
        content = root.find("content")
        t = root.get("type")
        if t == "proced":
            body = self.procedure(content)
        elif t == "fault":
            body = self.fault(content)
        else:
            body = "".join(self.block(c) for c in content)
        st = root.find("status")
        meta = (f'<div class="dmmeta"><span class="dmc">{esc(code)}</span>'
                f'<span>{TYPES[t]}</span><span>Issue {esc(root.get("issue"))}</span>'
                f'<span>{esc(root.get("date"))}</span><span>{esc(st.get("security"))}</span>'
                f'<span class="qa">QA: {esc(QA[st.get("qa")])}</span>'
                f'<span>Applies to {esc(root.findtext("applic"))}</span></div>')
        return f'<article class="dm" id="{esc(code)}">{meta}<h2>{esc(title_of(root))}</h2>{body}</article>'


# ---------------------------------------------------------------- pages

def page(title, body, css):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{css}">
</head>
<body>
{body}
</body>
</html>
"""


def lodm(order, dms, single):
    href = (lambda c: f"#{c}") if single else (lambda c: f"dm/{c}.html")
    rows = "".join(
        f'<tr><td><a href="{href(c)}">{esc(title_of(dms[c]))}</a></td><td class="dmc">{esc(c)}</td>'
        f'<td>{TYPES[dms[c].get("type")]}</td><td>{esc(dms[c].get("issue"))}</td><td>{esc(dms[c].get("date"))}</td></tr>'
        for c in order)
    return ('<section class="lodm"><h2>List of effective data modules</h2><div class="tw"><table><thead><tr>'
            '<th>Title</th><th>Data module code</th><th>Type</th><th>Issue</th><th>Date</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div></section>")


def contents(groups, dms, single):
    href = (lambda c: f"#{c}") if single else (lambda c: f"dm/{c}.html")
    out = ['<nav class="toc" aria-label="Contents"><h2>Contents</h2>']
    for title, codes in groups:
        out.append(f"<h3>{esc(title)}</h3><ol>")
        out += [f'<li><a href="{href(c)}">{esc(title_of(dms[c]))}</a></li>' for c in codes]
        out.append("</ol>")
    out.append("</nav>")
    return "".join(out)


def title_block(pm, link_pdf):
    pdf = f'<p><a class="btn" href="{PDF_NAME}">Download the manual as PDF</a></p>' if link_pdf else ""
    return (f'<header class="tp"><p class="pmc">{esc(pm.get("code"))} · Issue {esc(pm.get("issue"))} · {esc(pm.get("date"))}</p>'
            f'<h1>{esc(pm.findtext("title"))}</h1><p class="lede">{esc(pm.findtext("subtitle"))}</p>'
            f'<p>Applies to {esc(pm.findtext("applic"))}. Prepared by {esc(pm.findtext("author"))}.</p>'
            f'<p class="status"><strong>Status:</strong> {esc(pm.findtext("status"))}</p>'
            f'<div class="caution" role="note"><div class="nl">Caution</div><p>Downlink Desk is not flight software. '
            f'It cannot command a spacecraft and its limits are provisional. Do not use it to make decisions about real spacecraft hardware.</p></div>'
            f"{pdf}</header>")


def build(write=True):
    pm, groups, order, dms = load()
    if errors:
        return
    if not write:
        return order
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "dm").mkdir(parents=True)
    shutil.copytree(SRC / "graphics", OUT / "graphics")
    shutil.copy(ROOT / "tools" / "manual.css", OUT / "manual.css")

    # index
    body = (f'<main class="wrap">{title_block(pm, True)}{contents(groups, dms, False)}'
            f'{lodm(order, dms, False)}<footer><p>Source XML and build pipeline: '
            f'<a href="https://github.com/archer7778/downlink-desk-manual">github.com/archer7778/downlink-desk-manual</a>. '
            f'The software: <a href="https://github.com/archer7778/downlink-desk">Downlink Desk</a>.</p></footer></main>')
    (OUT / "index.html").write_text(page(pm.findtext("title"), body, "manual.css"))

    # one page per data module
    r = Renderer(dms, single=False)
    for i, c in enumerate(order):
        r.fig = 0
        prev = f'<a href="{order[i-1]}.html">← {esc(title_of(dms[order[i-1]]))}</a>' if i else "<span></span>"
        nxt = f'<a href="{order[i+1]}.html">{esc(title_of(dms[order[i+1]]))} →</a>' if i + 1 < len(order) else "<span></span>"
        body = (f'<main class="wrap"><p class="crumb"><a href="../index.html">{esc(pm.findtext("title"))}</a></p>'
                f'{r.dm(c)}<nav class="pn">{prev}{nxt}</nav></main>')
        (OUT / "dm" / f"{c}.html").write_text(page(f'{title_of(dms[c])} · {pm.findtext("title")}', body, "../manual.css"))

    # single document for print
    r = Renderer(dms, single=True)
    parts = [title_block(pm, False), contents(groups, dms, True), lodm(order, dms, True)]
    for title, codes in groups:
        parts.append(f'<h1 class="part">{esc(title)}</h1>')
        parts += [r.dm(c) for c in codes]
    (OUT / "manual.html").write_text(page(pm.findtext("title"), f'<main class="wrap print">{"".join(parts)}</main>', "manual.css"))
    return order


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    result = build(write=not check_only)
    if errors:
        print("Manual has errors:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print(f"OK: {len(result)} data modules checked" + ("" if check_only else f", site written to {OUT.relative_to(ROOT)}/"))
