"""Inventario del AX620: estructura, triángulos evaluados y huella del resto del avión.

blender -b X.blend -P inventario_ax620.py -- --salida inventario.json [--sin-tris]
"""
import bpy, sys, json, hashlib, argparse, time
from collections import defaultdict

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--salida", required=True)
ap.add_argument("--sin-tris", action="store_true")
a = ap.parse_args(argv)

ALCANCE_RAICES = ["CABINA", "Morro_Exterior", "Morro_Ventanas"]
t0 = time.time()


def arbol(col, prof=0, out=None):
    out = [] if out is None else out
    out.append({"nombre": col.name, "prof": prof, "objetos": len(col.objects),
                "hijos": [c.name for c in col.children]})
    for c in col.children:
        arbol(c, prof + 1, out)
    return out


def colecciones_de(raiz):
    res = set()
    def rec(c):
        res.add(c.name)
        for h in c.children:
            rec(h)
    rec(raiz)
    return res


escena = bpy.context.scene
inv = {"archivo": bpy.data.filepath, "blender": bpy.app.version_string,
       "version_archivo": list(bpy.data.version), "escenas": [s.name for s in bpy.data.scenes],
       "escena_activa": escena.name}
r = escena.render
inv["render"] = {"motor": r.engine, "res": [r.resolution_x, r.resolution_y, r.resolution_percentage],
                 "fps": r.fps, "frames": [escena.frame_start, escena.frame_end],
                 "unidades": [escena.unit_settings.system, escena.unit_settings.scale_length],
                 "world": escena.world.name if escena.world else None,
                 "camara": escena.camera.name if escena.camera else None,
                 "view_transform": escena.view_settings.view_transform}
inv["colecciones"] = arbol(escena.collection)

alcance_cols = set()
for n in ALCANCE_RAICES:
    c = bpy.data.collections.get(n)
    if c:
        alcance_cols |= colecciones_de(c)
    else:
        print("FALTA colección", n)
inv["colecciones_alcance"] = sorted(alcance_cols)


def en_alcance(ob):
    return any(c.name in alcance_cols for c in ob.users_collection)


# colección "propietaria" para el reparto de triángulos (la primera de alcance o la primera)
def col_principal(ob):
    for c in ob.users_collection:
        if c.name in alcance_cols:
            return c.name
    return ob.users_collection[0].name if ob.users_collection else "(sin colección)"


objs_alcance, objs_resto = [], []
for ob in bpy.data.objects:
    (objs_alcance if en_alcance(ob) else objs_resto).append(ob)


def r6(v):
    return [round(x, 6) for x in v]


def info_obj(ob):
    d = {"nombre": ob.name, "tipo": ob.type, "datos": ob.data.name if ob.data else None,
         "col": [c.name for c in ob.users_collection], "padre": ob.parent.name if ob.parent else None,
         "loc": r6(ob.location), "rot": r6(ob.rotation_euler), "esc": r6(ob.scale),
         "oculto_render": ob.hide_render, "oculto_vista": ob.hide_viewport}
    if ob.instance_type == "COLLECTION" and ob.instance_collection:
        d["instancia"] = ob.instance_collection.name
    mods = []
    for m in ob.modifiers:
        e = {"n": m.name, "t": m.type}
        if m.type == "NODES" and m.node_group:
            e["grupo"] = m.node_group.name
        if m.type == "BOOLEAN":
            e["op"] = m.operation
            e["obj"] = m.object.name if m.object else (m.collection.name if m.collection else None)
        mods.append(e)
    if mods:
        d["mods"] = mods
    if ob.type == "MESH":
        d["v"] = len(ob.data.vertices)
        d["f"] = len(ob.data.polygons)
    mats = [s.material.name for s in ob.material_slots if s.material]
    if mats:
        d["mats"] = mats
    props = {k: (v if isinstance(v, (int, float, str, bool)) else str(v)) for k, v in ob.items()}
    if props:
        d["props"] = props
    if ob.constraints:
        d["restr"] = [(c.type, c.name) for c in ob.constraints]
    return d


inv["objetos_alcance"] = [info_obj(o) for o in objs_alcance]
inv["num_objetos"] = {"total": len(bpy.data.objects), "alcance": len(objs_alcance), "resto": len(objs_resto)}


# ---- hash del resto del avión
def hash_malla(me):
    h = hashlib.sha256()
    import array
    n = len(me.vertices)
    co = array.array("f", [0.0]) * (n * 3)
    me.vertices.foreach_get("co", co)
    h.update(co.tobytes())
    nl = len(me.loops)
    vi = array.array("i", [0]) * nl
    me.loops.foreach_get("vertex_index", vi)
    h.update(vi.tobytes())
    np_ = len(me.polygons)
    ls = array.array("i", [0]) * np_
    me.polygons.foreach_get("loop_start", ls)
    h.update(ls.tobytes())
    mi = array.array("i", [0]) * np_
    me.polygons.foreach_get("material_index", mi)
    h.update(mi.tobytes())
    return h.hexdigest()


def hash_arbol_nodos(nt):
    h = hashlib.sha256()
    if nt is None:
        return None
    for n in sorted(nt.nodes, key=lambda n: n.name):
        h.update(f"{n.name}|{n.bl_idname}|{r6(n.location)}".encode())
        for s in n.inputs:
            if hasattr(s, "default_value"):
                try:
                    v = s.default_value
                    v = list(v) if hasattr(v, "__len__") and not isinstance(v, str) else v
                    h.update(f"{s.identifier}={v}".encode())
                except Exception:
                    pass
        if getattr(n, "node_tree", None):
            h.update(n.node_tree.name.encode())
        if getattr(n, "image", None):
            h.update(n.image.name.encode())
    for l in nt.links:
        h.update(f"{l.from_node.name}.{l.from_socket.identifier}>{l.to_node.name}.{l.to_socket.identifier}".encode())
    return h.hexdigest()


hash_obj = {}
mats_resto = set()
for ob in sorted(objs_resto, key=lambda o: o.name):
    h = hashlib.sha256()
    h.update(f"{ob.name}|{ob.type}|{ob.parent.name if ob.parent else ''}".encode())
    h.update(str([r6(row) for row in ob.matrix_world]).encode())
    h.update(str([(m.name, m.type, m.show_render) for m in ob.modifiers]).encode())
    h.update(str([s.material.name if s.material else None for s in ob.material_slots]).encode())
    h.update(f"{ob.hide_render}|{ob.instance_type}|{ob.instance_collection.name if ob.instance_collection else ''}".encode())
    for s in ob.material_slots:
        if s.material:
            mats_resto.add(s.material.name)
    if ob.type == "MESH":
        h.update(hash_malla(ob.data).encode())
    hash_obj[ob.name] = h.hexdigest()
hash_mats = {m: hash_arbol_nodos(bpy.data.materials[m].node_tree) for m in sorted(mats_resto)}
tot = hashlib.sha256()
for k in sorted(hash_obj):
    tot.update(f"{k}:{hash_obj[k]}".encode())
for k in sorted(hash_mats):
    tot.update(f"{k}:{hash_mats[k]}".encode())
inv["hash_resto"] = {"total": tot.hexdigest(), "objetos": hash_obj, "materiales": hash_mats}

# ---- nodos, materiales, imágenes, drivers
inv["grupos_nodos"] = sorted([(g.name, g.bl_idname, g.users) for g in bpy.data.node_groups])
img_uso = defaultdict(list)
for m in bpy.data.materials:
    if m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                img_uso[n.image.name].append(m.name)
inv["imagenes"] = [{"nombre": i.name, "ruta": i.filepath, "empaquetada": bool(i.packed_file),
                    "tam": list(i.size), "materiales": img_uso.get(i.name, [])} for i in bpy.data.images]
inv["materiales"] = sorted([(m.name, m.users) for m in bpy.data.materials])

drivers = []
for coleccion in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.node_groups,
                  bpy.data.shape_keys, bpy.data.lights, bpy.data.cameras):
    for idb in coleccion:
        ad = getattr(idb, "animation_data", None)
        if ad and ad.drivers:
            for fc in ad.drivers:
                dv = fc.driver
                drivers.append({"id": idb.name, "ruta": fc.data_path, "i": fc.array_index,
                                "expr": dv.expression, "tipo": dv.type,
                                "vars": [(v.name, v.targets[0].id.name if v.targets[0].id else None,
                                          v.targets[0].data_path) for v in dv.variables]})
inv["drivers"] = drivers
ctrl = bpy.data.objects.get("CAB_Control")
if ctrl:
    props = {}
    for k in ctrl.keys():
        v = ctrl[k]
        try:
            ui = ctrl.id_properties_ui(k).as_dict()
        except Exception:
            ui = {}
        props[k] = {"v": v if isinstance(v, (int, float, str, bool)) else str(v),
                    "min": ui.get("min"), "max": ui.get("max"), "desc": ui.get("description")}
    inv["cab_control"] = props
inv["acciones"] = [ac.name for ac in bpy.data.actions]

# ---- triángulos evaluados por colección (instancias incluidas)
if not a.sin_tris:
    dg = bpy.context.evaluated_depsgraph_get()
    cache = {}
    por_col = defaultdict(int)
    por_obj = defaultdict(int)
    for inst in dg.object_instances:
        ob = inst.object
        if ob.type not in ("MESH", "CURVE", "FONT", "SURFACE"):
            continue
        dueno = inst.parent.original if inst.is_instance and inst.parent else ob.original
        if dueno.hide_render:
            continue
        clave = ob.data.original.name if ob.type == "MESH" and inst.is_instance else ob.name
        key = (ob.type, id(ob.data) if inst.is_instance else ob.name)
        if key not in cache:
            try:
                me = ob.to_mesh()
                me.calc_loop_triangles()
                cache[key] = len(me.loop_triangles)
                ob.to_mesh_clear()
            except Exception:
                cache[key] = 0
        n = cache[key]
        por_col[col_principal(dueno)] += n
        por_obj[dueno.name] += n
    inv["tris_por_coleccion"] = dict(sorted(por_col.items(), key=lambda x: -x[1]))
    inv["tris_alcance"] = sum(v for k, v in por_col.items() if k in alcance_cols)
    inv["tris_total"] = sum(por_col.values())
    inv["tris_top_objetos"] = sorted(por_obj.items(), key=lambda x: -x[1])[:60]
inv["t_s"] = round(time.time() - t0, 1)

with open(a.salida, "w", encoding="utf-8") as f:
    json.dump(inv, f, ensure_ascii=False, indent=1)
print("INVENTARIO OK", a.salida, inv["num_objetos"], inv.get("tris_alcance"), inv["hash_resto"]["total"], inv["t_s"])
