"""F02 — Overhead completo (máxima prioridad visual) y corrección del Design Eye Point.

- Se retira el overhead antiguo (matrices aleatorias, colgado dentro del hueco del parabrisas e
  inclinado al revés). Se conservan las manetas de fuego en T.
- Nuevo overhead delantero (3 columnas, disposición Airbus A330) en un plano que arranca detrás
  del borde superior del parabrisas y sube hacia popa bajo el techo; overhead trasero con paneles
  de breakers. Lectura: popa = arriba del texto (como lo ve el piloto mirando hacia arriba).
"""
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
import axlib as ax
import panel_lib as pl
from panel_lib import Panel

a = ax.iniciar("F02")
random.seed(620)
COL = ax.coleccion("Overhead")

# ------------------------------------------------------------------ 0. retirar el overhead antiguo
manetas = {n: bpy.data.objects[n] for n in ("CAB_Fuego_Maneta_ENG1", "CAB_Fuego_Maneta_APU", "CAB_Fuego_Maneta_ENG2")}
for ob in list(COL.objects):
    if ob.name not in manetas:
        bpy.data.objects.remove(ob, do_unlink=True)
for n in ("CAB_Overhead_Carcasa", "CAB_Overhead_Carenado", "CAB_Overhead_Fondo"):
    if n in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
pl.fuentes_comunes()

# ------------------------------------------------------------------ 1. geometría de los planos
ALFA = math.radians(10.6)     # pendiente del overhead delantero (sube hacia popa)
BETA = math.radians(22.0)     # pendiente del overhead trasero
FRENTE = Vector((0.0, 0.300, 1.665))
dirF = Vector((0.0, -math.cos(ALFA), math.sin(ALFA)))
LF = 0.735
B0 = FRENTE + dirF * (LF + 0.012)
dirA = Vector((0.0, -math.cos(BETA), math.sin(BETA)))
LA = 0.52
ROT_F = (math.pi - ALFA, 0.0, 0.0)
ROT_A = (math.pi - BETA, 0.0, 0.0)


def pos_F(u_mm, v_mm):          # v desde el borde delantero hacia popa
    return FRENTE + Vector((u_mm / 1000.0, 0, 0)) + dirF * (v_mm / 1000.0)


def pos_A(u_mm, v_mm):
    return B0 + Vector((u_mm / 1000.0, 0, 0)) + dirA * (v_mm / 1000.0)


COLUMNAS = {"L": (-310.0, 278.5), "C": (0.0, 338.5), "R": (310.0, 278.5)}
_v = {"L": 0.0, "C": 0.0, "R": 0.0}
_sem = [10]


def panel(nombre, columna, alto, ancho=None, u=None, plano="F"):
    """Coloca el siguiente panel de la columna (de proa a popa) y devuelve el Panel."""
    uc, w = COLUMNAS[columna]
    if u is not None:
        uc = u
    if ancho is not None:
        w = ancho
    v0 = _v[columna]
    if u is None or ancho is None or ancho >= COLUMNAS[columna][1] - 1:
        pass
    centro = (pos_F if plano == "F" else pos_A)(uc, v0 + alto / 2)
    _sem[0] += 7
    p = Panel(nombre, COL, "CAB_Root", centro, ROT_F if plano == "F" else ROT_A, w / 1000.0, (alto - 1.5) / 1000.0,
              semilla=_sem[0])
    return p


def avanzar(columna, alto):
    _v[columna] += alto


def titulo(p, t):
    p.titulo(0, p.h * 500 - 6.0, t, ancho_linea=p.w * 1000 - 24)


# ================================================================== COLUMNA CENTRAL (proa → popa)
# --- fila delantera: APU | SIGNS | INT LT
h = 70
p = panel("APU", "C", h, ancho=111, u=-113.5)
titulo(p, "APU")
p.pb(-25, -5, "MASTER SW", "FAULT", "ON", "A", "B", inf_on=True)
p.pb(25, -5, "START", "ON", "AVAIL", "B", "G", inf_on=True)
p.cerrar()
p = panel("SIGNS", "C", h, ancho=111, u=0.0)
titulo(p, "SIGNS")
p.sw(-32, -6, "SEAT BELTS", "ON", "OFF", pos=1)
p.sw(0, -6, "NO SMOKING", "ON", "OFF", centro="AUTO", pos=0)
p.sw(32, -6, "EMER EXIT LT", "ON", "OFF", centro="ARM", pos=0)
p.cerrar()
p = panel("INT_LT", "C", h, ancho=112, u=113.5)
titulo(p, "INT LT")
p.knob(-30, -4, "OVHD INTEG LT", "OFF", "BRT", valor=0.55, etiqueta_y=-17)
p.sw(8, -4, "ICE IND & STBY COMPASS", "ON", "OFF", pos=-1, etiqueta=False)
p.texto(8, 13.5, "ICE IND &", "mini"); p.texto(8, 10.5, "STBY COMPASS", "mini")
p.sw(38, -4, "DOME", "BRT", "OFF", centro="DIM", pos=0)
p.texto(23, -25, "ANN LT  TEST / BRT / DIM", "mini")
p.cerrar()
avanzar("C", h)

# --- EXT LT
h = 70
p = panel("EXT_LT", "C", h)
titulo(p, "EXT LT")
xs = [-140, -100, -60, -20, 20, 60, 100, 140]
p.sw(xs[0], -6, "STROBE", "ON", "OFF", centro="AUTO", pos=0)
p.sw(xs[1], -6, "BEACON", "ON", "OFF", pos=1)
p.sw(xs[2], -6, "WING", "ON", "OFF", pos=-1)
p.sw(xs[3], -6, "NAV & LOGO", "1", "OFF", centro="2", pos=1)
p.sw(xs[4], -6, "RWY TURN OFF", "ON", "OFF", pos=-1)
p.sw(xs[5], -6, "LAND L", "ON", "RETRACT", centro="OFF", pos=-1)
p.sw(xs[6], -6, "LAND R", "ON", "RETRACT", centro="OFF", pos=-1)
p.rot(xs[7], -6, "NOSE", ["OFF", "TAXI", "T.O"], indice=0, arco=80, etiqueta_y=-18.5)
p.cerrar()
avanzar("C", h)

# --- ANTI ICE | CAB PRESS
h = 76
p = panel("ANTI_ICE", "C", h, ancho=150, u=-94.0)
titulo(p, "ANTI ICE")
p.pb(-48, -4, "WING", "FAULT", "ON", "A", "B")
p.pb(-16, -4, "ENG 1", "FAULT", "ON", "A", "B")
p.pb(16, -4, "ENG 2", "FAULT", "ON", "A", "B")
p.pb(48, -4, "PROBE/WINDOW", "", "ON", "A", "B")
p.texto(48, -20, "HEAT", "mini")
p.cerrar()
p = panel("CAB_PRESS", "C", h, ancho=187, u=75.5)
titulo(p, "CABIN PRESS")
p.knob(-62, -6, "MAN V/S CTL", "UP", "DN", valor=0.5, arco=120, marcas=7)
p.pb(-20, -4, "MODE SEL", "FAULT", "MAN", "A", "W")
p.knob(24, -6, "LDG ELEV", "AUTO", "+14", valor=0.0, arco=300, marcas=15)
p.pb(66, -4, "DITCHING", "", "ON", "A", "W", guarda="roja")
p.cerrar()
avanzar("C", h)

# --- AIR COND / BLEED con sinóptico
h = 102
p = panel("AIR_COND", "C", h)
titulo(p, "AIR COND")
# temperaturas
p.knob(-125, 18, "COCKPIT", "COLD", "HOT", valor=0.5, etiqueta_y=-15.0)
p.knob(-80, 18, "FWD CABIN", "COLD", "HOT", valor=0.55, etiqueta_y=-15.0)
p.knob(-35, 18, "AFT CABIN", "COLD", "HOT", valor=0.5, etiqueta_y=-15.0)
p.pb(10, 20, "HOT AIR", "FAULT", "OFF", "A", "W")
p.rot(55, 20, "PACK FLOW", ["LO", "NORM", "HI"], indice=1, arco=80, etiqueta_y=-15.5)
p.pb(110, 20, "APU BLEED", "FAULT", "ON", "A", "B")
# fila inferior: PACK 1, ENG 1 BLEED, X BLEED, ENG 2 BLEED, PACK 2
p.pb(-125, -28, "PACK 1", "FAULT", "OFF", "A", "W", etiqueta_arriba=False)
p.pb(-70, -28, "ENG 1 BLEED", "FAULT", "OFF", "A", "W", etiqueta_arriba=False)
p.rot(0, -28, "X BLEED", ["SHUT", "AUTO", "OPEN"], indice=1, arco=80, etiqueta_y=-15.5)
p.pb(70, -28, "ENG 2 BLEED", "FAULT", "OFF", "A", "W", etiqueta_arriba=False)
p.pb(125, -28, "PACK 2", "FAULT", "OFF", "A", "W", etiqueta_arriba=False)
# sinóptico: conductos de sangrado
p.linea([(-125, -17), (-125, -8), (-70, -8), (-70, -17)])
p.linea([(-70, -8), (-14, -8)]); p.linea([(14, -8), (70, -8)])
p.linea([(70, -17), (70, -8), (125, -8), (125, -17)])
p.linea([(0, -8), (0, -14)]); p.linea([(110, 9), (110, -8)])
p.cerrar()
avanzar("C", h)

# --- ELEC con sinóptico
h = 132
p = panel("ELEC", "C", h)
titulo(p, "ELEC")
# fila superior (popa): baterías y voltímetro
p.pb(-120, 34, "BAT 1", "FAULT", "OFF", "A", "W", etiqueta_arriba=True)
p.pb(-85, 34, "BAT 2", "FAULT", "OFF", "A", "W")
p.pb(-50, 34, "APU BAT", "FAULT", "OFF", "A", "W")
p.lcd(5, 36, 32, 11, "28.1V", material="MAT_CAB_Texto_Ambar", tam=0.0042)
p.texto(5, 47.5, "BAT")
p.pb(55, 34, "AC ESS FEED", "FAULT", "ALTN", "A", "W")
p.pb(100, 34, "GALY & CAB", "FAULT", "OFF", "A", "W")
p.pb(135, 34, "COMMERCIAL", "", "OFF", "A", "W")
# fila central: IDG y generadores con sinóptico
yG = -6
p.pb(-147, yG, "IDG 1", "FAULT", "", "A", "W", guarda="roja")
p.pb(-110, yG, "GEN 1", "FAULT", "OFF", "A", "W")
p.pb(-55, yG, "APU GEN", "FAULT", "OFF", "A", "W")
p.pb(0, yG, "BUS TIE", "", "OFF", "A", "W")
p.pb(55, yG, "EXT PWR", "AVAIL", "ON", "G", "B", sup_on=True)
p.pb(110, yG, "GEN 2", "FAULT", "OFF", "A", "W")
p.pb(147, yG, "IDG 2", "FAULT", "", "A", "W", guarda="roja")
yB = -36
p.texto(-130, yB - 9, "AC BUS 1"); p.texto(130, yB - 9, "AC BUS 2")
p.linea([(-150, yB), (-14, yB)]); p.linea([(14, yB), (150, yB)])
for x in (-110, -55, 55, 110):
    p.linea([(x, yG - 10), (x, yB)])
p.linea([(-14, yB), (-14, yB + 4)]); p.linea([(14, yB), (14, yB + 4)])
p.linea([(0, yG - 10), (0, yB + 4)], 0.5)
p.linea([(-147, yB), (-150, yB - 6)]); p.linea([(147, yB), (150, yB - 6)])
p.pb(-60, -52, "AC ESS BUS", "", "", "A", "W", etiqueta_arriba=False)
p.cerrar()
avanzar("C", h)

# --- FUEL con sinóptico de depósitos
h = 106
p = panel("FUEL", "C", h)
titulo(p, "FUEL")
p.texto(-120, 30, "L TK PUMPS"); p.texto(0, 30, "CTR TK PUMPS"); p.texto(120, 30, "R TK PUMPS")
for x in (-140, -100):
    p.pb(x, 15, "", "FAULT", "OFF", "A", "W")
p.texto(-140, 2, "1", "mini"); p.texto(-100, 2, "2", "mini")
p.pb(-20, 15, "", "FAULT", "OFF", "A", "W"); p.pb(20, 15, "", "FAULT", "OFF", "A", "W")
p.texto(-20, 2, "L", "mini"); p.texto(20, 2, "R", "mini")
for x in (100, 140):
    p.pb(x, 15, "", "FAULT", "OFF", "A", "W")
p.texto(100, 2, "1", "mini"); p.texto(140, 2, "2", "mini")
p.pb(-60, -30, "X FEED", "", "ON", "A", "W", etiqueta_arriba=False)
p.pb(60, -30, "MODE SEL", "FAULT", "MAN", "A", "W", etiqueta_arriba=False)
p.pb(0, -30, "T TANK MODE", "FAULT", "FWD", "A", "W", etiqueta_arriba=False)
# sinóptico de alimentación cruzada
p.caja_linea(-160, -8, -80, 26, 0.5); p.caja_linea(-40, -8, 40, 26, 0.5); p.caja_linea(80, -8, 160, 26, 0.5)
p.linea([(-120, -8), (-120, -30), (-71, -30)]); p.linea([(-49, -30), (-11, -30)])
p.linea([(11, -30), (49, -30)]); p.linea([(71, -30), (120, -30), (120, -8)])
p.texto(-140, -44, "ENG 1"); p.texto(140, -44, "ENG 2")
p.linea([(-140, -30), (-140, -38)]); p.linea([(140, -30), (140, -38)])
p.cerrar()
avanzar("C", h)

# --- HYD
h = 77
p = panel("HYD", "C", h)
titulo(p, "HYD")
p.texto(-120, 22, "ENG 1 PUMP", "mini"); p.texto(120, 22, "ENG 2 PUMP", "mini")
p.pb(-140, 5, "", "FAULT", "OFF", "A", "W"); p.pb(-105, 5, "", "FAULT", "OFF", "A", "W")
p.pb(105, 5, "", "FAULT", "OFF", "A", "W"); p.pb(140, 5, "", "FAULT", "OFF", "A", "W")
p.texto(-140, -9, "G", "mini"); p.texto(-105, -9, "B", "mini"); p.texto(105, -9, "Y", "mini"); p.texto(140, -9, "G", "mini")
p.pb(-55, 2, "ELEC PUMP", "FAULT", "OFF", "A", "W")
p.pb(-20, 2, "", "FAULT", "ON", "A", "B")
p.pb(20, 2, "PTU", "FAULT", "OFF", "A", "W")
p.pb(55, 2, "RAT MAN ON", "", "", "A", "W", guarda="roja")
p.texto(-37, -22, "BLUE   YELLOW", "mini")
p.cerrar()
avanzar("C", h)

# --- FIRE (manetas en T existentes + AGENT + TEST con guarda transparente)
h = 104
p = panel("FIRE", "C", h)
titulo(p, "FIRE")
for nombre, x, n_ag in (("ENG1", -112, 2), ("APU", 0, 1), ("ENG2", 112, 2)):
    m = manetas[f"CAB_Fuego_Maneta_{nombre}"]
    m.parent = p.placa
    m.matrix_parent_inverse = Matrix.Identity(4)
    m.location = (x / 1000.0, 0.012, 0.0)
    m.rotation_euler = (0, 0, 0)
    ax.rotulos(f"CAB_OH_FIRE_Maneta_{nombre}_Txt",
               [((0, 0.0045, 0.0285), {"ENG1": "ENG 1", "APU": "APU", "ENG2": "ENG 2"}[nombre]),
                ((0, -0.0045, 0.0285), "FIRE")], 0.0042, "MAT_CAB_Etiqueta", COL, m)
    p.texto(x, 40, "PUSH", "mini")
    if n_ag == 2:
        p.pb(x - 22, -32, "AGENT 1", "SQUIB", "DISCH", "W", "A", sup_on=False, etiqueta_arriba=False)
        p.pb(x + 22, -32, "AGENT 2", "SQUIB", "DISCH", "W", "A", etiqueta_arriba=False)
    else:
        p.pb(x - 22, -32, "AGENT", "SQUIB", "DISCH", "W", "A", etiqueta_arriba=False)
    tx = x + 38 if nombre != "APU" else x + 22
    p.pb(tx, 22 if nombre != "APU" else -32, "TEST", "", "", "A", "W", guarda="clara",
         etiqueta_arriba=nombre != "APU")
p.cerrar()
avanzar("C", h)

# ================================================================== COLUMNA IZQUIERDA (proa → popa)
h = 56
p = panel("WIPER_L", "L", h)
titulo(p, "WIPER")
p.rot(-45, -6, "", ["OFF", "SLOW", "FAST"], indice=0, arco=90)
p.pb(40, -6, "RAIN RPLNT", "", "", "A", "W")
p.cerrar(); avanzar("L", h)

h = 84
p = panel("MAINT_L", "L", h)
titulo(p, "MAINTENANCE")
p.pb(-80, -4, "FADEC GND PWR 1", "", "ON", "A", "B")
p.pb(-40, -4, "FADEC GND PWR 2", "", "ON", "A", "B")
p.pb(5, -4, "BLUE PUMP OVRD", "", "ON", "A", "B", guarda="roja")
p.pb(60, -4, "APU AUTO EXTG", "TEST", "", "W", "W")
p.texto(60, -18, "RESET", "mini")
p.cerrar(); avanzar("L", h)

h = 56
p = panel("CALLS", "L", h)
titulo(p, "CALLS")
for i, (n, x) in enumerate((("MECH", -90), ("FWD", -45), ("MID", 0), ("AFT", 45))):
    p.pb(x, -6, n, "", "", "W", "W")
p.pb(95, -6, "EMER", "CALL", "ON", "A", "W")
p.cerrar(); avanzar("L", h)

h = 60
p = panel("OXYGEN", "L", h)
titulo(p, "OXYGEN")
p.pb(-70, -6, "MASK MAN ON", "", "", "A", "W", guarda="roja")
p.pb(0, -6, "PASSENGER", "SYS ON", "", "W", "W")
p.pb(70, -6, "CREW SUPPLY", "", "OFF", "A", "W")
p.cerrar(); avanzar("L", h)

h = 50
p = panel("RCDR", "L", h)
titulo(p, "RCDR")
p.pb(-70, -6, "GND CTL", "", "ON", "A", "B")
p.pb(0, -6, "CVR ERASE", "", "", "W", "W")
p.pb(70, -6, "CVR TEST", "", "", "W", "W")
p.cerrar(); avanzar("L", h)

h = 60
p = panel("GPWS", "L", h)
titulo(p, "GPWS")
for n, x in (("SYS", -100), ("G/S MODE", -50), ("FLAP MODE", 0), ("LDG FLAP 3", 50), ("TERR", 100)):
    p.pb(x, -6, n, "FAULT", "OFF", "A", "W")
p.cerrar(); avanzar("L", h)

h = 76
p = panel("EMER_ELEC", "L", h)
titulo(p, "EMER ELEC PWR")
p.pb(-70, -2, "EMER GEN TEST", "", "", "W", "W")
p.pb(-10, -2, "GEN 1 LINE", "SMOKE", "OFF", "A", "W", guarda="roja")
p.pb(60, -2, "MAN ON", "FAULT", "", "A", "W", guarda="roja")
p.texto(60, -18, "RAT & EMER GEN", "mini")
p.cerrar(); avanzar("L", h)

h = 56
p = panel("EVAC", "L", h)
titulo(p, "EVAC")
p.pb(-70, -6, "COMMAND", "EVAC", "ON", "A", "W", guarda="roja")
p.pb(0, -6, "HORN SHUT OFF", "", "", "W", "W")
p.sw(70, -6, "CAPT & PURS", "CAPT", "CAPT & PURS", pos=1)
p.cerrar(); avanzar("L", h)

h = 56
p = panel("FLT_CTL_L", "L", h)
titulo(p, "FLT CTL")
p.pb(-80, -6, "PRIM 1", "FAULT", "OFF", "A", "W")
p.pb(-25, -6, "SEC 1", "FAULT", "OFF", "A", "W")
p.pb(30, -6, "FAC 1", "FAULT", "OFF", "A", "W")
p.cerrar(); avanzar("L", h)

h = 171
p = panel("ADIRS", "L", h)
titulo(p, "ADIRS")
p.lcd(-35, 55, 120, 15, "N 43°37.8   E 001°22.4", material="MAT_CAB_Texto_Verde", tam=0.0036)
p.texto(-35, 67, "DATA")
p.rot(85, 55, "", ["TEST", "TK/GS", "PPOS", "WIND", "HDG", "STS"], indice=2, arco=150, radio=15.0)
p.texto(85, 72, "DATA", "mini")
# teclado 4 × 3
teclas = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "CLR", "0", "ENT"]
for i, t in enumerate(teclas):
    fx, fy = i % 3, i // 3
    p.instancia("CAB_Fuente_Tecla_Keypad", -70 + fx * 20, 30 - fy * 15)
    p.texto(-70 + fx * 20, 30 - fy * 15, t, "mini")
    p.textos_tecla = True
p.texto(-50, 40, "N   S   E   W", "mini")
p.rot(30, 18, "SYS", ["OFF", "1", "3", "2"], indice=1, arco=120, radio=14.0, etiqueta_y=12.5)
p.pb(85, 18, "ON BAT", "", "", "A", "W")
# 3 selectores OFF/NAV/ATT + IR/ADR
for k, x in enumerate((-90, -10, 70)):
    n = ("1", "3", "2")[k]
    p.rot(x, -48, f"IR {n}", ["OFF", "NAV", "ATT"], indice=1, arco=90, radio=15.0, etiqueta_y=-18)
    p.pb(x + 30, -30, f"IR {n}", "FAULT", "ALIGN", "A", "W", inf_on=True)
    p.pb(x + 30, -62, f"ADR {n}", "FAULT", "OFF", "A", "W", etiqueta_arriba=False)
p.cerrar(); avanzar("L", h)

# ================================================================== COLUMNA DERECHA (proa → popa)
h = 56
p = panel("WIPER_R", "R", h)
titulo(p, "WIPER")
p.pb(-40, -6, "RAIN RPLNT", "", "", "A", "W")
p.rot(45, -6, "", ["OFF", "SLOW", "FAST"], indice=0, arco=90)
p.cerrar(); avanzar("R", h)

h = 72
p = panel("BLANCO_R1", "R", h)
p.cerrar(); avanzar("R", h)

h = 82
p = panel("CARGO_AIR", "R", h)
titulo(p, "CARGO AIR COND")
p.knob(-80, -6, "AFT", "COLD", "HOT", valor=0.4)
p.pb(-25, -4, "HOT AIR", "FAULT", "OFF", "A", "W")
p.pb(25, -4, "AFT ISOL VALVE", "FAULT", "OFF", "A", "W")
p.pb(80, -4, "FWD ISOL VALVE", "FAULT", "OFF", "A", "W")
p.cerrar(); avanzar("R", h)

h = 62
p = panel("VENTILATION", "R", h)
titulo(p, "VENTILATION")
p.pb(-70, -6, "CAB FANS", "", "OFF", "A", "W")
p.pb(0, -6, "BLOWER", "FAULT", "OVRD", "A", "W")
p.pb(70, -6, "EXTRACT", "FAULT", "OVRD", "A", "W")
p.cerrar(); avanzar("R", h)

h = 60
p = panel("ENG", "R", h)
titulo(p, "ENG")
p.pb(-60, -6, "MAN START 1", "", "ON", "A", "B")
p.pb(0, -6, "N1 MODE 1", "FAULT", "ON", "A", "B")
p.pb(60, -6, "MAN START 2", "", "ON", "A", "B")
p.cerrar(); avanzar("R", h)

h = 78
p = panel("CARGO_SMOKE", "R", h)
titulo(p, "CARGO SMOKE")
p.luz(-75, 8, "FWD SMOKE", "A"); p.luz(-75, -6, "AFT SMOKE", "A")
p.pb(-15, -4, "DISCH FWD", "", "DISCH", "A", "W", guarda="roja")
p.pb(35, -4, "DISCH AFT", "", "DISCH", "A", "W", guarda="roja")
p.pb(85, -4, "TEST", "", "", "W", "W")
p.cerrar(); avanzar("R", h)

h = 74
p = panel("BLANCO_R2", "R", h)
p.cerrar(); avanzar("R", h)

h = 64
p = panel("CVR", "R", h)
titulo(p, "AUDIO / CVR")
p.sw(-60, -6, "ACP 3 SWTG", "CAPT 3", "F/O 3", centro="NORM", pos=0)
p.pb(10, -6, "CVR GND CTL", "", "ON", "A", "B")
p.pb(70, -6, "SVCE INT OVRD", "", "ON", "A", "W")
p.cerrar(); avanzar("R", h)

h = 721 - _v["R"] - 56 - 4
p = panel("BLANCO_R3", "R", h)
p.cerrar(); avanzar("R", h)

h = 56
p = panel("FLT_CTL_R", "R", h)
titulo(p, "FLT CTL")
p.pb(-95, -6, "PRIM 2", "FAULT", "OFF", "A", "W")
p.pb(-45, -6, "PRIM 3", "FAULT", "OFF", "A", "W")
p.pb(5, -6, "SEC 2", "FAULT", "OFF", "A", "W")
p.pb(55, -6, "FAC 2", "FAULT", "OFF", "A", "W")
p.cerrar(); avanzar("R", h)

# ================================================================== OVERHEAD TRASERO: BREAKERS
NOMBRES_CB = ["FCU 1", "FCU 2", "ADIRU 1", "ADIRU 2", "ADIRU 3", "DMC 1", "DMC 2", "DMC 3", "FWC 1", "FWC 2",
              "SDAC 1", "SDAC 2", "PRIM 1", "PRIM 2", "PRIM 3", "SEC 1", "SEC 2", "FAC 1", "FAC 2", "FMGEC 1",
              "FMGEC 2", "MCDU 1", "MCDU 2", "MCDU 3", "RMP 1", "RMP 2", "RMP 3", "ACP 1", "ACP 2", "ACP 3",
              "VHF 1", "VHF 2", "VHF 3", "HF 1", "HF 2", "ATC 1", "ATC 2", "TCAS", "WXR 1", "WXR 2",
              "ILS 1", "ILS 2", "VOR 1", "VOR 2", "DME 1", "DME 2", "ADF", "GPWC", "CVR", "DFDR",
              "BSCU 1", "BSCU 2", "LGCIU 1", "LGCIU 2", "BMC 1", "BMC 2", "CPC 1", "CPC 2", "FQIC 1", "FQIC 2",
              "EEC 1A", "EEC 1B", "EEC 2A", "EEC 2B", "IGN 1A", "IGN 2A", "FADEC 1", "FADEC 2", "APU ECB", "APU START",
              "PROBE HT 1", "PROBE HT 2", "WSHLD HT L", "WSHLD HT R", "WIPER L", "WIPER R", "DOME LT", "FLOOD LT", "ANN LT", "INTEG LT"]
CB_PASO_X, CB_PASO_Y = 19.0, 23.0
_v["L"] = _v["C"] = _v["R"] = 0.0
def panel_cb(nombre, col, alto, filas, cols, semilla):
    uc, w = COLUMNAS[col]
    centro = pos_A(uc, _v[col] + alto / 2)
    _sem[0] += 7
    p = Panel(nombre, COL, "CAB_Root", centro, ROT_A, w / 1000.0, (alto - 1.5) / 1000.0, semilla=_sem[0])
    rnd = random.Random(semilla)
    x0 = -(cols - 1) * CB_PASO_X / 2
    y0 = (filas - 1) * CB_PASO_Y / 2 - 6
    letras = "ABCDEFGHJKLMNPQR"
    for f in range(filas):
        p.texto(x0 - 13, y0 - f * CB_PASO_Y, letras[f], "mini")
        for c in range(cols):
            x, y = x0 + c * CB_PASO_X, y0 - f * CB_PASO_Y
            if rnd.random() < 0.06:       # posición libre (sin breaker)
                continue
            tirado = rnd.random() < 0.012
            p.instancia("CAB_Fuente_Breaker", x, y, escala=1.0, z=0.0025 if tirado else 0.0)
            anillo = "CAB_Fuente_CB_Anillo_Blanco" if rnd.random() > 0.12 else "CAB_Fuente_CB_Anillo_Color"
            p.instancia(anillo, x, y)
            if rnd.random() < 0.035:
                p.instancia("CAB_Fuente_CB_Collarin", x, y)
            p.texto(x, y + 9.5, NOMBRES_CB[(f * cols + c + semilla * 7) % len(NOMBRES_CB)], "mini")
    for c in range(cols):
        p.texto(x0 + c * CB_PASO_X, y0 + 17, str(c + 1), "mini")
    p.cerrar()
    _v[col] += alto
    return p


# fuentes de anillos y collarines de breaker
aux = bpy.data.collections["CAB_Auxiliar"]
for nombre, matn in (("CAB_Fuente_CB_Anillo_Blanco", "MAT_CAB_Plastico_Blanco"), ("CAB_Fuente_CB_Anillo_Color", "MAT_CAB_Amarillo")):
    bm = ax.bm_nuevo()
    r = bmesh.ops.create_cone(bm, cap_ends=False, segments=24, radius1=0.0047, radius2=0.0047, depth=0.0011)
    bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0, 0.0040))
    ob = ax.objeto(nombre, ax.bm_a_malla(nombre, bm), aux, None)
    ob.modifiers.new("Solid", "SOLIDIFY").thickness = 0.0009
    ax.asignar(ob, matn)
    ob.hide_render = ob.hide_viewport = True
bm = ax.bm_nuevo()
ax.cilindro(bm, 0.0058, 0.0035, 20, (0, 0, 0.0042))
ax.caja(bm, (0.004, 0.012, 0.002), (0, -0.007, 0.006))
ob = ax.objeto("CAB_Fuente_CB_Collarin", ax.bm_a_malla("CAB_Fuente_CB_Collarin", bm), aux, None)
ax.asignar(ob, "MAT_CAB_Guarda_Roja")
ax.estilo(ob, bisel=0.0004, atributos=False)
ob.hide_render = ob.hide_viewport = True

panel_cb("CB_L1", "L", 255, 9, 13, 1)
panel_cb("CB_C1", "C", 255, 9, 16, 2)
panel_cb("CB_R1", "R", 255, 9, 13, 3)
panel_cb("CB_L2", "L", 255, 9, 13, 4)
panel_cb("CB_C2", "C", 255, 9, 16, 5)
panel_cb("CB_R2", "R", 255, 9, 13, 6)

# ================================================================== CARCASA
def carcasa():
    """Bandeja del overhead: marco perimetral, paredes laterales hasta el techo, fondo oscuro
    tras las juntas entre paneles y carenado delantero contra el borde del parabrisas."""
    bm = ax.bm_nuevo()
    ancho = 0.455
    prof = 0.11
    for (p0, d, L, ang) in ((FRENTE, dirF, LF, ALFA), (B0, dirA, LA, BETA)):
        up = Vector((0.0, math.sin(ang), math.cos(ang)))     # normal hacia el techo
        lado = Vector((1, 0, 0))
        a0 = p0 - d * 0.004
        a1 = p0 + d * (L + 0.004)
        # paredes laterales: placas de 12 mm de grosor
        for s in (-1, 1):
            c0 = a0 + lado * s * (ancho + 0.006) - up * 0.016
            c1 = a1 + lado * s * (ancho + 0.006) - up * 0.016
            vs = []
            for c in (c0, c1):
                for t in (0.0, prof + 0.016):
                    for e in (-0.006, 0.006):
                        vs.append(bm.verts.new(c + up * t + lado * e))
            # caja a partir de 8 vértices (orden: c, t, e)
            idx = lambda ci, ti, ei: vs[ci * 4 + ti * 2 + ei]
            for f in ((idx(0, 0, 0), idx(1, 0, 0), idx(1, 1, 0), idx(0, 1, 0)), (idx(0, 0, 1), idx(0, 1, 1), idx(1, 1, 1), idx(1, 0, 1)),
                      (idx(0, 0, 0), idx(0, 0, 1), idx(1, 0, 1), idx(1, 0, 0)), (idx(0, 1, 0), idx(1, 1, 0), idx(1, 1, 1), idx(0, 1, 1)),
                      (idx(0, 0, 0), idx(0, 1, 0), idx(0, 1, 1), idx(0, 0, 1)), (idx(1, 0, 0), idx(1, 0, 1), idx(1, 1, 1), idx(1, 1, 0))):
                bm.faces.new(f)
        # fondo oscuro
        f0 = [bm.verts.new(p + up * 0.012) for p in (a0 - lado * ancho, a1 - lado * ancho, a1 + lado * ancho, a0 + lado * ancho)]
        cara = bm.faces.new(f0)
        cara.material_index = 1
    # carenado delantero: del borde delantero del overhead hacia el techo y el marco del parabrisas
    up = Vector((0.0, math.sin(ALFA), math.cos(ALFA)))
    q0 = FRENTE - dirF * 0.004 - up * 0.016
    pts = [q0 + Vector((x, 0, 0)) for x in (-ancho - 0.012, ancho + 0.012)]
    alto = [p + Vector((0, 0.05, 0.09)) for p in pts]
    vs = [bm.verts.new(p) for p in pts + list(reversed(alto))]
    bm.faces.new(vs)
    nom = "CAB_OH_Carcasa"
    ob = ax.objeto(nom, ax.bm_a_malla(nom, bm), COL, "CAB_Root")
    ax.asignar(ob, "MAT_CAB_Panel", "MAT_CAB_Negro_Profundo")
    ax.estilo(ob, bisel=0.002, segs=2)
    # marco perimetral (lip) alrededor de cada plano
    for nombre, p0, d, L, ang in (("CAB_OH_Marco_Delantero", FRENTE, dirF, LF, ALFA), ("CAB_OH_Marco_Trasero", B0, dirA, LA, BETA)):
        bm = ax.bm_nuevo()
        c = p0 + d * (L / 2)
        exterior = ax.rect_redondeado(2 * ancho + 0.03, L + 0.026, 0.008, 3)
        interior = ax.rect_redondeado(2 * ancho - 0.002, L + 0.002, 0.002, 1)
        bm.free()
        ob = ax.objeto(nombre, bpy.data.meshes.new(nombre), COL, "CAB_Root", c, (math.pi - ang, 0, 0))
        bm = ax.bm_nuevo()
        ve = [bm.verts.new((x, y, 0.0012)) for x, y in exterior]
        vi = [bm.verts.new((x * 1.0, y * 1.0, 0.0012)) for x, y in ax.rect_redondeado(2 * ancho - 0.002, L + 0.002, 0.002, 3)]
        # anillo por puentes radiales (mismo número de vértices)
        n = len(ve)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((vi[i], vi[j], ve[j], ve[i]))
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        r = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
        for v in [e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)]:
            v.co.z -= 0.0042
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        ob.data = ax.bm_a_malla(nombre, bm)
        ax.asignar(ob, "MAT_CAB_Panel")
        ax.estilo(ob, bisel=0.0015, segs=2)


carcasa()

# ------------------------------------------------------------------ luces de domo/storm (cuerpos; la luz va en F08)
for s in (-1, 1):
    bm = ax.bm_nuevo()
    ax.cilindro(bm, 0.055, 0.018, 40, (0, 0, -0.009), mat=0)
    ax.cilindro(bm, 0.045, 0.006, 40, (0, 0, -0.019), mat=1)
    ob = ax.objeto(f"CAB_Luz_Domo_{'L' if s < 0 else 'R'}", ax.bm_a_malla("domo", bm), "Detalles", "CAB_Root",
                   (s * 0.62, -0.55, 2.27), (math.radians(-20), 0, 0))
    ax.asignar(ob, "MAT_CAB_Plastico_Blanco", "MAT_CAB_Lampara_Calida")
    ax.estilo(ob, bisel=0.002, segs=3)

ax.informe(pulsadores=len([o for o in COL.objects if "_PB_" in o.name]), objetos=len(COL.objects))
ax.guardar(a.salida)
