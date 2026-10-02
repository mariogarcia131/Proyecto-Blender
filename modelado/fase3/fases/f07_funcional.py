"""F07 — Funcionalidad: mandos con límites y drivers a CAB_Control, guardas animables y pantallas."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix
import axlib as ax

a = ax.iniciar("F07")
O = bpy.data.objects

# ------------------------------------------------------------------ 1. límites de los mandos existentes
for n_ in ("CAB_Pedestal_Gases_L", "CAB_Pedestal_Gases_R"):
    ax.limitar_rot(O[n_], x=(-26.1, 32.1))
for n_ in ("CAB_Reversa_Pivote_1", "CAB_Reversa_Pivote_2"):
    ax.limitar_rot(O[n_], x=(0.0, 60.3))
ax.limitar_rot(O["CAB_Pedestal_Flaps"], x=(-26.1, 22.1))
ax.limitar_rot(O["CAB_Pedestal_Speedbrake"], x=(-12.1, 28.1))
ax.limitar_rot(O["CAB_Tren_Pivote"], x=(-34.5, 34.5))
ax.limitar_rot(O["CAB_Freno_Parking"], z=(-90.1, 0.1))
for n_ in ("CAB_Trim_Rueda_L", "CAB_Trim_Rueda_R"):
    ax.limitar_rot(O[n_], x=(-1081, 1081))
for n_ in ("CAB_Trim_Indice_L", "CAB_Trim_Indice_R"):
    ax.limitar_loc(O[n_], y=(-0.0385, 0.0225))
ax.limitar_rot(O["CAB_Puerta_Pivote"], z=(-100.1, 0.1))
for n_ in ("CAB_Asiento_Capitan", "CAB_Asiento_Primer_Oficial"):
    ax.limitar_loc(O[n_], y=(-0.2505, -0.0095))

# ------------------------------------------------------------------ 2. pedales de timón y frenos de pie (enlazados en ambos puestos)
ax.propiedad("Pedales", 0.0, -1.0, 1.0, "Pedales de timón: -1 izquierda · +1 derecha (enlazados capitán/FO)")
ax.propiedad("Frenos_Pedales", 0.0, 0.0, 1.0, "Frenos de pie (punta de los pedales)")
for suf, signo_ext in (("", 1), ("_FO", -1)):
    for k in (0, 1):
        piv = O[f"CAB_Pedal_Pivote_{k}{suf}"]
        # pedal izquierdo: k=0 en el capitán (exterior) y k=1 en el FO (interior)
        izquierdo = (k == 0) if suf == "" else (k == 1)
        expr = f"-0.489 + p * 0.15" if izquierdo else f"-0.489 - p * 0.15"
        ax.driver(piv, "rotation_euler", expr, {"p": "Pedales"}, indice=0)
        ax.limitar_rot(piv, x=(-0.489 * 57.296 - 8.7, -0.489 * 57.296 + 8.7))
        fr = O[f"CAB_Pedal_Freno_Pivote_{k}{suf}"]
        ax.driver(fr, "rotation_euler", "-0.14 - b * 0.26", {"b": "Frenos_Pedales"}, indice=0)
        ax.limitar_rot(fr, x=(-23.0, -7.9))

# ------------------------------------------------------------------ 3. tiller (capitán y FO)
ax.propiedad("Tiller", 0.0, -1.0, 1.0, "Volante de rodadura (tiller): ±75°")
for n_ in ("CAB_Tiller", "CAB_Tiller_FO"):
    ax.driver(O[n_], "rotation_euler", "-t * 1.309", {"t": "Tiller"}, indice=2)
    ax.limitar_rot(O[n_], z=(-75.1, 75.1))

# ------------------------------------------------------------------ 4. rotatorios del FCU: giran con el valor seleccionado
for k, expr, var in (("SPD", "v * 0.0628", "FCU_SPD"), ("HDG", "v * 0.017453", "FCU_HDG"),
                     ("ALT", "v * 0.000628", "FCU_ALT"), ("VS", "v * 0.00157", "FCU_VS")):
    ax.driver(O[f"CAB_FCU_Knob_{k}"], "rotation_euler", expr, {"v": var}, indice=2)

# ------------------------------------------------------------------ 5. ventanas laterales deslizantes (W2)
ax.propiedad("Ventana_Lateral_L", 0.0, 0.0, 1.0, "Ventana lateral deslizante del capitán: 0 cerrada · 1 abierta")
ax.propiedad("Ventana_Lateral_R", 0.0, 0.0, 1.0, "Ventana lateral deslizante del FO: 0 cerrada · 1 abierta")
for lado, s in (("L", -1), ("R", 1)):
    prop = f"Ventana_Lateral_{lado}"
    for base in ("CAB_Vidrio_W2_", "CAB_Marco_W2_", "CAB_Junta_W2_", "CAB_Tornillos_Marco_W2_"):
        ob = O[base + lado]
        # objetos en coordenadas de mundo: popa = +X mundo; hacia dentro = -s en Y mundo
        ax.driver(ob, "location", "v * 0.33", {"v": prop}, indice=0)
        ax.driver(ob, "location", f"{-s} * min(v * 6, 1) * 0.028", {"v": prop}, indice=1)
        ax.limitar_loc(ob, x=(0.0, 0.33))

# ------------------------------------------------------------------ 6. guardas animables (rojas y transparentes)
g = bpy.data.node_groups.get("GN_CAB_Rotar_Instancias")
if g:
    bpy.data.node_groups.remove(g)
g = bpy.data.node_groups.new("GN_CAB_Rotar_Instancias", "GeometryNodeTree")
ax.marcar(g)
g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
s_ang = g.interface.new_socket("Angulo", in_out="INPUT", socket_type="NodeSocketFloat")
s_piv = g.interface.new_socket("Bisagra", in_out="INPUT", socket_type="NodeSocketVector")
s_piv.default_value = (0.0, 0.0179, 0.0)
n = ax.Nodos(g)
gi = n.nodo("NodeGroupInput"); go = n.nodo("NodeGroupOutput")
rad = n.mat("MULTIPLY", gi.outputs["Angulo"], math.pi / 180.0)
rot = n.nodo("FunctionNodeEulerToRotation")
n.con(rot.inputs[0], n.comb(rad, 0.0, 0.0))
ri = n.nodo("GeometryNodeRotateInstances")
n.con(ri.inputs["Instances"], gi.outputs["Geometry"])
n.con(ri.inputs["Rotation"], rot.outputs[0])
n.con(ri.inputs["Pivot Point"], gi.outputs["Bisagra"])
ri.inputs["Local Space"].default_value = True
n.con(go.inputs["Geometry"], ri.outputs[0])
ax.propiedad("Guardas", 0.0, 0.0, 1.0, "Apertura de las guardas de los pulsadores protegidos (0 cerradas · 1 abiertas)")
n_g = 0
for ob in O:
    if ob.type == "MESH" and (ob.name.endswith("_Guarda_Roja") or ob.name.endswith("_Guarda_Clara")):
        m = ax.gn(ob, g, "Guardas")
        ax.driver(ob, ax.gn_ruta(m, "Angulo"), "-g * 75", {"g": "Guardas"})
        n_g += 1

# ------------------------------------------------------------------ 7. pantallas: textos por encima del LCD (estaban 1 mm por debajo)
fijados = 0
for ob in O:
    if ob.name.startswith("CAB_Pantalla_") and "_Txt_" in ob.name and ob.location.z < 0.001:
        lcd = O.get(ob.name.split("_Txt_")[0] + "_LCD")
        if lcd is None:
            continue
        zl = min(v.co.z for v in lcd.data.vertices) + lcd.location.z
        ob.location.z = zl + 0.0003
        fijados += 1

ax.informe(guardas=n_g, textos_pantalla=fijados)
ax.guardar(a.salida)
