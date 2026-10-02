"""F03 — Panel principal y glareshield (ampliar lo existente).

- Pantallas (PFD, ND, ECAM sup/inf, ISIS): tornillería perimetral, sensor de luz ambiente,
  ranuras de ventilación y cristal con tratamiento antirreflejo; píxel visible en macro.
- Paneles laterales: ATT HDG, AIR DATA, EIS DMC, PFD/ND XFR, TERR ON ND, GPWS G/S
  (LOUD SPEAKER y CONSOLE/FLOOR LT ya existen).
- Panel central: A/SKID & N/W STRG, AUTO BRK LO/MED/MAX con DECEL/ON, agujas del indicador
  triple de frenos y acumulador, indicador de tren (UNLK rojo / flecha verde por pata).
- Glareshield: tapizado de cuero con grano, flood lights bajo el borde; FCU con collarín y
  tracción push/pull visible (driver FCU_*_Gestionada).
- Panel de rodillas: clips de checklist, bandeja deslizante y portamapas.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix
import axlib as ax
import panel_lib as pl
from panel_lib import Panel

a = ax.iniciar("F03")
COL_P = bpy.data.collections["Panel_Principal"]
COL_G = bpy.data.collections["Glareshield"]
COL_PED = bpy.data.collections["Pedestal"]
dg = bpy.context.evaluated_depsgraph_get()


def bb_local(ob, espacio):
    oe = ob.evaluated_get(dg)
    me = oe.to_mesh()
    M = espacio.matrix_world.inverted() @ ob.matrix_world
    pts = [M @ v.co for v in me.vertices]
    oe.to_mesh_clear()
    return Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])


# ------------------------------------------------------------------ material: cristal antirreflejo
m = ax.material("MAT_CAB_Cristal_AR")
n = ax.Nodos(m.node_tree)
lw = n.nodo("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.08
tinte = n.mezcla(lw.outputs["Facing"], (0.55, 0.45, 0.85, 1), (0.75, 0.95, 0.80, 1))   # reflejo violeta-verdoso del AR
huellas = n.suave(n.ruido(n.nodo("ShaderNodeTexCoord").outputs["Object"], 90.0, 3.0, 0.6), 0.6, 0.85)
gl = n.nodo("ShaderNodeBsdfGlossy")
n.con(gl.inputs["Color"], tinte)
n.con(gl.inputs["Roughness"], n.mat("ADD", 0.04, n.mat("MULTIPLY", huellas, n.mat("MULTIPLY", n.param("Suciedad"), 0.12))))
tr = n.nodo("ShaderNodeBsdfTransparent")
fr = n.nodo("ShaderNodeFresnel"); fr.inputs["IOR"].default_value = 1.12   # reflectancia baja (≈0,3 % frontal)
mx = n.nodo("ShaderNodeMixShader")
n.con(mx.inputs[0], fr.outputs[0]); n.con(mx.inputs[1], tr.outputs[0]); n.con(mx.inputs[2], gl.outputs[0])
ax.salida_material(n, mx.outputs[0])

# ------------------------------------------------------------------ 1. pantallas
PANTALLAS = [("CAB_Pantalla_PFD_L", "CAB_Panel_DU_L"), ("CAB_Pantalla_ND_L", "CAB_Panel_DU_L"),
             ("CAB_Pantalla_PFD_R", "CAB_Panel_DU_R"), ("CAB_Pantalla_ND_R", "CAB_Panel_DU_R"),
             ("CAB_Pantalla_ECAM_Sup", "CAB_Panel_Central"), ("CAB_Pantalla_ECAM_Inf", "CAB_Pedestal_ECAM")]
for pref, padre_n in PANTALLAS:
    padre = bpy.data.objects[padre_n]
    col = COL_P if padre_n != "CAB_Pedestal_ECAM" else COL_PED
    lmin, lmax = bb_local(bpy.data.objects[pref + "_LCD"], padre)
    bmin, bmax = bb_local(bpy.data.objects[pref + "_Bisel"], padre)
    zt = bmax.z
    cx, cy = (lmin.x + lmax.x) / 2, (lmin.y + lmax.y) / 2
    # cristal AR entre el LCD y el borde del bisel
    bm = ax.bm_nuevo()
    ax.caja(bm, (lmax.x - lmin.x + 0.004, lmax.y - lmin.y + 0.004, 0.0008), (cx, cy, lmin.z + 0.0011))
    ob = ax.objeto(pref + "_Cristal", ax.bm_a_malla(pref + "_Cristal", bm, suave=False), col, padre)
    ax.asignar(ob, "MAT_CAB_Cristal_AR")
    # tornillería perimetral (8 tornillos de cabeza plana)
    ins = 0.0055
    pts = [(bmin.x + ins, bmax.y - ins), (bmax.x - ins, bmax.y - ins), (bmin.x + ins, bmin.y + ins), (bmax.x - ins, bmin.y + ins),
           (cx, bmax.y - ins), (bmin.x + ins, cy), (bmax.x - ins, cy), (cx - 0.05, bmax.y - ins)]
    tor = ax.puntos(pref + "_Tornillos_Perimetro", [(x, y, zt - 0.0002) for x, y in pts], col, padre,
                    atributos={"cab_giro": ("FLOAT", [i * 0.71 for i in range(len(pts))])})
    ax.gn(tor, "GN_CAB_Instancias_Puntos", Objeto="CAB_Fuente_Tornillo_Plano", Escala=0.85, Giro_Aleatorio=6.28, Semilla=len(pref))
    # sensor de luz ambiente (lente negra con aro)
    bm = ax.bm_nuevo()
    ax.cilindro(bm, 0.0032, 0.0012, 24, (0, 0, 0.0006), mat=0)
    ax.esfera(bm, 0.0024, (0, 0, 0.0008), 16, 8, mat=1, escala=(1, 1, 0.45))
    sen = ax.objeto(pref + "_Sensor_Luz", ax.bm_a_malla(pref + "_Sensor_Luz", bm), col, padre,
                    (bmax.x - 0.016, bmax.y - 0.0075, zt - 0.0002))
    ax.asignar(sen, "MAT_CAB_Metal_Anodizado", "MAT_CAB_Lente_Humo")
    ax.estilo(sen, bisel=0.0002, atributos=False)
    # ranuras de ventilación en el borde superior del bisel
    bm = ax.bm_nuevo()
    for i in range(14):
        x = cx - 0.065 + i * 0.010
        ax.prisma(bm, ax.rect_redondeado(0.0055, 0.0018, 0.0009, 3, x, bmax.y - 0.0075), zt - 0.0012, zt + 0.00005)
    ran = ax.objeto(pref + "_Ventilacion", ax.bm_a_malla(pref + "_Ventilacion", bm), col, padre)
    ax.asignar(ran, "MAT_CAB_Negro_Profundo")
    # píxel visible en macro: densidad de píxel real de una DU de 7,25" (≈ 768 px)
    for s in bpy.data.objects[pref + "_LCD"].material_slots:
        if s.material:
            for nd in s.material.node_tree.nodes:
                if nd.type == "GROUP" and nd.node_tree and nd.node_tree.name == "NG_CAB_LCD":
                    nd.inputs["Pixeles"].default_value = 768.0
                    nd.inputs["Distancia_Subpixel"].default_value = 0.33

# ISIS: cristal y tornillos
padre = bpy.data.objects["CAB_Panel_Central"]
lmin, lmax = bb_local(bpy.data.objects["CAB_ISIS_LCD"], padre)
bm = ax.bm_nuevo()
ax.caja(bm, (lmax.x - lmin.x + 0.003, lmax.y - lmin.y + 0.003, 0.0006), ((lmin.x + lmax.x) / 2, (lmin.y + lmax.y) / 2, lmin.z + 0.0010))
ob = ax.objeto("CAB_ISIS_Cristal", ax.bm_a_malla("CAB_ISIS_Cristal", bm, suave=False), COL_P, padre)
ax.asignar(ob, "MAT_CAB_Cristal_AR")

# ------------------------------------------------------------------ 2. paneles laterales
for lado, s in (("L", -1), ("R", 1)):
    p = Panel(f"LAT_{lado}", COL_P, None, None, None, 0.224, 0.343, prefijo="CAB_PP_", existente=f"CAB_Panel_Exterior_{lado}")
    quien = "CAPT 3" if lado == "L" else "F/O 3"
    xs = (-70, -32, 6) if lado == "L" else (-6, 32, 70)
    for x, nombre in zip(xs, ("ATT HDG", "AIR DATA", "EIS DMC")):
        p.pb(x, 10, nombre, "", quien, "A", "W")
    p.pb(-50 * s * -1 if lado == "R" else -50, -32, "PFD/ND XFR", "", "", "W", "W")
    p.pb(-10 if lado == "L" else 10, -32, "TERR ON ND", "", "ON", "A", "G")
    p.pb(30 if lado == "L" else -30, -32, "GPWS G/S", "", "G/S", "A", "A")
    p.texto(0, -55, "LOUD SPEAKER        CONSOLE/FLOOR LT" if lado == "L" else "CONSOLE/FLOOR LT        LOUD SPEAKER", "mini")
    p.cerrar()

# ------------------------------------------------------------------ 3. panel central
pc = bpy.data.objects["CAB_Panel_Central"]
for n_ in ("CAB_Autobrake_LO", "CAB_Autobrake_MED", "CAB_Autobrake_MAX"):   # sustituidos por pulsadores DECEL/ON
    bpy.data.objects[n_].hide_render = True
    bpy.data.objects[n_].hide_viewport = True
p = Panel("CENTRAL", COL_P, None, None, None, 0.63, 0.363, prefijo="CAB_PP_", existente=pc)
for x, nombre in ((185, "LO"), (215, "MED"), (245, "MAX")):
    ob = p.pb(x, -11.5, "", "DECEL", "ON", "G", "B", id_=f"AUTOBRK_{nombre}")
p.texto(215, 6, "AUTO/BRK")
p.sw(205, -80, "", "ON", "OFF", pos=1, etiqueta=False)
p.texto(205, -62, "A/SKID &", "mini"); p.texto(205, -66, "N/W STRG", "mini")
p.pb(150, -80, "BRK FAN", "HOT", "ON", "A", "B")
p.cerrar()

# agujas del indicador triple de frenos (ACCU arriba, L/R abajo)
esf = bpy.data.objects["CAB_Frenos_Esfera"]
ax.propiedad("Freno_Presion_Acumulador", 3.0, 0.0, 4.0, "Presión del acumulador de frenos (×1000 PSI)")
for nombre, piv, ang0, expr, vars_ in (
        ("ACCU", (0.0, 0.006), 0.0, "-0.9 + p * 0.45", {"p": "Freno_Presion_Acumulador"}),
        ("L", (-0.0075, -0.0075), 0.0, "-0.25 + f * 0.9", {"f": "Freno_Parking"}),
        ("R", (0.0075, -0.0075), 0.0, "0.25 - f * 0.9", {"f": "Freno_Parking"})):
    bm = ax.bm_nuevo()
    v = [bm.verts.new(c) for c in ((-0.0007, 0.0, 0), (0.0007, 0.0, 0), (0.0002, 0.0115, 0), (-0.0002, 0.0115, 0))]
    bm.faces.new(v)
    ax.cilindro(bm, 0.0013, 0.0006, 12, (0, 0, 0.0002))
    ag = ax.objeto(f"CAB_Frenos_Aguja_{nombre}", ax.bm_a_malla(f"CAB_Frenos_Aguja_{nombre}", bm), COL_P, esf,
                   (piv[0], piv[1], 0.0066))
    ax.asignar(ag, "MAT_CAB_Plastico_Blanco")
    ax.driver(ag, "rotation_euler", expr, vars_, indice=2)
ax.rotulos("CAB_Frenos_Escala_Txt", [((0.0, 0.0150, 0.0064), "ACCU PRESS"), ((0.0, -0.0145, 0.0064), "BRAKES"),
                                      ((-0.0115, -0.0035, 0.0064), "L"), ((0.0115, -0.0035, 0.0064), "R"),
                                      ((-0.0090, 0.0085, 0.0064), "0"), ((0.0, 0.0105, 0.0064), "2"), ((0.0090, 0.0085, 0.0064), "4"),
                                      ((0.0, -0.0045, 0.0064), "PSI x1000")], 0.0018, "MAT_CAB_Etiqueta", COL_P, esf)

# indicador del tren: tres celdas (L / NOSE / R) con UNLK rojo y flecha verde
def mat_estado(nombre, color, k=8.0):
    m = ax.material(nombre)
    n = ax.Nodos(m.node_tree)
    est = n.attr("cab_estado", "OBJECT")
    em = n.mat("MULTIPLY", n.mat("MAXIMUM", est, n.param("Prueba_Anunciadores")), n.mat("MULTIPLY_ADD", n.param("Intensidad_Integral"), 4.0, k))
    sh = ax.principled(n, base=n.mezcla(est, (0.05, 0.05, 0.05, 1), color), rough=0.35, emision=color, fuerza_em=em)
    ax.salida_material(n, sh)
    return m


mat_estado("MAT_CAB_Indicador_Verde", (0.15, 1.0, 0.3, 1))
mat_estado("MAT_CAB_Indicador_Rojo", (1.0, 0.08, 0.04, 1))
tren_panel = Panel("TREN_IND", COL_P, pc, (0.135, 0.120, 0.0), (0, 0, 0), 0.088, 0.034, grosor=0.004, prefijo="CAB_PP_",
                   material="MAT_CAB_Panel", dzus=False)
tren_panel.texto(0, 21, "LDG GEAR", "mini")
for i, pata in enumerate(("L", "NOSE", "R")):
    x = (-0.028 + i * 0.028)
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.022, 0.026, 0.0016), (x, 0, 0.0008))
    cel = ax.objeto(f"CAB_Tren_Celda_{pata}", ax.bm_a_malla(f"CAB_Tren_Celda_{pata}", bm), COL_P, tren_panel.placa)
    ax.asignar(cel, "MAT_CAB_Negro_Profundo"); ax.estilo(cel, bisel=0.0004, atributos=False)
    bm = ax.bm_nuevo()
    v = [bm.verts.new(c) for c in ((x - 0.0072, -0.0012, 0.00175), (x + 0.0072, -0.0012, 0.00175), (x, -0.0100, 0.00175))]
    bm.faces.new(v)
    fl = ax.objeto(f"CAB_Tren_Flecha_{pata}", ax.bm_a_malla("flecha", bm, suave=False), COL_P, tren_panel.placa)
    ax.asignar(fl, "MAT_CAB_Indicador_Verde")
    fl["cab_estado"] = 1.0
    ax.driver(fl, '["cab_estado"]', "min(max((t - 0.98) * 100, 0), 1)", {"t": "Tren"})
    un = ax.rotulos(f"CAB_Tren_UNLK_{pata}", [((x, 0.0062, 0.00175), "UNLK")], 0.0042, "MAT_CAB_Indicador_Rojo", COL_P, tren_panel.placa)
    un["cab_estado"] = 0.0
    ax.driver(un, '["cab_estado"]', "min(max(min(t, 1 - t) * 60, 0), 1)", {"t": "Tren"})
tren_panel.texto(-28, -19, "L", "mini"); tren_panel.texto(0, -19, "NOSE", "mini"); tren_panel.texto(28, -19, "R", "mini")
tren_panel.cerrar()

# ------------------------------------------------------------------ 4. FCU: collarines y tracción push/pull
for k, desc in (("SPD", "velocidad"), ("HDG", "rumbo"), ("ALT", "altitud"), ("VS", "V/S")):
    ax.propiedad(f"FCU_{k}_Gestionada", 1.0 if k in ("SPD", "ALT") else 0.0, 0.0, 1.0,
                 f"FCU {desc}: 1 = gestionada (mando pulsado, guiones y punto) · 0 = seleccionada (mando tirado)")
fcu = bpy.data.objects["CAB_FCU"]
for k in ("SPD", "HDG", "ALT", "VS"):
    kn = bpy.data.objects[f"CAB_FCU_Knob_{k}"]
    bm = ax.bm_nuevo()
    r = bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=0.0185, radius2=0.0172, depth=0.0028)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 0.0014))
    ax.cilindro(bm, 0.0045, 0.006, 24, (0, 0, 0.003), mat=1)                 # eje visible al tirar
    col = ax.objeto(f"CAB_FCU_Collarin_{k}", ax.bm_a_malla(f"CAB_FCU_Collarin_{k}", bm), COL_G, fcu, kn.location.copy())
    ax.asignar(col, "MAT_CAB_Plastico_Mate", "MAT_CAB_Metal_Cepillado")
    ax.estilo(col, bisel=0.0005, atributos=True)
    kn.location.z = 0.0
    ax.driver(kn, "location", "0.0028 + (1 - g) * 0.0032", {"g": f"FCU_{k}_Gestionada"}, indice=2)
# moleteado más marcado en los mandos del FCU y EFIS
for f in ("CAB_Fuente_Knob_FCU", "CAB_Fuente_Knob_FCU_P", "CAB_Fuente_Knob_EFIS"):
    for mdf in bpy.data.objects[f].modifiers:
        if mdf.type == "NODES" and mdf.node_group.name == "GN_CAB_Moleteado":
            ax.gn_set(mdf, "Dientes", 60.0)
            ax.gn_set(mdf, "Profundidad", 0.00048)

# ------------------------------------------------------------------ 5. glareshield: cuero y flood lights
m = ax.material("MAT_CAB_Glareshield")
n = ax.Nodos(m.node_tree)
tc = n.nodo("ShaderNodeTexCoord").outputs["Object"]
grano = n.voronoi(tc, 1400.0, "F1", "Distance", 0.9)
grano2 = n.ruido(tc, 380.0, 3.0, 0.6)
arr = n.mat("ADD", n.mat("MULTIPLY", n.suave(grano, 0.0, 0.42), 0.6), n.mat("MULTIPLY", grano2, 0.4))
uso = n.attr("cab_curvatura")
desg = n.grupo("NG_CAB_Desgaste_Bordes", uso, n.mat("MULTIPLY", n.param("Desgaste"), 0.35), 6.0, 18.0, 3.0, tc).outputs[0]
base = n.mezcla(n.ruido(tc, 6.0, 2.0), (0.030, 0.034, 0.042, 1), (0.036, 0.040, 0.050, 1))
base = n.mezcla(n.mat("MULTIPLY", desg, 0.6), base, (0.075, 0.078, 0.085, 1))
bump = n.nodo("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.35
bump.inputs["Distance"].default_value = 0.0004
n.con(bump.inputs["Height"], arr)
sh = ax.principled(n, base=base, rough=n.mat("ADD", 0.62, n.mat("MULTIPLY", grano2, 0.12)), normal=bump.outputs[0],
                   coat=0.15, coat_rough=0.45)
ax.salida_material(n, sh)

m = ax.material("MAT_CAB_Flood_Lente")
n = ax.Nodos(m.node_tree)
fz = n.mat("MULTIPLY", n.mat("ADD", n.param("Intensidad_Flood"), n.mat("MULTIPLY", n.param("Modo_Cabina"), 0.6)), 6.0)
sh = ax.principled(n, base=(0.8, 0.78, 0.72, 1), rough=0.3, emision=(1.0, 0.82, 0.62, 1), fuerza_em=fz)
ax.salida_material(n, sh)
for nombre, x, w in (("L", -0.55, 0.36), ("C", 0.0, 0.42), ("R", 0.55, 0.36)):
    bm = ax.bm_nuevo()      # lente enrasada en la cara inferior del glareshield (no tapa las pantallas)
    ax.caja(bm, (w, 0.020, 0.0016), (0, 0, 0), mat=0)
    ax.caja(bm, (w - 0.012, 0.011, 0.0006), (0, 0.0, -0.0009), mat=1)
    ob = ax.objeto(f"CAB_Glareshield_Flood_{nombre}", ax.bm_a_malla("flood", bm), COL_G, "CAB_Root", (x, 0.689, 0.7311))
    ax.asignar(ob, "MAT_CAB_Plastico_Mate", "MAT_CAB_Flood_Lente")
    ax.estilo(ob, bisel=0.0005, segs=2)

# ------------------------------------------------------------------ 6. panel de rodillas
m = ax.material("MAT_CAB_Tinta")
n = ax.Nodos(m.node_tree)
ax.salida_material(n, ax.principled(n, base=(0.012, 0.012, 0.014, 1), rough=0.6))
COL_D = bpy.data.collections["Detalles"]
ax.propiedad("Bandeja_Rodillas", 0.0, 0.0, 1.0, "Bandeja deslizante del panel de rodillas: 0 recogida · 1 extendida")
for lado, s in (("L", -1), ("R", 1)):
    # clips de checklist con tarjeta
    for dx in (-0.05, 0.05):
        bm = ax.bm_nuevo()
        ax.caja(bm, (0.022, 0.006, 0.030), (0, 0, 0))
        ax.cilindro(bm, 0.0035, 0.022, 16, (0, -0.002, 0.012), eje="X")
        cl = ax.objeto(f"CAB_Rodillera_Clip_{lado}_{'a' if dx < 0 else 'b'}", ax.bm_a_malla("clip", bm), COL_D, "CAB_Root",
                       (s * 0.55 + dx, 0.659, 0.392))
        ax.asignar(cl, "MAT_CAB_Cromo"); ax.estilo(cl, bisel=0.0006)
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.15, 0.0012, 0.11), (0, 0, 0))
    card = ax.objeto(f"CAB_Rodillera_Checklist_{lado}", ax.bm_a_malla("card", bm), COL_D, "CAB_Root", (s * 0.55, 0.6555, 0.345))
    ax.asignar(card, "MAT_CAB_Papel"); ax.estilo(card, bisel=0.0004, atributos=False)
    ax.rotulos(f"CAB_Rodillera_Checklist_Txt_{lado}",
               [((0, -0.0007, 0.045), "NORMAL CHECKLIST"), ((0, -0.0007, 0.030), "BEFORE START"),
                ((0, -0.0007, 0.020), "AFTER START"), ((0, -0.0007, 0.010), "BEFORE TAKEOFF"),
                ((0, -0.0007, 0.000), "AFTER TAKEOFF"), ((0, -0.0007, -0.010), "APPROACH"),
                ((0, -0.0007, -0.020), "LANDING"), ((0, -0.0007, -0.030), "PARKING")],
               0.0055, "MAT_CAB_Tinta", COL_D, card, rot=(math.radians(90), 0, 0))
    # bandeja deslizante bajo el panel de rodillas
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.32, 0.20, 0.008), (0, -0.10, 0))
    ax.caja(bm, (0.32, 0.012, 0.022), (0, -0.006, 0.007))
    for xx in (-0.16, 0.16):
        ax.caja(bm, (0.006, 0.2, 0.014), (xx, -0.10, 0.006))
    band = ax.objeto(f"CAB_Rodillera_Bandeja_{lado}", ax.bm_a_malla("bandeja", bm), COL_D, "CAB_Root", (s * 0.42, 0.858, 0.33))
    ax.asignar(band, "MAT_CAB_Plastico_Gris"); ax.estilo(band, bisel=0.002)
    ax.driver(band, "location", "0.858 - b * 0.19", {"b": "Bandeja_Rodillas"}, indice=1)
    ax.limitar_loc(band, y=(0.858 - 0.19, 0.858))
    # portamapas (bolsillo) en el extremo exterior
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.16, 0.02, 0.12), (0, 0, 0))
    pm = ax.objeto(f"CAB_Rodillera_Portamapas_{lado}", ax.bm_a_malla("portamapas", bm), COL_D, "CAB_Root", (s * 0.86, 0.648, 0.30))
    ax.asignar(pm, "MAT_CAB_Cuero"); ax.estilo(pm, bisel=0.006, segs=3, subsurf=1)
    gn = ax.gn(pm, "GN_CAB_Arrugas", Fuerza=0.002, Escala=14.0, Semilla=float(s + 3))

ax.informe(ok=True)
ax.guardar(a.salida)
