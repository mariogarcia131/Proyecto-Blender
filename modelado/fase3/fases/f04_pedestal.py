"""F04 — Pedestal.

- ECAM Control Panel completo entre los MCDU (los MCDU se separan hacia los bordes).
- Sección trasera nueva del pedestal: MCDU 3 (centro); SWITCHING, RMP 3 e impresora (izquierda);
  iluminación (FLOOD LT MAIN PNL & PED, INTEG LT, LOUDSPEAKER), ACP 3 y manivela de extensión del
  tren por gravedad con su tapa (derecha).
- Laterales: tornillería, bandas de goma, mazos de cables y placards de datos.
- Refinado: gatillo del speedbrake.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix
import axlib as ax
from panel_lib import Panel

a = ax.iniciar("F04")
COL = bpy.data.collections["Pedestal"]
ROT_MCDU = (0.139, 0.0, 0.0)


def duplicar(raiz, sufijo, loc=None):
    """Copia una jerarquía (malla enlazada) con nombres «<nombre><sufijo>»."""
    fuentes = [raiz] + list(raiz.children_recursive)
    mapa = {}
    for s in fuentes:
        c = s.copy()
        c.name = s.name + sufijo
        ax.marcar(c)
        for cc in list(c.users_collection):
            cc.objects.unlink(c)
        (s.users_collection[0] if s.users_collection else COL).objects.link(c)
        mapa[s] = c
    for s, c in mapa.items():
        c.parent = mapa.get(s.parent, s.parent)
        c.matrix_parent_inverse = s.matrix_parent_inverse.copy()
        c.matrix_basis = s.matrix_basis.copy()
        for m in c.modifiers:
            if m.type == "BOOLEAN" and m.object in mapa:
                m.object = mapa[m.object]
    if loc is not None:
        mapa[raiz].location = loc
    return mapa[raiz]


# ------------------------------------------------------------------ 1. MCDU separados y ECP en el centro
for lado, s in (("L", -1), ("R", 1)):
    bpy.data.objects[f"CAB_MCDU_{lado}"].location.x = s * 0.1765
ecp = Panel("ECP", COL, "CAB_Root", (0.0, 0.452, 0.350), ROT_MCDU, 0.198, 0.252, prefijo="CAB_PED_", semilla=31)
ecp.titulo(0, 116, "ECAM CONTROL", ancho_linea=170)
ecp.knob(-55, 95, "UPPER DISPLAY", "OFF", "BRT", valor=0.7, arco=240, marcas=9, radio=11, etiqueta_y=-14)
ecp.knob(55, 95, "LOWER DISPLAY", "OFF", "BRT", valor=0.7, arco=240, marcas=9, radio=11, etiqueta_y=-14)
teclas = [("TO CONFIG", -55, 58, False), ("EMER CANC", 55, 58, False),
          ("ENG", -62, 28, True), ("BLEED", 0, 28, False), ("PRESS", 62, 28, False),
          ("ELEC", -62, 4, False), ("HYD", 0, 4, False), ("FUEL", 62, 4, False),
          ("APU", -62, -20, False), ("COND", 0, -20, False), ("DOOR", 62, -20, False),
          ("WHEEL", -62, -44, False), ("F/CTL", 0, -44, False), ("ALL", 62, -44, False),
          ("CLR", -62, -78, False), ("STS", 0, -78, False), ("RCL", 62, -78, False)]
led_on, led_off = [], []
for nombre, x, y, sel in teclas:
    ecp.instancia("CAB_Fuente_Tecla_FCU", x, y, escala=1.15 if nombre not in ("TO CONFIG", "EMER CANC") else 1.0)
    ecp.texto(x, y - 1.2, nombre, "mini" if len(nombre) > 4 else "peq", z=0.0071 if nombre not in ("TO CONFIG", "EMER CANC") else 0.0062)
    if nombre not in ("TO CONFIG", "EMER CANC", "ALL", "RCL"):
        (led_on if sel else led_off).append((x, y + 5.0))
ecp.linea([(-90, -62), (90, -62)], 0.5)
for lista, est, suf in ((led_on, 1.0, "On"), (led_off, 0.0, "Off")):
    if not lista:
        continue
    bm = ax.bm_nuevo()
    for x, y in lista:
        ax.caja(bm, (0.012, 0.0016, 0.0006), (x / 1000, y / 1000, 0.0072))
    ob = ax.objeto(f"CAB_PED_ECP_LED_{suf}", ax.bm_a_malla("led", bm, suave=False), COL, ecp.placa)
    ax.asignar(ob, "MAT_CAB_Indicador_Verde")
    ob["cab_estado"] = est
ecp.cerrar()

# ------------------------------------------------------------------ 2. sección trasera del pedestal
Y0, Y1 = -0.500, -0.835
bm = ax.bm_nuevo()
ax.caja(bm, (0.50, Y0 - Y1, 0.309), (0, (Y0 + Y1) / 2, 0.309 / 2))
cuerpo = ax.objeto("CAB_Pedestal_Cuerpo_Trasero", ax.bm_a_malla("ped_tras", bm), COL, "CAB_Root")
ax.asignar(cuerpo, bpy.data.objects["CAB_Pedestal_Cuerpo"].active_material)
ax.estilo(cuerpo, bisel=0.004, segs=3)
bm = ax.bm_nuevo()
ax.caja(bm, (0.51, Y0 - Y1, 0.06), (0, (Y0 + Y1) / 2, 0.03))
zoc = ax.objeto("CAB_Pedestal_Zocalo_Trasero", ax.bm_a_malla("zoc_tras", bm), COL, "CAB_Root")
ax.asignar(zoc, bpy.data.objects["CAB_Pedestal_Zocalo"].active_material)
ax.estilo(zoc, bisel=0.003)

mcdu3 = duplicar(bpy.data.objects["CAB_MCDU_L"], "_3", (0.0, -0.668, 0.309 + 0.016))
mcdu3.rotation_euler = (0.0, 0.0, 0.0)
rmp3 = duplicar(bpy.data.objects["CAB_Pedestal_RMP_1"], "_3", (-0.163, -0.660, 0.317))
acp3 = duplicar(bpy.data.objects["CAB_Pedestal_ACP_1"], "_3", (0.163, -0.660, 0.317))

sw = Panel("SWITCHING", COL, "CAB_Root", (-0.163, -0.556, 0.317), (0, 0, 0), 0.145, 0.10, prefijo="CAB_PED_", semilla=41)
sw.titulo(0, 42, "SWITCHING", ancho_linea=125)
for (x, y, nombre, pos) in ((-40, 12, "ATT HDG", ["CAPT 3", "NORM", "F/O 3"]), (40, 12, "AIR DATA", ["CAPT 3", "NORM", "F/O 3"]),
                            (-40, -26, "EIS DMC", ["CAPT 3", "NORM", "F/O 3"]), (40, -26, "ECAM/ND XFR", ["CAPT", "NORM", "F/O"])):
    sw.rot(x, y, nombre, pos, indice=1, arco=100, radio=14.0, etiqueta_y=-15.5)
sw.cerrar()

lt = Panel("LIGHTING", COL, "CAB_Root", (0.163, -0.556, 0.317), (0, 0, 0), 0.145, 0.10, prefijo="CAB_PED_", semilla=43)
lt.titulo(0, 42, "LIGHTING", ancho_linea=125)
lt.knob(-45, 4, "FLOOD LT", "OFF", "BRT", valor=0.3, arco=240, marcas=9, radio=11.0, etiqueta_y=-16)
lt.texto(-45, -24, "MAIN PNL & PED", "mini")
lt.knob(0, 4, "INTEG LT", "OFF", "BRT", valor=0.55, arco=240, marcas=9, radio=11.0, etiqueta_y=-16)
lt.knob(45, 4, "LOUDSPEAKER", "OFF", "MAX", valor=0.4, arco=240, marcas=9, radio=11.0, etiqueta_y=-16)
lt.cerrar()

# impresora con ranura y papel
imp = Panel("PRINTER", COL, "CAB_Root", (-0.163, -0.775, 0.317), (0, 0, 0), 0.145, 0.105, prefijo="CAB_PED_", semilla=47)
imp.titulo(0, 44, "PRINTER", ancho_linea=125)
imp.pb(-40, -30, "FEED", "", "", "W", "W")
imp.pb(0, -30, "TEST", "", "", "W", "W")
imp.luz(40, -30, "PAPER OUT", "A")
imp.cerrar()
bm = ax.bm_nuevo()
ax.caja(bm, (0.120, 0.034, 0.014), (0, 0, 0.007), mat=0)
ax.caja(bm, (0.104, 0.0035, 0.004), (0, 0.004, 0.0142), mat=1)      # ranura
ob = ax.objeto("CAB_PED_PRINTER_Carcasa", ax.bm_a_malla("imp", bm), COL, imp.placa, (0, 0.012, 0))
ax.asignar(ob, "MAT_CAB_Plastico_Mate", "MAT_CAB_Negro_Profundo"); ax.estilo(ob, bisel=0.0015)
bm = ax.bm_nuevo()            # papel curvado saliendo de la ranura
seg = 14
prev = None
for i in range(seg + 1):
    t = i / seg
    y = 0.004 - 0.07 * t
    z = 0.0145 + 0.03 * math.sin(t * math.pi * 0.5) - 0.012 * t * t
    a_ = bm.verts.new((-0.048, y, z)); b_ = bm.verts.new((0.048, y, z))
    if prev:
        bm.faces.new((prev[0], prev[1], b_, a_))
    prev = (a_, b_)
ob = ax.objeto("CAB_PED_PRINTER_Papel", ax.bm_a_malla("papel", bm), COL, imp.placa, (0, 0.012, 0))
ax.asignar(ob, "MAT_CAB_Papel")
ob.modifiers.new("Solid", "SOLIDIFY").thickness = 0.0002
ax.rotulos("CAB_PED_PRINTER_Texto", [((0, -0.030, 0.035), "ACARS  KONAN  FL350"), ((0, -0.040, 0.033), "WIND 270/045  T-52")],
           0.0026, "MAT_CAB_Tinta", COL, ob, rot=(math.radians(-25), 0, 0))

# manivela de extensión del tren por gravedad con su tapa
gr = Panel("GRAVITY_GEAR", COL, "CAB_Root", (0.163, -0.775, 0.317), (0, 0, 0), 0.145, 0.105, prefijo="CAB_PED_", semilla=53)
gr.titulo(0, 44, "GRAVITY GEAR EXTN", ancho_linea=125)
gr.texto(0, -42, "TURN CLOCKWISE 3 TIMES", "mini")
gr.cerrar()
bm = ax.bm_nuevo()
ax.caja(bm, (0.10, 0.065, 0.010), (0, 0, -0.005), mat=0)               # alojamiento
ob = ax.objeto("CAB_PED_GRAVITY_Alojamiento", ax.bm_a_malla("aloj", bm), COL, gr.placa, (0, -0.002, 0.0002))
ax.asignar(ob, "MAT_CAB_Negro_Profundo")
piv_m = ax.vacio("CAB_PED_GRAVITY_Manivela_Pivote", COL, gr.placa, (0.0, -0.002, -0.004))
bm = ax.bm_nuevo()
ax.cilindro(bm, 0.008, 0.012, 24, (0, 0, 0.002))
ax.caja(bm, (0.050, 0.010, 0.006), (0.024, 0, 0.007))
ax.cilindro(bm, 0.007, 0.022, 20, (0.046, 0, 0.018), mat=1)
man = ax.objeto("CAB_PED_GRAVITY_Manivela", ax.bm_a_malla("manivela", bm), COL, piv_m)
ax.asignar(man, "MAT_CAB_Metal_Anodizado", "MAT_CAB_Rojo_Fuego"); ax.estilo(man, bisel=0.001)
ax.propiedad("Tren_Gravedad_Tapa", 0.35, 0.0, 1.0, "Tapa de la manivela de extensión por gravedad: 0 cerrada · 1 abierta")
ax.propiedad("Tren_Gravedad_Vueltas", 0.0, 0.0, 3.0, "Vueltas de la manivela de extensión por gravedad")
ax.driver(piv_m, "rotation_euler", "-v * 6.28319", {"v": "Tren_Gravedad_Vueltas"}, indice=2)
piv_t = ax.vacio("CAB_PED_GRAVITY_Tapa_Pivote", COL, gr.placa, (0.0, 0.031, 0.0006))
bm = ax.bm_nuevo()
ax.caja(bm, (0.104, 0.068, 0.003), (0, -0.034, 0.0015))
tapa = ax.objeto("CAB_PED_GRAVITY_Tapa", ax.bm_a_malla("tapa", bm), COL, piv_t)
ax.asignar(tapa, "MAT_CAB_Panel"); ax.estilo(tapa, bisel=0.001)
ax.rotulos("CAB_PED_GRAVITY_Tapa_Txt", [((0, -0.026, 0.0032), "GRAVITY GEAR"), ((0, -0.036, 0.0032), "EXTN"),
                                         ((0, -0.050, 0.0032), "LIFT COVER")], 0.0034, "MAT_CAB_Etiqueta", COL, tapa)
ax.driver(piv_t, "rotation_euler", "-t * 1.9", {"t": "Tren_Gravedad_Tapa"}, indice=0)
ax.limitar_rot(piv_t, x=(-110, 0))

# ------------------------------------------------------------------ 3. laterales: tornillos, goma, cables, placards
for s in (-1, 1):
    x = s * 0.2515
    pts = []
    for y in [0.70 - i * 0.05 for i in range(31)]:
        pts.append((x, y, 0.296)); pts.append((x, y, 0.082))
    for z in (0.12, 0.17, 0.22, 0.27):
        pts.append((x, 0.735, z)); pts.append((x, -0.815, z))
    tor = ax.puntos(f"CAB_PED_Tornillos_{'L' if s < 0 else 'R'}", pts, COL, "CAB_Root",
                    atributos={"cab_normal": ("FLOAT_VECTOR", [(s, 0, 0)] * len(pts))})
    ax.gn(tor, "GN_CAB_Instancias_Puntos", Objeto="CAB_Fuente_Tornillo", Escala=0.8, Giro_Aleatorio=6.28, Semilla=7 + s)
    # banda de goma en la arista superior lateral
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.012, 1.58, 0.016), (0, 0, 0))
    gom = ax.objeto(f"CAB_PED_Goma_{'L' if s < 0 else 'R'}", ax.bm_a_malla("goma", bm), COL, "CAB_Root",
                    (s * 0.2525, -0.045, 0.309))
    ax.asignar(gom, "MAT_CAB_Goma"); ax.estilo(gom, bisel=0.004, segs=3)
    # placards de datos
    for k, (y, z, txt) in enumerate(((0.45, 0.20, "P/N D3214-200-01  S/N 4471"), (-0.62, 0.20, "PEDESTAL AFT  P/N D3214-310"))):
        bm = ax.bm_nuevo()
        ax.caja(bm, (0.0008, 0.075, 0.022), (0, 0, 0))
        pla = ax.objeto(f"CAB_PED_Placard_{'L' if s < 0 else 'R'}_{k}", ax.bm_a_malla("placard", bm), COL, "CAB_Root",
                        (s * 0.2522, y, z))
        ax.asignar(pla, "MAT_CAB_Placard_Plata"); ax.estilo(pla, bisel=0.0004, atributos=False)
        ax.rotulos(f"CAB_PED_Placard_Txt_{'L' if s < 0 else 'R'}_{k}", [((s * 0.0006, 0, 0.004), txt.split("  ")[0]),
                                                                        ((s * 0.0006, 0, -0.004), txt.split("  ")[1])],
                   0.0034, "MAT_CAB_Tinta", COL, pla, rot=(math.radians(90), 0, math.radians(90 * s)))
# mazo de cables en la base del pedestal (lado derecho, hacia el suelo)
cu = bpy.data.curves.new("CAB_PED_Mazo", "CURVE")
cu.dimensions = "3D"; cu.bevel_depth = 0.006; cu.bevel_resolution = 3
sp = cu.splines.new("BEZIER"); sp.bezier_points.add(3)
for p, c in zip(sp.bezier_points, ((0.26, 0.50, 0.08), (0.285, 0.1, 0.03), (0.30, -0.4, 0.015), (0.27, -0.83, 0.03))):
    p.co = c; p.handle_left_type = p.handle_right_type = "AUTO"
mz = ax.objeto("CAB_PED_Mazo_Cables", cu, COL, "CAB_Root")
ax.asignar(mz, "MAT_CAB_Mazo")

# ------------------------------------------------------------------ 4. gatillo del speedbrake
sb = bpy.data.objects.get("CAB_Speedbrake_Mango")
if sb:
    bm = ax.bm_nuevo()
    ax.caja(bm, (0.012, 0.004, 0.018), (0, 0, 0))
    gat = ax.objeto("CAB_Speedbrake_Gatillo", ax.bm_a_malla("gatillo", bm), COL, sb, (0.0, 0.016, -0.004))
    ax.asignar(gat, "MAT_CAB_Plastico_Mate"); ax.estilo(gat, bisel=0.0012)

ax.informe(ok=True)
ax.guardar(a.salida)
