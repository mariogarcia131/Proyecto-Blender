"""F01 — Correcciones base.

1. Lado del primer oficial con geometría real (escala positiva) en lugar de instancias (-1,-1,-1).
2. Sidesticks: límites ±16° pitch / ±20° roll; el del FO con propiedades propias.
3. Design Eye Point: viseras recogidas en su raíl y compás standby en lo alto del poste central.
4. Parabrisas: material reescrito (arcos del limpia en su pivote real, película calefactora).
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from mathutils import Vector, Matrix, Euler
import axlib as ax

a = ax.iniciar("F01")
root = ax.ROOT()

# ------------------------------------------------------------------ 0. GN_CAB_Rotulos: el último elemento de cada
# lista no se dibujaba (en 5.2 «Find in String» no devuelve -1 si no encuentra «|»). Se decide con «Count» = 0.
g = bpy.data.node_groups["GN_CAB_Rotulos"]
for f in [n for n in g.nodes if n.bl_idname == "FunctionNodeFindInString"]:
    for l in list(f.outputs["First Found"].links):
        if l.to_node.bl_idname == "FunctionNodeCompare":
            cmp = l.to_node
            g.links.remove(l)
            cmp.data_type = "INT"
            cmp.operation = "EQUAL"
            g.links.new(f.outputs["Count"], cmp.inputs[0])   # A
            cmp.inputs[1].default_value = 0                    # B

# ------------------------------------------------------------------ 1. lado del FO
for n in ("CAB_Lateral_Primer_Oficial", "CAB_Asiento_Primer_Oficial"):
    o = bpy.data.objects.get(n)
    if o is not None and o.instance_type == "COLLECTION":
        bpy.data.objects.remove(o, do_unlink=True)

ax.propiedad("Sidestick_FO_Pitch", 0.0, -1.0, 1.0, "Sidestick primer oficial: picado/encabritado")
ax.propiedad("Sidestick_FO_Roll", 0.0, -1.0, 1.0, "Sidestick primer oficial: alabeo")
REMAPEO = {"Sidestick_Pitch": "Sidestick_FO_Pitch", "Sidestick_Roll": "Sidestick_FO_Roll"}


def nombre_fo(n):
    return "CAB_Asiento_Primer_Oficial" if n == "CAB_Asiento_Capitan" else n + "_FO"


def espejar_coleccion(src_col, dst_nombre, dst_padre):
    dst = ax.coleccion(dst_nombre, dst_padre)
    fuentes = list(src_col.objects)
    mapa, datos_hechos = {}, {}
    for s in fuentes:
        c = s.copy()
        c.name = nombre_fo(s.name)
        ax.marcar(c)
        if s.data is not None:
            clave = s.data.as_pointer()
            if clave not in datos_hechos:
                d = s.data.copy()
                d.name = s.data.name + "_FO"
                ax.espejar_datos(d)
                datos_hechos[clave] = d
            c.data = datos_hechos[clave]
        for col in list(c.users_collection):
            col.objects.unlink(c)
        dst.objects.link(c)
        mapa[s] = c
    for s, c in mapa.items():
        c.parent = mapa.get(s.parent, s.parent)
        c.matrix_parent_inverse = ax.SX @ s.matrix_parent_inverse @ ax.SX
        c.matrix_basis = ax.SX @ s.matrix_basis @ ax.SX
        # entradas GN que son posiciones en espacio local
        for m in c.modifiers:
            if m.type == "NODES" and m.node_group:
                for it in m.node_group.interface.items_tree:
                    if it.item_type == "SOCKET" and it.in_out == "INPUT" and it.socket_type == "NodeSocketVector" \
                            and any(k in it.name for k in ("Centro", "Posicion")):
                        pi = getattr(m.properties.inputs, it.identifier)
                        v = Vector(pi.value)
                        pi.value = (-v.x, v.y, v.z)
        # drivers: mismas expresiones; variables del capitán → propiedades del FO cuando existen
        if c.animation_data:
            for fc in c.animation_data.drivers:
                for v in fc.driver.variables:
                    for t in v.targets:
                        for k, nuevo in REMAPEO.items():
                            if t.data_path == f'["{k}"]':
                                t.data_path = f'["{nuevo}"]'
    return dst, mapa


lat_fo, mapa_lat = espejar_coleccion(bpy.data.collections["Lateral_Capitan"], "Lateral_Primer_Oficial", "Laterales")
asi_fo, mapa_asi = espejar_coleccion(bpy.data.collections["Asiento_Capitan"], "Asiento_Primer_Oficial", "Asientos")


def fijar_driver(ob, ruta, indice, expr):
    for fc in ob.animation_data.drivers:
        if fc.data_path == ruta and fc.array_index == indice:
            fc.driver.expression = expr
            return
    raise KeyError(f"{ob.name} sin driver {ruta}[{indice}]")


# límites de los sidesticks: ±16° pitch, ±20° roll (driver + restricción)
for piv in (bpy.data.objects["CAB_Sidestick_Pivote"], bpy.data.objects["CAB_Sidestick_Pivote_FO"]):
    fijar_driver(piv, "rotation_euler", 0, "-p * 0.27925")
    fijar_driver(piv, "rotation_euler", 1, "r * 0.34907")
    for c in list(piv.constraints):
        if c.type == "LIMIT_ROTATION":
            piv.constraints.remove(c)
    ax.limitar_rot(piv, x=(-16, 16), y=(-20, 20))

# ------------------------------------------------------------------ 2. viseras recogidas y raíles
col_det = bpy.data.collections["Detalles"]
for lado, s in (("L", -1), ("R", 1)):
    vis = bpy.data.objects[f"CAB_Visera_W1_{lado}"]
    pin = bpy.data.objects[f"CAB_Visera_Pinza_W1_{lado}"]
    bisagra = Vector((s * 0.645, 0.505, 1.552))
    rot = Euler((math.radians(-20.0), 0.0, 0.0))
    # la pinza conserva su posición relativa a la bisagra de la visera
    rel = vis.matrix_basis.inverted() @ pin.matrix_basis
    vis.location = bisagra
    vis.rotation_euler = rot
    pin.matrix_basis = vis.matrix_basis @ rel
    # raíl a lo largo del borde superior del W1
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.86, 0.014, 0.007), (0.0, 0.0, 0.0))
    for x in (-0.40, 0.0, 0.40):   # soportes del raíl
        ax.caja(bm, (0.018, 0.022, 0.018), (x, 0.004, 0.009))
    rail = ax.objeto(f"CAB_Visera_Rail_W1_{lado}", ax.bm_a_malla(f"CAB_Visera_Rail_W1_{lado}", bm), col_det,
                     loc=(s * 0.575, 0.507, 1.566))
    ax.asignar(rail, "MAT_CAB_Metal_Anodizado")
    ax.estilo(rail, bisel=0.0012)

# ------------------------------------------------------------------ 3. compás standby en lo alto del poste central
comp = bpy.data.objects["CAB_Compas"]
comp.location.z += 0.128
# soporte del compás al marco superior
bm = ax.bm_nuevo()
ax.caja(bm, (0.05, 0.03, 0.05), (0, 0.0, 0.0))
sop = ax.objeto("CAB_Compas_Soporte", ax.bm_a_malla("CAB_Compas_Soporte", bm), col_det,
                loc=(comp.location.x, comp.location.y + 0.005, comp.location.z + 0.065))
ax.asignar(sop, "MAT_CAB_Pintura_Gris")
ax.estilo(sop, bisel=0.003, segs=3)

# ------------------------------------------------------------------ 4. parabrisas
M = root.matrix_world
piv_l = M @ Vector((-1.022, 1.721, 0.600))
piv_r = M @ Vector((1.022, 1.721, 0.600))
e_lat = (M.to_3x3() @ Vector((1, 0, 0))).normalized()           # mundo: +Y
e_sub = (M.to_3x3() @ Vector((0, -0.767, 0.642))).normalized()  # pendiente del parabrisas hacia arriba
for n in ("CAB_Vidrio_W1_L", "CAB_Vidrio_W1_R"):
    bpy.data.objects[n]["cab_limpia"] = 1.0

m = ax.material("MAT_CAB_Vidrio_Parabrisas")
n = ax.Nodos(m.node_tree)
geo = n.nodo("ShaderNodeNewGeometry")
P = geo.outputs["Position"]
limpia = n.attr("cab_limpia", "OBJECT")
susp = n.param("Suciedad_Parabrisas")
resis = n.param("Resistencias_Parabrisas")


def barrido(piv, signo):
    d = n.vmat("SUBTRACT", P, tuple(piv))
    u = n.vmat("DOT_PRODUCT", d, tuple(e_lat * -signo))   # hacia el interior (escobilla aparcada)
    v = n.vmat("DOT_PRODUCT", d, tuple(e_sub))
    r = n.vmat("LENGTH", d)
    ang = n.nodo("ShaderNodeMath", operation="ARCTAN2")
    n.con(ang.inputs[0], v); n.con(ang.inputs[1], u)
    ang = ang.outputs[0]
    m_r = n.mat("MULTIPLY", n.suave(r, 0.20, 0.235), n.mat("SUBTRACT", 1.0, n.suave(r, 0.82, 0.855)))
    m_a = n.mat("MULTIPLY", n.suave(ang, -0.06, 0.02), n.mat("SUBTRACT", 1.0, n.suave(ang, 1.42, 1.52)))
    lado = n.suave(n.mat("MULTIPLY", n.sep(P)[1], signo), 0.0, 0.05)
    return n.mat("MULTIPLY", n.mat("MULTIPLY", m_r, m_a), lado), r


bl, rl = barrido(piv_l, -1)
br, rr = barrido(piv_r, 1)
barr = n.mat("MULTIPLY", n.mat("MAXIMUM", bl, br), limpia)
r_arco = n.mezcla(n.suave(n.sep(P)[1], -0.01, 0.01), rl, rr, tipo="FLOAT")
# suciedad: velo de baja frecuencia + motas; el barrido la reduce al 15 %
velo = n.mat("MULTIPLY", n.suave(n.ruido(P, 9.0, 5.0, 0.55), 0.48, 0.80), 0.35)
motas = n.suave(n.ruido(P, 420.0, 1.0, 0.5), 0.70, 0.84)
insectos = n.mat("MULTIPLY", n.suave(n.voronoi(P, 7.0, salida="Distance"), 0.035, 0.0),
                 n.mat("GREATER_THAN", n.sep(n.voronoi(P, 7.0, salida="Color"))[0], 0.86))
sucio = n.mat("ADD", n.mat("MULTIPLY", velo, 0.7), n.mat("MULTIPLY", motas, 0.25))
sucio = n.mat("ADD", sucio, n.mat("MULTIPLY", insectos, 0.8))
sucio = n.mat("MULTIPLY", sucio, n.mat("SUBTRACT", 1.0, n.mat("MULTIPLY", barr, 0.85)))
sucio = n.mat("MULTIPLY", sucio, susp)
# arcos finos dentro del barrido (micro-rayado del caucho)
arcos = n.mat("MULTIPLY", n.suave(n.mat("SINE", n.mat("MULTIPLY", r_arco, 2400.0)), 0.92, 1.0),
              n.suave(n.ruido(n.comb(n.mat("MULTIPLY", r_arco, 30.0), 0.0, 0.0), 6.0), 0.45, 0.7))
arcos = n.mat("MULTIPLY", n.mat("MULTIPLY", arcos, barr), susp)
# película calefactora: tinte dorado en reflexión según el driver
peso = n.nodo("ShaderNodeLayerWeight")
peso.inputs["Blend"].default_value = 0.4
tinte_ref = n.mezcla(n.mat("MULTIPLY", resis, 0.7), (1.0, 1.0, 1.0, 1), (1.0, 0.80, 0.48, 1))
rough = n.mat("ADD", 0.015, n.mat("ADD", n.mat("MULTIPLY", sucio, 0.22), n.mat("MULTIPLY", arcos, 0.10)))
fres = n.nodo("ShaderNodeFresnel")
fres.inputs["IOR"].default_value = 1.52
glossy = n.nodo("ShaderNodeBsdfGlossy")
n.con(glossy.inputs["Color"], tinte_ref)
n.con(glossy.inputs["Roughness"], rough)
transp = n.nodo("ShaderNodeBsdfTransparent")
tinte_tr = n.mezcla(n.mat("MULTIPLY", resis, 0.5), (0.955, 0.975, 0.965, 1), (0.93, 0.92, 0.84, 1))
tinte_tr = n.mezcla(n.mat("MULTIPLY", sucio, 0.18), tinte_tr, (0.86, 0.85, 0.80, 1))
n.con(transp.inputs["Color"], tinte_tr)
difuso = n.nodo("ShaderNodeBsdfDiffuse")
difuso.inputs["Color"].default_value = (0.55, 0.52, 0.46, 1)
s1 = n.nodo("ShaderNodeMixShader")
n.con(s1.inputs[0], fres.outputs[0]); n.con(s1.inputs[1], transp.outputs[0]); n.con(s1.inputs[2], glossy.outputs[0])
s2 = n.nodo("ShaderNodeMixShader")       # la suciedad densa dispersa algo de luz
n.con(s2.inputs[0], n.mat("MULTIPLY", sucio, 0.035)); n.con(s2.inputs[1], s1.outputs[0]); n.con(s2.inputs[2], difuso.outputs[0])
ax.salida_material(n, s2.outputs[0])
m.blend_method = "HASHED" if hasattr(m, "blend_method") else None

ax.informe(fo_lateral=len(mapa_lat), fo_asiento=len(mapa_asi))
ax.guardar(a.salida)
