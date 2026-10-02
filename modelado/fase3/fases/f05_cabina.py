"""F05 — Consolas laterales, asientos, observadores, mamparo trasero, puerta, forro y techo."""
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
import axlib as ax
from panel_lib import Panel

a = ax.iniciar("F05")
rnd = random.Random(5)
root = ax.ROOT()
M = root.matrix_world
Mi = M.inverted()
sc = bpy.context.scene
COL_E = bpy.data.collections["Estructura"]
COL_D = bpy.data.collections["Detalles"]
COL_A = bpy.data.collections["Asientos"]
YB = -1.615   # plano del mamparo trasero


def actualizar():
    bpy.context.view_layer.update()


def emparentar_mundo(ob, padre):
    actualizar()
    mw = ob.matrix_world.copy()
    ob.parent = padre
    ob.matrix_parent_inverse = Matrix.Identity(4)
    actualizar()
    ob.matrix_world = mw


def rayo(o_local, d_local, dist=3.0, excluir=()):
    dg = bpy.context.evaluated_depsgraph_get()
    o = M @ Vector(o_local)
    d = (M.to_3x3() @ Vector(d_local)).normalized()
    for _ in range(6):
        h, loc, nor, i, ob, _m = sc.ray_cast(dg, o, d, distance=dist)
        if not h:
            return None
        if ob.name in excluir or ob.name.startswith(("DIAG", "CAB_Fuente")):
            o = loc + d * 0.002
            continue
        return Mi @ loc, (Mi.to_3x3() @ nor).normalized(), ob.name
    return None


def caja_obj(nombre, tam, loc, col, padre="CAB_Root", rot=(0, 0, 0), mats=("MAT_CAB_Pintura_Gris",), bisel=0.002, centro=(0, 0, 0)):
    bm = ax.bm_nuevo()
    ax.caja(bm, tam, centro)
    ob = ax.objeto(nombre, ax.bm_a_malla(nombre, bm), col, padre, loc, rot)
    ax.asignar(ob, *mats)
    ax.estilo(ob, bisel=bisel, segs=2)
    return ob


def placard(nombre, txt_lineas, loc, rot, col, padre="CAB_Root", ancho=0.10, alto=0.03, mat="MAT_CAB_Placard_Negro",
            mat_txt="MAT_CAB_Etiqueta", tam=0.0045):
    ob = caja_obj(nombre, (ancho, alto, 0.0008), loc, col, padre, rot, (mat,), bisel=0.0003)
    n = len(txt_lineas)
    items = [((0, (n - 1) * tam * 0.65 - i * tam * 1.3, 0.00045), t) for i, t in enumerate(txt_lineas)]
    ax.rotulos(nombre + "_Txt", items, tam, mat_txt, col, ob)
    return ob


# ------------------------------------------------------------------ materiales auxiliares
src = bpy.data.materials["MAT_CAB_Cuero"]
liso = src.copy()
liso.name = "MAT_CAB_Cuero_Liso"
ax.marcar(liso)
for nd in liso.node_tree.nodes:
    if nd.type == "GROUP" and nd.node_tree and nd.node_tree.name == "NG_CAB_Parametros":
        for l in list(nd.outputs["Piel_Oveja"].links):
            dest = l.to_socket
            liso.node_tree.links.remove(l)
            try:
                dest.default_value = 0.0
            except Exception:
                pass
asientos_piloto = set()
for base in ("CAB_Asiento_Cojin", "CAB_Asiento_Respaldo", "CAB_Asiento_Reposacabezas", "CAB_Asiento_Lateral_+0.24",
             "CAB_Asiento_Lateral_-0.24"):
    asientos_piloto |= {base, base + "_FO"}
for ob in bpy.data.objects:
    if ob.type in ("MESH", "CURVE") and ob.name not in asientos_piloto:
        for s in ob.material_slots:
            if s.material == src:
                s.material = liso

m = ax.material("MAT_CAB_Blanco_Botiquin")
n = ax.Nodos(m.node_tree)
ax.salida_material(n, ax.principled(n, base=(0.82, 0.82, 0.8, 1), rough=0.45))
m = ax.material("MAT_CAB_Rojo_Cruz")
n = ax.Nodos(m.node_tree)
ax.salida_material(n, ax.principled(n, base=(0.6, 0.02, 0.02, 1), rough=0.5))

# juntas y fijaciones procedurales en el forro y el mamparo (coordenadas de mundo)
fm = bpy.data.materials["MAT_CAB_Forro"]
nt = fm.node_tree
n = ax.Nodos(nt)
bsdf = next(x for x in nt.nodes if x.type == "BSDF_PRINCIPLED")
geo = n.nodo("ShaderNodeNewGeometry")
px, py, pz = n.sep(geo.outputs["Position"])


def linea_rep(c, paso, ancho=0.0016, desfase=0.0):
    r = n.mat("SUBTRACT", n.mat("ADD", c, desfase), n.mat("MULTIPLY", n.mat("ROUND", n.mat("DIVIDE", n.mat("ADD", c, desfase), paso)), paso))
    return n.mat("SUBTRACT", 1.0, n.suave(n.mat("ABSOLUTE", r), ancho * 0.5, ancho))


def puntos_rep(c, paso, desfase=0.0):
    r = n.mat("SUBTRACT", n.mat("ADD", c, desfase), n.mat("MULTIPLY", n.mat("ROUND", n.mat("DIVIDE", n.mat("ADD", c, desfase), paso)), paso))
    return n.mat("SUBTRACT", 1.0, n.suave(n.mat("ABSOLUTE", r), 0.0028, 0.0042))


jx = linea_rep(px, 0.53, desfase=0.11)
jy = linea_rep(py, 0.64, desfase=0.32)
jz = linea_rep(pz, 0.58, desfase=0.05)
junta = n.mat("MAXIMUM", jx, n.mat("MAXIMUM", jy, jz))
# fijaciones: a lo largo de las juntas cada 0,16 m
fx = n.mat("MULTIPLY", linea_rep(px, 0.53, 0.012, 0.11), n.mat("MAXIMUM", puntos_rep(py, 0.16, 0.05), puntos_rep(pz, 0.16, 0.05)))
fz = n.mat("MULTIPLY", linea_rep(pz, 0.58, 0.012, 0.05), n.mat("MAXIMUM", puntos_rep(px, 0.16, 0.02), puntos_rep(py, 0.16, 0.02)))
fij = n.mat("MAXIMUM", fx, fz)
fij = n.mat("MULTIPLY", fij, n.mat("SUBTRACT", 1.0, junta))
col_link = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].links else None
base_old = col_link if col_link is not None else tuple(bsdf.inputs["Base Color"].default_value)
nueva = n.mezcla(n.mat("MULTIPLY", junta, 0.75), base_old, (0.06, 0.065, 0.07, 1))
nueva = n.mezcla(fij, nueva, (0.42, 0.43, 0.44, 1))
nt.links.new(nueva, bsdf.inputs["Base Color"])
bump = n.nodo("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.6
bump.inputs["Distance"].default_value = 0.0012
n.con(bump.inputs["Height"], n.mat("SUBTRACT", n.mat("MULTIPLY", fij, 0.5), junta))
if bsdf.inputs["Normal"].links:
    nt.links.new(bsdf.inputs["Normal"].links[0].from_socket, bump.inputs["Normal"])
nt.links.new(bump.outputs[0], bsdf.inputs["Normal"])
fm["ax_juntas"] = "F05"

# ------------------------------------------------------------------ 1. mamparo trasero: armarios y equipamiento
COLM = ax.coleccion("Mamparo_Trasero", "CABINA")
# armario de equipaje de tripulación (izquierda, abajo) y armario de documentación (encima)
caja_obj("CAB_Mamparo_Equipaje", (0.95, 0.42, 0.78), (-1.85, YB + 0.21, 0.39), COLM, mats=("MAT_CAB_Pintura_Gris",), bisel=0.006)
for i, x in enumerate((-2.08, -1.62)):
    caja_obj(f"CAB_Mamparo_Equipaje_Puerta_{i}", (0.44, 0.012, 0.70), (x, YB + 0.426, 0.40), COLM, mats=("MAT_CAB_Panel_Claro",), bisel=0.004)
    caja_obj(f"CAB_Mamparo_Equipaje_Tirador_{i}", (0.09, 0.02, 0.018), (x + (0.17 if i == 0 else -0.17), YB + 0.44, 0.66), COLM,
             mats=("MAT_CAB_Metal_Cepillado",), bisel=0.003)
placard("CAB_Mamparo_Equipaje_Placard", ["CREW BAGGAGE", "MAX 30 KG"], (-1.85, YB + 0.4335, 0.70), (math.radians(90), 0, 0), COLM, ancho=0.16, alto=0.04)
caja_obj("CAB_Mamparo_Documentacion", (0.78, 0.30, 0.52), (-1.85, YB + 0.15, 1.30), COLM, mats=("MAT_CAB_Pintura_Gris",), bisel=0.006)
for i, x in enumerate((-2.04, -1.66)):
    caja_obj(f"CAB_Mamparo_Documentacion_Puerta_{i}", (0.36, 0.012, 0.46), (x, YB + 0.306, 1.30), COLM, mats=("MAT_CAB_Panel_Claro",), bisel=0.004)
    caja_obj(f"CAB_Mamparo_Documentacion_Cierre_{i}", (0.03, 0.016, 0.05), (x + (0.15 if i == 0 else -0.15), YB + 0.318, 1.30), COLM,
             mats=("MAT_CAB_Metal_Anodizado",), bisel=0.003)
placard("CAB_Mamparo_Documentacion_Placard", ["DOCUMENTATION", "FCOM  QRH  MEL"], (-1.85, YB + 0.3135, 1.50), (math.radians(90), 0, 0), COLM, ancho=0.18, alto=0.04)
# perchero
bm = ax.bm_nuevo()
ax.caja(bm, (0.42, 0.02, 0.05), (0, 0, 0))
for x in (-0.15, -0.05, 0.05, 0.15):
    ax.cilindro(bm, 0.005, 0.06, 12, (x, 0.03, 0.0), eje="Y")
    ax.esfera(bm, 0.009, (x, 0.062, 0.006), 12, 8)
per = ax.objeto("CAB_Mamparo_Perchero", ax.bm_a_malla("perchero", bm), COLM, "CAB_Root", (1.70, YB + 0.01, 1.78))
ax.asignar(per, "MAT_CAB_Metal_Cepillado"); ax.estilo(per, bisel=0.002)
# PBE (capucha antihumo) en su contenedor
caja_obj("CAB_Mamparo_PBE", (0.26, 0.16, 0.30), (1.40, YB + 0.08, 1.38), COLM, mats=("MAT_CAB_Placard_Amarillo",), bisel=0.008)
caja_obj("CAB_Mamparo_PBE_Tirador", (0.12, 0.02, 0.03), (1.40, YB + 0.17, 1.27), COLM, mats=("MAT_CAB_Rojo_Fuego",), bisel=0.004)
placard("CAB_Mamparo_PBE_Placard", ["PROTECTIVE", "BREATHING EQUIPMENT", "PULL TO OPEN"], (1.40, YB + 0.1605, 1.44),
        (math.radians(90), 0, 0), COLM, ancho=0.20, alto=0.07, tam=0.0085)
# gafas antihumo
caja_obj("CAB_Mamparo_Gafas", (0.16, 0.07, 0.10), (1.40, YB + 0.035, 1.12), COLM, mats=("MAT_CAB_Placard_Negro",), bisel=0.006)
placard("CAB_Mamparo_Gafas_Placard", ["SMOKE GOGGLES"], (1.40, YB + 0.0705, 1.12), (math.radians(90), 0, 0), COLM, ancho=0.13, alto=0.025)
# botiquín
caja_obj("CAB_Mamparo_Botiquin", (0.30, 0.13, 0.22), (1.90, YB + 0.065, 0.98), COLM, mats=("MAT_CAB_Blanco_Botiquin",), bisel=0.01)
bm = ax.bm_nuevo()
ax.caja(bm, (0.08, 0.002, 0.024), (0, 0, 0)); ax.caja(bm, (0.024, 0.002, 0.08), (0, 0, 0))
cr = ax.objeto("CAB_Mamparo_Botiquin_Cruz", ax.bm_a_malla("cruz", bm, suave=False), COLM, "CAB_Root", (1.90, YB + 0.1305, 1.00))
ax.asignar(cr, "MAT_CAB_Rojo_Cruz")
placard("CAB_Mamparo_Botiquin_Placard", ["FIRST AID KIT"], (1.90, YB + 0.1305, 0.90), (math.radians(90), 0, 0), COLM, ancho=0.14, alto=0.025)
# extintor: precinto de alambre con plomo y placard; hacha: soporte con presillas
ext = bpy.data.objects["CAB_Extintor"]
bm = ax.bm_nuevo()
ax.cilindro(bm, 0.0006, 0.05, 6, (0, 0, 0), eje="X")
ax.cilindro(bm, 0.0045, 0.003, 16, (0.028, 0, -0.004), eje="Y")
pre = ax.objeto("CAB_Extintor_Precinto", ax.bm_a_malla("precinto", bm), COL_D, ext, (0.0, -0.035, 0.455))
ax.asignar(pre, "MAT_CAB_Rojo_Fuego")
placard("CAB_Extintor_Placard", ["HALON 1211", "FIRE EXTINGUISHER"], (0.82, YB + 0.002, 0.62), (math.radians(90), 0, 0), COL_D,
        ancho=0.15, alto=0.04, mat="MAT_CAB_Placard_Plata", mat_txt="MAT_CAB_Tinta")
hacha = bpy.data.objects["CAB_Hacha"]
for z in (-0.12, 0.10):
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.05, 0.03, 0.022), (0, 0, 0))
    ob = ax.objeto(f"CAB_Hacha_Presilla_{'a' if z < 0 else 'b'}", ax.bm_a_malla("presilla", bm), COL_D, hacha, (0.0, 0.004, z))
    ax.asignar(ob, "MAT_CAB_Goma"); ax.estilo(ob, bisel=0.003)
# juntas de panel del mamparo (relieve) y tornillería del contorno
pts = []
for x in [-2.6 + i * 0.32 for i in range(17)]:
    if abs(x) < 0.52:
        continue
    for z in (0.05, 0.62, 1.24, 1.86, 2.45):
        pts.append((x, YB + 0.0015, z))
tor = ax.puntos("CAB_Mamparo_Fijaciones", pts, COLM, "CAB_Root",
                atributos={"cab_normal": ("FLOAT_VECTOR", [(0, 1, 0)] * len(pts))})
ax.gn(tor, "GN_CAB_Instancias_Puntos", Objeto="CAB_Fuente_Tornillo_Plano", Escala=1.0, Giro_Aleatorio=6.28, Semilla=4)

# ------------------------------------------------------------------ 2. puerta blindada
piv = bpy.data.objects["CAB_Puerta_Pivote"]
ref = bpy.data.objects["CAB_Puerta_Hoja"]
actualizar()
# rejilla de descompresión (persiana) en la parte baja de la hoja
bm = ax.bm_nuevo()
ax.caja(bm, (0.50, 0.012, 0.30), (0, 0, 0), mat=0)
for k in range(12):
    lam = ax.caja(bm, (0.46, 0.004, 0.016), (0, 0.006, -0.125 + k * 0.023), mat=1)
    transf = Matrix.Translation((0, 0.006, -0.125 + k * 0.023)) @ Matrix.Rotation(math.radians(35), 4, "X") @ Matrix.Translation((0, -0.006, 0.125 - k * 0.023))
    ax.transformar(bm, lam, transf)
rej = ax.objeto("CAB_Puerta_Rejilla_Descompresion", ax.bm_a_malla("rejilla", bm), COL_E, "CAB_Root", (0.0, YB + 0.032, 0.36))
ax.asignar(rej, "MAT_CAB_Pintura_Gris", "MAT_CAB_Negro_Profundo"); ax.estilo(rej, bisel=0.001)
emparentar_mundo(rej, piv)
# panel de acceso de emergencia (escape) en la parte alta
ob = caja_obj("CAB_Puerta_Panel_Escape", (0.40, 0.010, 0.36), (0.0, YB + 0.030, 1.30), COL_E, mats=("MAT_CAB_Panel_Claro",), bisel=0.003)
emparentar_mundo(ob, piv)
pl = placard("CAB_Puerta_Placard_Escape", ["EMERGENCY EXIT", "PUSH PANEL HARD"], (0.0, YB + 0.0356, 1.30), (math.radians(90), 0, 0), COL_E,
             ancho=0.18, alto=0.05, mat="MAT_CAB_Placard_Amarillo", mat_txt="MAT_CAB_Tinta", tam=0.007)
emparentar_mundo(pl, piv)
pl = placard("CAB_Puerta_Placard_Obstruir", ["DO NOT OBSTRUCT"], (0.0, YB + 0.0306, 0.58), (math.radians(90), 0, 0), COL_E,
             ancho=0.16, alto=0.025)
emparentar_mundo(pl, piv)
# cerrojos (pestillos eléctricos) en el canto y en el marco
for z in (0.45, 1.0, 1.55):
    ob = caja_obj(f"CAB_Puerta_Cerrojo_{int(z * 100)}", (0.03, 0.05, 0.08), (0.43, YB + 0.03, z), COL_E,
                  mats=("MAT_CAB_Metal_Cepillado",), bisel=0.003)
    ob2 = caja_obj(f"CAB_Puerta_Cerradero_{int(z * 100)}", (0.04, 0.04, 0.10), (0.475, YB + 0.025, z), COL_E,
                   mats=("MAT_CAB_Acero",), bisel=0.003)
    emparentar_mundo(ob, piv)

# ------------------------------------------------------------------ 3. observadores
# 1.º: reposacabezas, arnés (existe), ACP, máscara y auriculares
caja_obj("CAB_Jumpseat_Reposacabezas", (0.30, 0.07, 0.16), (-0.90, YB + 0.045, 1.52), COL_A, mats=("MAT_CAB_Cuero_Liso",), bisel=0.02)
obs = Panel("OBS1_ACP", COL_A, "CAB_Root", (-1.38, YB + 0.003, 1.08), (math.radians(90), 0, 0), 0.145, 0.094, prefijo="CAB_",
            semilla=61)
obs.titulo(0, 38, "ACP 4", ancho_linea=120)
for i, t in enumerate(("VHF1", "VHF2", "VHF3", "HF1", "INT", "CAB")):
    obs.pb(-55 + i * 22, 8, "", "", t, "W", "W", id_=f"OBS1_{i}")
for i, x in enumerate((-50, -20, 10, 40)):
    obs.knob(x, -22, "", "", "", valor=0.4, arco=200, marcas=5, radio=9.0)
obs.cerrar()
caja_obj("CAB_Jumpseat_Mascara_Caja", (0.19, 0.11, 0.13), (-1.38, YB + 0.055, 1.33), COL_A, mats=("MAT_CAB_Plastico_Gris",), bisel=0.006)
placard("CAB_Jumpseat_Mascara_Placard", ["CREW OXYGEN MASK"], (-1.38, YB + 0.1106, 1.36), (math.radians(90), 0, 0), COL_A, ancho=0.15, alto=0.022)
caja_obj("CAB_Jumpseat_Auriculares_Gancho", (0.04, 0.05, 0.03), (-1.18, YB + 0.03, 1.45), COL_A, mats=("MAT_CAB_Plastico_Mate",), bisel=0.004)
bm = ax.bm_nuevo()
bmesh.ops.create_circle(bm, cap_ends=False, segments=24, radius=0.075)
r = bmesh.ops.extrude_edge_only(bm, edges=bm.edges[:])
for v in bm.verts:
    if v.co.y < -0.01:
        v.select = False
au = ax.objeto("CAB_Jumpseat_Auriculares", ax.bm_a_malla("aur", bm), COL_A, "CAB_Root", (-1.18, YB + 0.06, 1.37), (math.radians(90), 0, 0))
au.modifiers.new("Solid", "SOLIDIFY").thickness = 0.012
ax.asignar(au, "MAT_CAB_Plastico_Mate")
for sx in (-0.075, 0.075):
    ob = ax.objeto(f"CAB_Jumpseat_Auricular_Copa_{'a' if sx < 0 else 'b'}", None, COL_A, "CAB_Root")
    bpy.data.objects.remove(ob)
    bm = ax.bm_nuevo(); ax.cilindro(bm, 0.035, 0.03, 24, (0, 0, 0), eje="X")
    ob = ax.objeto(f"CAB_Jumpseat_Auricular_Copa_{'a' if sx < 0 else 'b'}", ax.bm_a_malla("copa", bm), COL_A, "CAB_Root",
                   (-1.18 + sx, YB + 0.065, 1.33))
    ax.asignar(ob, "MAT_CAB_Plastico_Mate"); ax.estilo(ob, bisel=0.006, segs=3)

# 2.º observador nuevo: copia del transportín plegado en el lado derecho
fuente = [o for o in bpy.data.objects if o.name.startswith("CAB_Jumpseat_") and o.get("ax_fase") is None]
mapa = {}
for s_ in fuente:
    c = s_.copy()
    if s_.data is not None:
        c.data = s_.data.copy()
    c.name = s_.name.replace("CAB_Jumpseat_", "CAB_Jumpseat2_")
    ax.marcar(c)
    for cc in list(c.users_collection):
        cc.objects.unlink(c)
    COL_A.objects.link(c)
    mapa[s_] = c
for s_, c in mapa.items():
    c.parent = mapa.get(s_.parent, s_.parent)
    c.matrix_parent_inverse = s_.matrix_parent_inverse.copy()
    c.matrix_basis = s_.matrix_basis.copy()
    if c.parent == root:
        if c.type == "CURVE":
            for sp in c.data.splines:
                for p in sp.bezier_points:
                    for at in ("co", "handle_left", "handle_right"):
                        v = getattr(p, at); setattr(p, at, Vector((v.x + 2.50, v.y, v.z)))
                for p in sp.points:
                    p.co = (p.co[0] + 2.50, p.co[1], p.co[2], p.co[3])
        elif c.location.length < 1e-6 and c.data is not None and hasattr(c.data, "vertices"):
            for v in c.data.vertices:
                v.co.x += 2.50
        else:
            c.location.x += 2.50
caja_obj("CAB_Jumpseat2_Reposacabezas", (0.30, 0.07, 0.16), (1.60, YB + 0.045, 1.52), COL_A, mats=("MAT_CAB_Cuero_Liso",), bisel=0.02)

# ------------------------------------------------------------------ 4. consolas laterales (ambos lados)
COL_L = bpy.data.collections["Laterales"]
ax.propiedad("Mesa_Capitan", 0.0, 0.0, 1.0, "Mesa extraíble del capitán: 0 recogida · 1 extendida")
ax.propiedad("Mesa_FO", 0.0, 0.0, 1.0, "Mesa extraíble del primer oficial: 0 recogida · 1 extendida")
for lado, s in (("L", -1), ("R", 1)):
    suf = "" if s < 0 else "_FO"
    # mesa extraíble: sale del frontal de la consola hacia el piloto
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.40, 0.34, 0.012), (0, -0.17, 0))
    ax.caja(bm, (0.40, 0.02, 0.03), (0, -0.335, 0.008))
    mesa = ax.objeto(f"CAB_Mesa_{lado}", ax.bm_a_malla("mesa", bm), COL_L, "CAB_Root", (s * 1.08, 0.80, 0.475))
    ax.asignar(mesa, "MAT_CAB_Plastico_Gris"); ax.estilo(mesa, bisel=0.003)
    prop = "Mesa_Capitan" if s < 0 else "Mesa_FO"
    ax.driver(mesa, "location", "0.80 - m * 0.34", {"m": prop}, indice=1)
    ax.limitar_loc(mesa, y=(0.46, 0.80))
    placard(f"CAB_Mesa_Placard_{lado}", ["PULL"], (s * 1.08, 0.4645, 0.475), (math.radians(90), 0, 0), COL_L, ancho=0.05, alto=0.012)
    emparentar_mundo(bpy.data.objects[f"CAB_Mesa_Placard_{lado}"], mesa)
    # soporte de EFB (tableta) en brazo articulado sobre la consola exterior
    bm = ax.bm_nuevo()
    ax.cilindro(bm, 0.012, 0.16, 16, (0, 0, 0.08))
    ax.caja(bm, (0.03, 0.03, 0.03), (0, 0, 0.165))
    efb_b = ax.objeto(f"CAB_EFB_Brazo_{lado}", ax.bm_a_malla("efb_b", bm), COL_L, "CAB_Root", (s * 1.55, 0.32, 0.43))
    ax.asignar(efb_b, "MAT_CAB_Metal_Anodizado"); ax.estilo(efb_b, bisel=0.002)
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.26, 0.012, 0.18), (0, 0, 0), mat=0)
    ax.caja(bm, (0.235, 0.002, 0.155), (0, -0.0065, 0), mat=1)
    efb = ax.objeto(f"CAB_EFB_Tableta_{lado}", ax.bm_a_malla("efb", bm), COL_L, "CAB_Root", (s * 1.55, 0.32, 0.70),
                    (math.radians(-15), 0, math.radians(-25 * s)))
    ax.asignar(efb, "MAT_CAB_Plastico_Mate", "MAT_CAB_Pantalla_MCDU"); ax.estilo(efb, bisel=0.004, segs=3)
    # ACP lateral (jacks de audio: HEADSET / BOOM / MASK)
    acp = Panel(f"ACP_LAT_{lado}", COL_L, "CAB_Root", (s * 1.62, 0.02, 0.432), (0, 0, 0), 0.11, 0.06, prefijo="CAB_",
                semilla=71 + s)
    acp.titulo(0, 23, "AUDIO", ancho_linea=95)
    for i, (t, x) in enumerate((("HEADSET", -32), ("BOOM", 0), ("MASK", 32))):
        acp.instancia("CAB_Fuente_Taladro", x, -2)
        acp.texto(x, -14, t, "mini")
    acp.cerrar()
    # gasper (difusor orientable) en la pared, bajo la ventana lateral
    for k, (y, z) in enumerate(((0.05, 0.95), (-0.35, 0.95))):
        hit = rayo((s * 1.6, y, z), (s, 0, 0))
        if hit:
            p, nrm, _ = hit
            bm = ax.bm_nuevo()
            ax.cilindro(bm, 0.032, 0.012, 32, (0, 0, 0.006), mat=0)
            ax.esfera(bm, 0.022, (0, 0, 0.012), 24, 12, mat=1)
            ax.cilindro(bm, 0.009, 0.012, 16, (0.004, 0.0, 0.03), mat=0)
            g = ax.objeto(f"CAB_Gasper_{lado}_{k}", ax.bm_a_malla("gasper", bm), COL_L, "CAB_Root", p,
                          (-nrm).to_track_quat("-Z", "Z").to_euler())
            g.rotation_euler = nrm.to_track_quat("Z", "Y").to_euler()
            ax.asignar(g, "MAT_CAB_Plastico_Gris", "MAT_CAB_Cromo"); ax.estilo(g, bisel=0.001)
    # calefactor de pies (rejilla en el frontal bajo de la consola)
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.24, 0.006, 0.12), (0, 0, 0), mat=0)
    for k in range(9):
        ax.caja(bm, (0.22, 0.004, 0.005), (0, -0.004, -0.048 + k * 0.012), mat=1)
    cal = ax.objeto(f"CAB_Calefactor_Pies_{lado}", ax.bm_a_malla("calef", bm), COL_L, "CAB_Root", (s * 1.08, 0.494, 0.13))
    ax.asignar(cal, "MAT_CAB_Pintura_Gris", "MAT_CAB_Negro_Profundo"); ax.estilo(cal, bisel=0.001)
    placard(f"CAB_Calefactor_Placard_{lado}", ["FOOT WARMER"], (s * 1.08, 0.4905, 0.205), (math.radians(90), 0, 0), COL_L, ancho=0.12, alto=0.02)
    # compartimento de la cuerda de escape sobre la ventana lateral
    hit = rayo((s * 1.6, 0.85, 1.72), (s, 0, 0.25))
    if hit:
        p, nrm, _ = hit
        q = nrm.to_track_quat("Z", "Y").to_euler()
        ob = caja_obj(f"CAB_Cuerda_Escape_Tapa_{lado}", (0.30, 0.16, 0.012), p + nrm * 0.006, COL_L, rot=q, mats=("MAT_CAB_Panel_Claro",), bisel=0.004)
        placard(f"CAB_Cuerda_Escape_Placard_{lado}", ["ESCAPE ROPE"], p + nrm * 0.0125, q, COL_L, ancho=0.15, alto=0.03,
                mat="MAT_CAB_Placard_Amarillo", mat_txt="MAT_CAB_Tinta", tam=0.007)

# ------------------------------------------------------------------ 5. asientos de pilotos
ax.propiedad("Asiento_Lumbar", 0.4, 0.0, 1.0, "Ajuste lumbar de los asientos")
for suf, s in (("", -1), ("_FO", 1)):
    resp = bpy.data.objects["CAB_Asiento_Respaldo_Pivote" + suf]
    asi = bpy.data.objects["CAB_Asiento_Capitan" if not suf else "CAB_Asiento_Primer_Oficial"]
    actualizar()
    x0 = asi.matrix_world.translation
    xc = (Mi @ x0).x
    # enrollador del arnés (caja en lo alto del respaldo, por detrás)
    ob = caja_obj(f"CAB_Asiento_Enrollador{suf}", (0.11, 0.06, 0.07), (xc, -0.40, 0.90), COL_A, mats=("MAT_CAB_Plastico_Mate",), bisel=0.008)
    emparentar_mundo(ob, resp)
    # ajuste lumbar (mando en el lateral del respaldo)
    bm = ax.bm_nuevo(); ax.cilindro(bm, 0.022, 0.016, 32, (0, 0, 0), eje="X")
    lum = ax.objeto(f"CAB_Asiento_Lumbar{suf}", ax.bm_a_malla("lumbar", bm), COL_A, "CAB_Root", (xc - s * 0.255, -0.33, 0.52))
    ax.asignar(lum, "MAT_CAB_Plastico_Knob"); ax.estilo(lum, bisel=0.002)
    ax.gn(lum, "GN_CAB_Moleteado", Dientes=40.0, Profundidad=0.0006, Z_Min=-1.0, Z_Max=1.0)
    emparentar_mundo(lum, resp)
    ax.driver(lum, "rotation_euler", "l * 3.14", {"l": "Asiento_Lumbar"}, indice=0)
    # chaleco salvavidas bajo el asiento (bolsa) y placard
    ob = caja_obj(f"CAB_Asiento_Chaleco{suf}", (0.30, 0.10, 0.06), (xc, 0.00, 0.10), COL_A, mats=("MAT_CAB_Placard_Amarillo",), bisel=0.02)
    emparentar_mundo(ob, asi)
    pl = placard(f"CAB_Asiento_Chaleco_Placard{suf}", ["LIFE VEST UNDER SEAT"], (xc, 0.051, 0.16), (math.radians(90), 0, 0), COL_A,
                 ancho=0.16, alto=0.02, mat="MAT_CAB_Placard_Amarillo", mat_txt="MAT_CAB_Tinta")
    emparentar_mundo(pl, asi)
    pl = placard(f"CAB_Asiento_Placard_Ajuste{suf}", ["SEAT ADJ", "FWD/AFT  HEIGHT  RECLINE"], (xc - s * 0.257, -0.10, 0.23),
                 (math.radians(90), 0, math.radians(90 * s)), COL_A, ancho=0.12, alto=0.03)
    emparentar_mundo(pl, asi)

# ------------------------------------------------------------------ 6. techo: rejillas de aire y luces de lectura del techo
for k, (x, y) in enumerate(((-0.75, -0.25), (0.75, -0.25), (-0.75, 0.25), (0.75, 0.25), (0.0, -1.25))):
    hit = rayo((x, y, 1.6), (0, 0, 1))
    if not hit:
        continue
    p, nrm, _ = hit
    q = nrm.to_track_quat("Z", "Y").to_euler()
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.22, 0.08, 0.008), (0, 0, 0.004), mat=0)
    for j in range(8):
        ax.caja(bm, (0.20, 0.004, 0.006), (0, -0.032 + j * 0.009, 0.006), mat=1)
    ob = ax.objeto(f"CAB_Techo_Rejilla_{k}", ax.bm_a_malla("rej", bm), COL_E, "CAB_Root", p - nrm * 0.002, q)
    ob.rotation_euler = (-nrm).to_track_quat("Z", "Y").to_euler()
    ob.location = p - nrm * 0.003
    ax.asignar(ob, "MAT_CAB_Plastico_Gris", "MAT_CAB_Negro_Profundo"); ax.estilo(ob, bisel=0.001)

ax.informe(ok=True)
ax.guardar(a.salida)
