#!/usr/bin/env python3
"""auto-triage — the bot that pairs and diagnoses Cosmonarchy bug reports.

Runs whenever new crash reports land in this repo (see
.github/workflows/auto-triage.yml). It:

1. scans crash-reports/*/ for reports without a diagnosis,
2. pairs the two sides of the same game (same build sha, report timestamps
   within a few hours),
3. runs the mechanical comparison (build/plugin/config identity, the game's
   own desync records, crash signatures),
4. writes diagnosis.md into both reports and updates the INDEX.md:
   FLASH lane (a mechanical difference is the cause — a cheap model can
   explain it) or DEEP lane (both sides identical — the divergence is in the
   engine/plugins; escalate to a stronger model with the generated prompt).

Read-only apart from writing diagnosis.md / INDEX.md; safe to re-run.
"""
import glob
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "crash-reports")
INDEX = os.path.join(REPORTS, "INDEX.md")


def files(report_dir):
    return {os.path.basename(p): p for p in glob.glob(os.path.join(report_dir, "*"))}


def read(report_dir, name):
    for key, path in files(report_dir).items():
        if key.endswith(name):
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
    return ""


def marker(text, needle):
    for line in text.splitlines():
        if needle in line:
            return line.strip()
    return ""


def build_sha(report_dir):
    text = read(report_dir, "build-id.txt")
    for line in text.splitlines():
        line = line.strip()
        if re.fullmatch(r"[0-9a-f]{40}", line):
            return line
        if line.startswith("sha:"):
            return line[4:].strip()
    return ""


def plugin_rev(report_dir):
    return marker(read(report_dir, "cosmo_plus.log"), "feature build:")


def plus_yml(report_dir):
    return read(report_dir, "plus.yml") or read(report_dir, "conf_plus.yml")


def crash_addresses(report_dir):
    found = set()
    text = read(report_dir, "cosmo_crash.log")
    for m in re.finditer(r"addr=0x([0-9a-fA-F]+)", text):
        found.add("0x" + m.group(1).lower())
    return sorted(found)


def desync_frames(report_dir):
    frames = []
    for key in files(report_dir):
        if "Critical" in key:
            for line in open(files(report_dir)[key], encoding="utf-8", errors="replace"):
                if "Critical frame:" in line:
                    frames.append(line.strip())
    return frames


def line_diff(a, b, cap=24):
    al, bl = a.splitlines(), b.splitlines()
    out, shown = [], 0
    for i in range(max(len(al), len(bl))):
        if shown >= cap:
            break
        x = al[i].strip() if i < len(al) else "(missing)"
        y = bl[i].strip() if i < len(bl) else "(missing)"
        if x == y:
            continue
        out.append(f"  side A: {x}")
        out.append(f"  side B: {y}")
        shown += 2
    return "\n".join(out)


def diagnose(a_dir, b_dir):
    findings = []
    sha_a, sha_b = build_sha(a_dir), build_sha(b_dir)
    if sha_a and sha_b and sha_a != sha_b:
        findings.append(("critical", "Different game builds",
                         f"A: {sha_a}\nB: {sha_b}\nBoth players must run the same commit."))
    rev_a, rev_b = plugin_rev(a_dir), plugin_rev(b_dir)
    if rev_a and rev_b and rev_a != rev_b:
        findings.append(("critical", "Different Plus plugin builds",
                         f"A: {rev_a}\nB: {rev_b}\nUpdate the older side in the launcher."))
    yml_a, yml_b = plus_yml(a_dir), plus_yml(b_dir)
    if yml_a and yml_b and yml_a != yml_b:
        findings.append(("critical", "plus.yml differs between the clients",
                         line_diff(yml_a, yml_b)))
    shared = set(crash_addresses(a_dir)) & set(crash_addresses(b_dir))
    if shared:
        findings.append(("info", "Both sides hit the same crash",
                         f"shared signature: {', '.join(sorted(shared))}"))
    frames = desync_frames(a_dir) + desync_frames(b_dir)
    if frames:
        findings.append(("info", "The game's own desync detector fired",
                         "; ".join(frames[:4])))

    mechanical = [f for f in findings if f[0] == "critical"]
    lines = ["# Diagnosis", ""]
    if mechanical:
        lines += [
            "## Route: FLASH lane (cheap model)",
            "",
            "A mechanical difference between the two clients is the cause. ",
            "Fixing it needs no deep reasoning:",
            "",
        ]
        for sev, title, detail in findings:
            lines += [f"- **[{sev}] {title}**: {detail}", ""]
        lines += [
            "## The fix",
            "",
            "Make both machines identical: the same game build (same commit), the same ",
            "Plus plugin build, the same plus.yml. The launcher's Update button handles ",
            "the first two; the Config tab handles the file. Then re-test one game.",
        ]
    else:
        lines += [
            "## Route: DEEP lane (escalate to a stronger model)",
            "",
            "The two reports are mechanically identical, yet the games desync (or crash). ",
            "The divergence is inside the engine or the plugins. Hand the prompt below ",
            "and the report files to the stronger model.",
            "",
        ]
        for sev, title, detail in findings:
            lines += [f"- **[{sev}] {title}**: {detail}", ""]
        lines += [
            "## Deep prompt",
            "",
            "```",
            "Two StarCraft: Brood War 1.16.1 total-conversion (Cosmonarchy) clients desync",
            "every lockstep game. Builds, plugin revisions and configs are IDENTICAL on both",
            "sides. Reason step by step: 1) classify the divergence (RNG stream, unit state,",
            "sync data) from the game's own desync records (Local/Remote hashes, last",
            "random number); 2) enumerate per-client writes that can leak into synced state",
            "(UI globals the simulation may read, the client selection table, draw-pass",
            "writes); 3) for each crash signature, name the owning module (exe 0x00400000,",
            "gptp.qdp ~0x02500000-0x02800000); 4) output the most likely root cause, the",
            "evidence, one concrete instrument to confirm it, and the minimal fix.",
            "```",
        ]
    lines += ["", f"- Generated: {datetime.utcnow().isoformat()}Z (auto-triage bot)"]
    return "\n".join(lines)


def slug_time(slug):
    try:
        return datetime.strptime(slug[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def main():
    if not os.path.isdir(REPORTS):
        print("no crash-reports dir yet")
        return 0
    slugs = sorted(os.listdir(REPORTS))
    pending = []
    for slug in slugs:
        d = os.path.join(REPORTS, slug)
        if os.path.isdir(d) and not os.path.exists(os.path.join(d, "diagnosis.md")):
            pending.append((slug, d))

    # Pair by build sha + timestamp proximity.
    by_sha = {}
    for slug, d in pending:
        by_sha.setdefault(build_sha(d) or "unknown", []).append((slug, d))

    changed = []
    for sha, group in by_sha.items():
        for i, (slug_a, a) in enumerate(group):
            t_a = slug_time(slug_a)
            for slug_b, b in group[i + 1:]:
                t_b = slug_time(slug_b)
                if t_a and t_b and abs((t_b - t_a).total_seconds()) > 6 * 3600:
                    continue
                text = diagnose(a, b)
                for d in (a, b):
                    with open(os.path.join(d, "diagnosis.md"), "w") as f:
                        f.write(text)
                changed.append((slug_a, slug_b, text))
                break

    # INDEX.md
    rows = ["# Crash reports", ""]
    for slug in reversed(slugs):
        d = os.path.join(REPORTS, slug)
        if not os.path.isdir(d):
            continue
        diag = os.path.exists(os.path.join(d, "diagnosis.md"))
        route = ""
        if diag:
            text = open(os.path.join(d, "diagnosis.md")).read()
            route = "FLASH" if "FLASH lane" in text else "DEEP"
        note = read(d, "summary.md")
        rows.append(f"- `{slug}` — build `{build_sha(d) or '?'}` — "
                    f"diagnosis: {'yes (' + route + ')' if diag else 'waiting for pair'}")
    rows.append("")
    with open(INDEX, "w") as f:
        f.write("\n".join(rows))

    print(f"paired {len(changed)} report pair(s); {len(pending)} pending total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
