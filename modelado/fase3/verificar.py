"""Verificaciones finales del .blend de la Fase 3 (alcance: CABINA, Morro_Exterior, Morro_Ventanas)."""
import bpy, json
ALC = ["CABINA", "Morro_Exterior", "Morro_Ventanas"]
cols = set()
def rec(c):
    cols.add(c.name)
    for h in c.children: rec(h)
for n in ALC: rec(bpy.data.collections[n])
alc = [o for o in bpy.data.objects if any(c.name in cols for c in o.users_collection)]
neg = [o.name for o in bpy.data.objects if o.matrix_world.determinant() < 0 or any(s < 0 for s in o.scale)]
neg_alc = [n for n in neg if n in {o.name for o in alc}]
mats = set()
for o in alc:
    for s in o.material_slots:
        if s.material: mats.add(s.material)
def imagenes_en(nt, vistos=None):
    vistos = vistos or set(); out = []
    for n in nt.nodes:
        if n.type in ("TEX_IMAGE", "TEX_ENVIRONMENT") and n.image: out.append(n.image.name)
        if n.type == "GROUP" and n.node_tree and n.node_tree.name not in vistos:
            vistos.add(n.node_tree.name); out += imagenes_en(n.node_tree, vistos)
    return out
tex = {m.name: imagenes_en(m.node_tree) for m in mats if m.node_tree}
tex = {k: v for k, v in tex.items() if v}
no_simples, total = [], 0
for coleccion in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.node_groups, bpy.data.lights,
                  bpy.data.cameras, bpy.data.worlds):
    for idb in coleccion:
        ad = getattr(idb, "animation_data", None)
        if ad:
            for fc in ad.drivers:
                total += 1
                d = fc.driver
                if d.type == "SCRIPTED" and not d.is_simple_expression:
                    no_simples.append((idb.name, fc.data_path, d.expression))
                if not d.is_valid:
                    no_simples.append((idb.name, fc.data_path, "NO VÁLIDO"))
sc = bpy.context.scene
camaras = [o.name for o in bpy.data.collections["Camaras_Presentacion"].objects if o.type == "CAMERA"]
r = {"escala_negativa_total": neg, "escala_negativa_alcance": neg_alc, "materiales_alcance": len(mats),
     "texturas_imagen_en_alcance": tex, "drivers_total": total, "drivers_no_simples_o_invalidos": no_simples[:20],
     "camaras_presentacion": len(camaras), "escena": sc.name, "camara_activa": sc.camera.name if sc.camera else None,
     "frame_end": sc.frame_end, "fps": sc.render.fps, "imagenes_sin_empaquetar": [i.name for i in bpy.data.images if not i.packed_file and i.source == "FILE"],
     "lod_cabina": bpy.data.objects["CAB_Control"]["LOD_Cabina"], "props_cab_control": len(bpy.data.objects["CAB_Control"].keys())}
print("VERIF " + json.dumps(r, ensure_ascii=False))
