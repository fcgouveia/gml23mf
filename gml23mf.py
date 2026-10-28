"""
gml2stl.py - converte um grafo GML em um arquivo 3MF para impressão 3D multicor.

Cada cluster vira UM objeto nomeado no 3MF (cluster_<valor>), reunindo as esferas dos seus nós
e as arestas internas. Arestas entre clusters diferentes ficam em "arestas_entre_clusters".
No fatiador (PrusaSlicer, OrcaSlicer, Bambu Studio) basta atribuir um filamento por objeto.
As cores embutidas servem só de pré-visualização.

Dependências: pip install networkx trimesh numpy
Uso: python gml2stl.py 2Dgraph.gml 3Dgraph.3mf --cluster-attr cluster
"""
import argparse
import colorsys
import re
import zipfile
from xml.sax.saxutils import quoteattr

import networkx as nx
import numpy as np
import trimesh

SEM_CLUSTER = "sem_cluster"


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s))[:60]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def cluster_of(data, attr):
    v = data.get(attr)
    return SEM_CLUSTER if v is None else str(v)


def cluster_colors(graph, attr):
    """Cor por cluster: atributo 'color' do primeiro nó do cluster (se existir), senão paleta."""
    clusters = {}
    for n, d in graph.nodes(data=True):
        clusters.setdefault(cluster_of(d, attr), []).append(n)
    keys = sorted(clusters, key=lambda k: (k == SEM_CLUSTER, str(k)))
    colors = {}
    for i, k in enumerate(keys):
        given = next((graph.nodes[n].get("color") for n in clusters[k]
                      if isinstance(graph.nodes[n].get("color"), str)
                      and re.fullmatch(r"#?[0-9a-fA-F]{6}", graph.nodes[n]["color"])), None)
        if given:
            colors[k] = hex_to_rgb(given)
        else:
            r, g, b = colorsys.hsv_to_rgb(i / max(len(keys), 1), 0.65, 0.95)
            colors[k] = (int(r * 255), int(g * 255), int(b * 255))
    return clusters, colors


def compute_positions(graph, args):
    """X e Y vêm do GML (x scale_xy). Z vem de --z-attr, normalizado (mín->0, máx->1) e
    multiplicado pela maior extensão entre X e Y (x --z-ratio), para o modelo ficar proporcional."""
    xy = {n: (float(d.get("x", 0)) * args.scale_xy, float(d.get("y", 0)) * args.scale_xy)
          for n, d in graph.nodes(data=True)}
    xs, ys = [p[0] for p in xy.values()], [p[1] for p in xy.values()]
    extent = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0

    raw = {}
    for n, d in graph.nodes(data=True):
        try:
            raw[n] = float(d[args.z_attr])
        except (KeyError, TypeError, ValueError):
            pass
    if not raw:
        keys = sorted({k for _, d in graph.nodes(data=True) for k in d})
        print(f"AVISO: atributo '{args.z_attr}' não encontrado; Z = 0. Atributos disponíveis: {keys}")
    lo, hi = (min(raw.values()), max(raw.values())) if raw else (0.0, 0.0)
    mean = (lo + hi) / 2
    z_extent = extent * args.z_ratio
    pos = {}
    for n in graph.nodes:
        v = raw.get(n, mean)
        z = (v - lo) / (hi - lo) * z_extent if hi > lo else 0.0
        pos[n] = np.array([xy[n][0], xy[n][1], z])
    print(f"Extensão X/Y: {extent:.1f} mm | Z: {args.z_attr} de {lo:g} a {hi:g} -> 0 a {z_extent:.1f} mm")
    return pos


def build_objects(graph, args):
    clusters, colors = cluster_colors(graph, args.cluster_attr)
    pos = compute_positions(graph, args)
    parts = {k: [] for k in clusters}
    parts["arestas_entre_clusters"] = []

    for n, d in graph.nodes(data=True):
        r = max(float(d.get("degree", graph.degree(n))) * args.node_scale, args.min_radius)
        s = trimesh.creation.icosphere(subdivisions=args.subdiv, radius=r)
        s.apply_translation(pos[n])
        parts[cluster_of(d, args.cluster_attr)].append(s)

    for u, v, d in graph.edges(data=True):
        if np.linalg.norm(pos[v] - pos[u]) < 1e-9:
            continue
        r = max(float(d.get("value", d.get("weight", 1))) ** 0.2 * args.edge_scale,
                args.min_radius * 0.3)
        c = trimesh.creation.cylinder(radius=r, segment=[pos[u], pos[v]], sections=16)
        cu = cluster_of(graph.nodes[u], args.cluster_attr)
        cv = cluster_of(graph.nodes[v], args.cluster_attr)
        parts[cu if cu == cv else "arestas_entre_clusters"].append(c)

    objs = []
    for k, meshes in parts.items():
        if not meshes:
            continue
        if k == "arestas_entre_clusters":
            objs.append((k, trimesh.util.concatenate(meshes), hex_to_rgb(args.edge_color), 0))
        else:
            objs.append((f"cluster_{safe_name(k)}", trimesh.util.concatenate(meshes),
                         colors[k], len(clusters[k])))
    return objs


def write_3mf(path, objs):
    mats = {}
    for _, _, c, _ in objs:
        mats.setdefault("#%02X%02X%02X" % c, len(mats))
    x = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<model unit="millimeter" xml:lang="en-US" '
         'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>',
         '<basematerials id="1">']
    x += [f'<base name="cor_{h[1:]}" displaycolor="{h}FF"/>' for h in mats]
    x.append('</basematerials>')
    build = []
    for i, (name, m, c, _) in enumerate(objs, start=2):
        pi = mats["#%02X%02X%02X" % c]
        x.append(f'<object id="{i}" name={quoteattr(name)} type="model" pid="1" pindex="{pi}">'
                 '<mesh><vertices>')
        x += [f'<vertex x="{a:.5f}" y="{b:.5f}" z="{d:.5f}"/>' for a, b, d in m.vertices]
        x.append('</vertices><triangles>')
        x += [f'<triangle v1="{a}" v2="{b}" v3="{d}"/>' for a, b, d in m.faces]
        x.append('</triangles></mesh></object>')
        build.append(f'<item objectid="{i}"/>')
    x.append('</resources><build>' + "".join(build) + '</build></model>')
    ct = ('<?xml version="1.0" encoding="UTF-8"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "\n".join(x))


def sanitize_gml(text):
    """Chaves como <links>, <total link strength> ou score<avg._pub._year> (VOSviewer) não são
    GML válido. Fora de textos entre aspas, viram 'links', 'total_link_strength' e
    'score_avg_pub_year'."""
    def fix(m):
        if m.group(1):                      # texto entre aspas: não mexe
            return m.group(1)
        prefix, inner = m.group(2), m.group(3)
        key = re.sub(r"[^0-9a-z]+", "_", inner.lower()).strip("_") or "attr"
        if prefix:
            key = prefix + "_" + key
        return key if key[0].isalpha() else "a_" + key
    return re.sub(r'("(?:[^"\\]|\\.)*")|([A-Za-z0-9_]*)<([^<>"\n]+)>', fix, text)


def load_gml(path):
    """Lê o GML como UTF-8, corrige chaves inválidas e usa o 'id' como chave do nó."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        text = sanitize_gml(f.read())
    try:
        return nx.parse_gml(text, label="id")
    except nx.NetworkXError as e:
        print("Erro ao ler o GML:", e)
        print("Primeiras linhas do arquivo (após correção):")
        print("\n".join(text.splitlines()[:14]))
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", nargs="?", default="2Dgraph.gml")
    p.add_argument("output", nargs="?", default="3Dgraph.3mf")
    p.add_argument("--cluster-attr", default="cluster", help="atributo do nó que define o cluster")
    p.add_argument("--scale-xy", type=float, default=50)
    p.add_argument("--z-attr", default="score_avg_pub_year",
                   help="atributo do nó que define Z (score<avg._pub._year> vira score_avg_pub_year)")
    p.add_argument("--z-ratio", type=float, default=1.0,
                   help="altura total em Z = maior extensão de X/Y x este fator (1.0 = proporcional)")
    p.add_argument("--node-scale", type=float, default=0.2, help="raio = grau * este valor")
    p.add_argument("--min-radius", type=float, default=0.5)
    p.add_argument("--edge-scale", type=float, default=0.6)
    p.add_argument("--edge-color", default="#888888")
    p.add_argument("--subdiv", type=int, default=2, help="resolução das esferas")
    args = p.parse_args()

    graph = load_gml(args.input)
    objs = build_objects(graph, args)
    write_3mf(args.output, objs)
    print(f"Gerado {args.output}. Um objeto por cluster (atribua um filamento a cada):")
    for name, _, c, n in objs:
        print(f"  {name:32s} #{c[0]:02x}{c[1]:02x}{c[2]:02x}  {n} nós")


if __name__ == "__main__":
    main()
