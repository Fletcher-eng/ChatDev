"""Build the Graphify knowledge graph for the Specpoint vault.

Run build-vault.mjs first (it writes graphify-out/.graphify_extract.json), then:
    pip install graphifyy
    python specpoint/obsidian/build-graph.py ["path/to/Specpoint Vault"]

Writes into <vault>/graphify-out/: graph.json, GRAPH_REPORT.md, graph.html (works
offline), plus "Knowledge graph.canvas" in the vault so it opens inside Obsidian.
"""
import json
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.detect import detect
from graphify.export import to_canvas, to_html, to_json
from graphify.report import generate

HERE = Path(__file__).resolve().parent
VAULT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "Specpoint Vault"
OUT = VAULT / "graphify-out"
VIS = "https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"

extraction = json.loads((OUT / ".graphify_extract.json").read_text(encoding="utf-8"))
detection = detect(VAULT, extra_excludes=["graphify-out", ".obsidian", "Templates"])
(OUT / ".graphify_detect.json").write_text(json.dumps(detection, ensure_ascii=False), encoding="utf-8")

G = build_from_json(extraction, root=str(VAULT), directed=False)
if G.number_of_nodes() == 0:
    raise SystemExit("Graph is empty: run build-vault.mjs first.")
communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)


def label_for(members):
    """Name a community after its two best connected key ideas."""
    ranked = sorted(members, key=lambda n: G.degree(n), reverse=True)
    concepts = [n for n in ranked if G.nodes[n].get("file_type") == "concept"] or ranked
    names = [G.nodes[n].get("label", n) for n in concepts[:2]]
    # Prefer the topic a community is mostly about, if one dominates.
    topics = Counter(m.group(1) for n in members
                     for m in [re.match(r"Biology (\d+) ", G.nodes[n].get("label", ""))] if m)
    if topics:
        t, count = topics.most_common(1)[0]
        if count >= 2:
            return f"Topic {t}: " + " and ".join(names)
    return " and ".join(names)


# Names chosen by reading each cluster (graphify's labelling step). A cluster is
# named by the first rule whose key note it contains; anything new falls back to
# label_for so the names stay sensible after rebuilds.
RULES = [
    ("Mistake book", "Your subjects and study pages"),
    ("Osmosis", "Osmosis and water in cells"),
    ("Diffusion", "Diffusion, respiration and active transport"),
    ("Bacterial cell", "Bacteria, DNA and biotechnology"),
    ("Red blood cell", "Cells for transport and defence"),
    ("Photosynthesis", "Cell types and nutrition"),
    ("Specialised cell", "Specialised cells and organisation"),
    ("Magnification", "Size of specimens and magnification"),
    ("Ribosomes", "Biology map, molecules and later topics"),
]


def name_cluster(members):
    names = {G.nodes[n].get("label") for n in members}
    for key, name in RULES:
        if key in names:
            return name
    return label_for(members)


labels = {cid: name_cluster(m) for cid, m in communities.items()}
questions = suggest_questions(G, communities, labels)
tokens = {"input": 0, "output": 0}
to_json(G, communities, str(OUT / "graph.json"), force=True, community_labels=labels)
report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, str(VAULT),
                  suggested_questions=questions)
(OUT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
(OUT / ".graphify_analysis.json").write_text(json.dumps({
    "communities": {str(k): v for k, v in communities.items()},
    "cohesion": {str(k): v for k, v in cohesion.items()},
    "gods": gods, "surprises": surprises, "questions": questions,
}, indent=2, ensure_ascii=False), encoding="utf-8")
(OUT / ".graphify_labels.json").write_text(json.dumps({str(k): v for k, v in labels.items()}, ensure_ascii=False),
                                           encoding="utf-8")

# Interactive page, made to work offline by keeping the drawing library next to it.
html_path = OUT / "graph.html"
to_html(G, communities, str(html_path), community_labels=labels)
lib = OUT / "vis-network.min.js"
if not lib.exists():
    try:
        urllib.request.urlretrieve(VIS, lib)
    except OSError as err:
        print(f"Could not download vis-network ({err}). graph.html will need internet until you save {VIS} as {lib}.")
if lib.exists():
    page = html_path.read_text(encoding="utf-8").replace(VIS, "vis-network.min.js")
    # Browsers refuse crossorigin and integrity checks on local files, so drop them for the local copy.
    page = re.sub(r'(<script src="vis-network\.min\.js")\s+integrity="[^"]*"\s+crossorigin="[^"]*"', r"\1", page)
    html_path.write_text(page, encoding="utf-8")

# Obsidian Canvas: each card opens the matching note.
def rel(sf):
    p = Path(sf)
    return str(p.resolve().relative_to(VAULT)) if p.is_absolute() else str(p)


files = {n["id"]: rel(n["source_file"]).removesuffix(".md") for n in extraction["nodes"]}
to_canvas(G, communities, str(VAULT / "Knowledge graph.canvas"), community_labels=labels, node_filenames=files)

print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities")
for cid, name in sorted(labels.items()):
    print(f"  {cid}: {name} ({len(communities[cid])})")
