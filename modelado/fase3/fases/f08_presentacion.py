"""F08 — Presentación: mundo, plataforma, luces físicas, cámaras del vídeo y de las fotos, animación.

Parámetros por variables de entorno (para reconstruir con otra duración o fps sin tocar el guion):
  AX_FPS (por defecto 30)
El guion se escribe en segundos; las fotos usan fotogramas a partir de 9001 (fuera del vídeo) con
el estado de CAB_Control fijado por fotograma (día, noche, piel de oveja…).
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
import axlib as ax

a = ax.iniciar("F08")
sc = bpy.context.scene
root = ax.ROOT()
ctrl = ax.CTRL()
M = root.matrix_world.copy()
FPS = int(os.environ.get("AX_FPS", "30"))
SUELO_Z = -5.55          # contacto de los neumáticos del tren de morro (mundo)


def L(p):                # marco local de CAB_Root → mundo
    return M @ Vector(p)


# ------------------------------------------------------------------ 0. colecciones
COL_ENT = ax.coleccion("Entorno_Presentacion", "AX620")
COL_CAM = ax.coleccion("Camaras_Presentacion", "AX620")
COL_LUZ = ax.coleccion("Iluminacion_Cabina", "CABINA")

# ------------------------------------------------------------------ 1. propiedades de iluminación
ax.propiedad("Luz_Domo", 0.0, 0.0, 1.0, "Luces de domo (techo): 0 apagadas · 1 máximo")
ax.propiedad("Luz_Storm", 0.0, 0.0, 1.0, "Luz de tormenta (domo al máximo y flood de panel)")
ax.propiedad("Luz_Lectura", 0.0, 0.0, 1.0, "Luces de lectura de las consolas laterales")
ax.propiedad("Luz_Sol", 1.0, 0.0, 1.0, "Intensidad del sol (se apaga en el modo Noche)")

# ------------------------------------------------------------------ 2. mundo (día/noche)
SOL_DIR = Vector((-0.62, -0.52, 0.60)).normalized()      # hacia el sol: delante-izquierda y alto
elev = math.asin(SOL_DIR.z)
azim = math.atan2(SOL_DIR.x, SOL_DIR.y)
w = bpy.data.worlds.get("AX620_Mundo") or bpy.data.worlds.new("AX620_Mundo")
ax.marcar(w)
sc.world = w
w.use_nodes = True
nt = w.node_tree
nt.nodes.clear()
n = ax.Nodos(nt)
sky = n.nodo("ShaderNodeTexSky", sky_type="MULTIPLE_SCATTERING")
sky.sun_disc = False
sky.sun_elevation = elev
sky.sun_rotation = azim
sky.altitude = 120.0
sky.air_density = 1.0
sky.aerosol_density = 0.6
sky.ozone_density = 1.0
modo = n.attr("Modo_Cabina", "OBJECT")  # no hay objeto en el mundo: se usa un valor con driver
val_modo = n.valor(0.0)
ax.driver(nt, f'nodes["{val_modo.node.name}"].outputs[0].default_value', "m", {"m": "Modo_Cabina"})
lp = n.nodo("ShaderNodeLightPath")
geo_dir = n.nodo("ShaderNodeTexCoord").outputs["Generated"]
# noche: cielo azul muy oscuro con degradado y estrellas procedurales
vec = n.nodo("ShaderNodeTexCoord").outputs["Generated"]
_, _, vz = n.sep(n.vmat("NORMALIZE", n.vmat("SUBTRACT", vec, (0.5, 0.5, 0.5))))
noche = n.mezcla(n.suave(vz, -0.05, 0.6), (0.010, 0.014, 0.030, 1), (0.0012, 0.0018, 0.0050, 1))
est = n.voronoi(n.vmat("NORMALIZE", n.vmat("SUBTRACT", vec, (0.5, 0.5, 0.5))), 380.0, "F1", "Distance", 1.0)
brillo_est = n.mat("MULTIPLY", n.suave(est, 0.03, 0.0), n.mat("GREATER_THAN", n.ruido(vec, 900.0, 1.0), 0.62))
noche = n.mezcla(n.mat("MULTIPLY", brillo_est, n.suave(vz, 0.02, 0.15)), noche, (1.6, 1.6, 1.9, 1), blend="ADD")
cielo = n.mezcla(val_modo, sky.outputs[0], noche)
bg = n.nodo("ShaderNodeBackground")
n.con(bg.inputs[0], cielo)
bg.inputs[1].default_value = 1.0
out = n.nodo("ShaderNodeOutputWorld")
n.con(out.inputs[0], bg.outputs[0])
w.cycles_visibility.diffuse = True

# sol explícito (sombras nítidas, menos ruido que el disco del cielo)
sol_d = bpy.data.lights.get("AX620_Sol") or bpy.data.lights.new("AX620_Sol", "SUN")
sol_d.angle = math.radians(0.53)
sol_d.color = (1.0, 0.96, 0.90)
sol = ax.objeto("AX620_Sol", sol_d, COL_ENT, None)
sol.rotation_euler = (-SOL_DIR).to_track_quat("-Z", "Y").to_euler()
ax.driver(sol_d, "energy", "4.2 * s * (1 - m)", {"s": "Luz_Sol", "m": "Modo_Cabina"})
# luna (relleno azulado débil en el modo Noche)
luna_d = bpy.data.lights.get("AX620_Luna") or bpy.data.lights.new("AX620_Luna", "SUN")
luna_d.angle = math.radians(0.6)
luna_d.color = (0.65, 0.75, 1.0)
luna = ax.objeto("AX620_Luna", luna_d, COL_ENT, None)
luna.rotation_euler = (-Vector((0.5, 0.7, 0.45)).normalized()).to_track_quat("-Z", "Y").to_euler()
ax.driver(luna_d, "energy", "0.12 * m", {"m": "Modo_Cabina"})
# focos de la plataforma (solo de noche): torres de iluminación delante-izquierda y delante-derecha
for i, (pos, col) in enumerate((((-50.0, -16.0, 16.0), (1.0, 0.86, 0.70)), ((-47.0, 14.0, 14.0), (0.95, 0.92, 0.88)))):
    fd = bpy.data.lights.get(f"AX620_Foco_Plataforma_{i + 1}") or bpy.data.lights.new(f"AX620_Foco_Plataforma_{i + 1}", "SPOT")
    fd.spot_size = math.radians(48.0)
    fd.spot_blend = 0.5
    fd.shadow_soft_size = 0.6
    fd.color = col
    fo = ax.objeto(f"AX620_Foco_Plataforma_{i + 1}", fd, COL_ENT, None, pos)
    fo.rotation_euler = (Vector((-30.0, 0.0, -1.5)) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    ax.driver(fd, "energy", f"{3600 if i == 0 else 2200} * m", {"m": "Modo_Cabina"})

# ------------------------------------------------------------------ 3. plataforma neutra (hormigón procedural)
bm = ax.bm_nuevo()
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=400.0)
pl = ax.objeto("AX620_Plataforma", ax.bm_a_malla("plataforma", bm, suave=False), COL_ENT, None, (-20.0, 0.0, SUELO_Z))
m = ax.material("MAT_ENT_Hormigon")
n = ax.Nodos(m.node_tree)
P = n.nodo("ShaderNodeTexCoord").outputs["Object"]
px, py, _ = n.sep(P)
def junta(c, paso):
    r = n.mat("SUBTRACT", c, n.mat("MULTIPLY", n.mat("ROUND", n.mat("DIVIDE", c, paso)), paso))
    return n.mat("SUBTRACT", 1.0, n.suave(n.mat("ABSOLUTE", r), 0.008, 0.02))
juntas = n.mat("MAXIMUM", junta(px, 6.0), junta(py, 6.0))
manchas = n.ruido(P, 0.08, 6.0, 0.62)
fino = n.ruido(P, 9.0, 3.0, 0.6)
base = n.mezcla(manchas, (0.30, 0.30, 0.29, 1), (0.42, 0.41, 0.39, 1))
base = n.mezcla(n.mat("MULTIPLY", fino, 0.3), base, (0.25, 0.25, 0.24, 1))
base = n.mezcla(n.mat("MULTIPLY", juntas, 0.8), base, (0.12, 0.12, 0.12, 1))
# línea de rodaje amarilla bajo el eje del avión con borde negro
lin = n.mat("SUBTRACT", 1.0, n.suave(n.mat("ABSOLUTE", py), 0.075, 0.09))
borde = n.mat("SUBTRACT", 1.0, n.suave(n.mat("ABSOLUTE", py), 0.13, 0.145))
base = n.mezcla(borde, base, (0.02, 0.02, 0.02, 1))
base = n.mezcla(lin, base, ax.srgb_a_lineal((0.86, 0.66, 0.08)) + (1,))
bump = n.nodo("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.25
n.con(bump.inputs["Height"], n.mat("SUBTRACT", fino, n.mat("MULTIPLY", juntas, 2.0)))
ax.salida_material(n, ax.principled(n, base=base, rough=n.mat("ADD", 0.72, n.mat("MULTIPLY", fino, 0.15)), normal=bump.outputs[0]))
ax.asignar(pl, m)

# ------------------------------------------------------------------ 4. luces físicas de cabina
def luz_area(nombre, forma, tam, loc_local, mira_local, energia_expr, vars_, color=(1.0, 0.86, 0.68), spread=180.0):
    d = bpy.data.lights.new(nombre, "AREA")
    d.shape = forma
    if forma in ("RECTANGLE", "ELLIPSE"):
        d.size, d.size_y = tam
    else:
        d.size = tam
    d.color = color
    d.spread = math.radians(spread)
    ob = ax.objeto(nombre, d, COL_LUZ, "CAB_Root", loc_local)
    ob.rotation_euler = (Vector(mira_local) - Vector(loc_local)).to_track_quat("-Z", "Y").to_euler()
    ax.driver(d, "energy", energia_expr, vars_)
    return ob


def luz_spot(nombre, loc_local, mira_local, energia_expr, vars_, cono=40.0, color=(1.0, 0.86, 0.68), radio=0.01):
    d = bpy.data.lights.new(nombre, "SPOT")
    d.spot_size = math.radians(cono)
    d.spot_blend = 0.6
    d.shadow_soft_size = radio
    d.color = color
    ob = ax.objeto(nombre, d, COL_LUZ, "CAB_Root", loc_local)
    ob.rotation_euler = (Vector(mira_local) - Vector(loc_local)).to_track_quat("-Z", "Y").to_euler()
    ax.driver(d, "energy", energia_expr, vars_)
    return ob


for s, lado in ((-1, "L"), (1, "R")):
    luz_area(f"CAB_Luz_Domo_{lado}_Luz", "DISK", 0.09, (s * 0.62, -0.57, 2.245), (s * 0.45, -0.3, 0.5),
             "18 * min(d + st, 1)", {"d": "Luz_Domo", "st": "Luz_Storm"}, color=(1.0, 0.90, 0.78), spread=120)
    luz_spot(f"CAB_Luz_Lectura_{lado}_Luz", (s * 1.89, 0.03, 0.56), (s * 1.30, 0.15, 0.43),
             "6 * l", {"l": "Luz_Lectura"}, cono=55, radio=0.012)
for nombre, x, w_ in (("L", -0.55, 0.34), ("C", 0.0, 0.40), ("R", 0.55, 0.34)):
    luz_area(f"CAB_Glareshield_Flood_{nombre}_Luz", "RECTANGLE", (w_, 0.012), (x, 0.689, 0.729), (x, 0.80, 0.45),
             "5 * min(f + st, 1.5)", {"f": "Intensidad_Flood", "st": "Luz_Storm"}, spread=110)
luz_spot("CAB_Flood_Pedestal_Luz", (0.0, 0.26, 1.63), (0.0, 0.02, 0.32), "14 * min(f + st, 1.5)",
         {"f": "Intensidad_Flood", "st": "Luz_Storm"}, cono=62, radio=0.03)

# ------------------------------------------------------------------ 5. render base (los trozos imponen el resto)
r = sc.render
r.engine = "CYCLES"
r.fps, r.fps_base = FPS, 1.0
c = sc.cycles
c.max_bounces = 8
c.diffuse_bounces = 4
c.glossy_bounces = 4
c.transmission_bounces = 8
c.transparent_max_bounces = 24
c.volume_bounces = 0
c.sample_clamp_indirect = 8.0
c.caustics_reflective = False
c.caustics_refractive = False
c.use_light_tree = True
c.filter_width = 1.5
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "None"
sc.view_settings.exposure = -0.4

# ------------------------------------------------------------------ 5a. exposición de cámara (compositor)
# color.exposicion es global y forma parte de la huella; la exposición por plano (exteriores de día
# más oscuros, noches más claras) se anima aquí, dentro del .blend inmutable.
ax.propiedad("Exposicion_EV", 0.0, -4.0, 4.0, "Exposición de cámara en EV aplicada en el compositor (por plano y por foto)")
gc = bpy.data.node_groups.get("AX620_Composicion")
if gc:
    bpy.data.node_groups.remove(gc)
gc = bpy.data.node_groups.new("AX620_Composicion", "CompositorNodeTree")
ax.marcar(gc)
gc.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
rl = gc.nodes.new("CompositorNodeRLayers")
ex = gc.nodes.new("CompositorNodeExposure")
go = gc.nodes.new("NodeGroupOutput")
rl.location, ex.location, go.location = (-300, 0), (0, 0), (250, 0)
gc.links.new(rl.outputs["Image"], ex.inputs["Image"])
gc.links.new(ex.outputs["Image"], go.inputs[0])
ax.driver(gc, f'nodes["{ex.name}"].inputs[1].default_value', "ev", {"ev": "Exposicion_EV"})
sc.compositing_node_group = gc
sc.render.use_compositing = True

# ------------------------------------------------------------------ 5b. acabado de materiales
def fresnel_schlick(m):
    """Sustituye los nodos Fresnel por Schlick con |cos θ|: el Fresnel de Cycles invierte el IOR en
    caras traseras y da reflexión interna total a ángulos rasantes (parabrisas negro desde dentro)."""
    nt = m.node_tree
    nn = ax.Nodos(nt)
    for fr in [x for x in nt.nodes if x.type == "FRESNEL"]:
        ior = fr.inputs["IOR"].default_value
        f0 = ((ior - 1.0) / (ior + 1.0)) ** 2
        geo = nn.nodo("ShaderNodeNewGeometry")
        cos = nn.mat("ABSOLUTE", nn.vmat("DOT_PRODUCT", geo.outputs["Normal"], geo.outputs["Incoming"]))
        f = nn.mat("ADD", f0, nn.mat("MULTIPLY", 1.0 - f0, nn.mat("POWER", nn.mat("SUBTRACT", 1.0, cos), 5.0)))
        for l in list(fr.outputs[0].links):
            nt.links.new(f, l.to_socket)
        nt.nodes.remove(fr)


for nombre in ("MAT_CAB_Vidrio_Parabrisas", "MAT_CAB_Cristal_AR"):
    if nombre in bpy.data.materials:
        fresnel_schlick(bpy.data.materials[nombre])
# FCU en modo gestionado: guiones en SPD/HDG/VS y punto de «managed» (ALT mantiene el valor)
def fcu_gestionado(k, guiones):
    m = bpy.data.materials.get(f"MAT_CAB_LCD_FCU_{k}")
    if m is None:
        return
    nt = m.node_tree
    nn = ax.Nodos(nt)
    g7 = next(x for x in nt.nodes if x.type == "GROUP" and x.node_tree and x.node_tree.name == "NG_CAB_Numero7")
    dest = [l.to_socket for l in g7.outputs["Mascara"].links]
    u = g7.inputs["U"].links[0].from_socket
    v = g7.inputs["V"].links[0].from_socket
    dig = g7.inputs["Digitos"].default_value
    ancho = g7.inputs["Ancho_Celda"].default_value
    gest = nn.param(f"FCU_{k}_Gestionada")
    mascara = g7.outputs["Mascara"]
    if guiones:
        banda = nn.mat("LESS_THAN", nn.mat("ABSOLUTE", nn.mat("SUBTRACT", v, 0.5)), 0.022)
        guion = nn.mat("MULTIPLY", g7.outputs["Fantasma"], banda)
        mascara = nn.mezcla(gest, mascara, guion, tipo="FLOAT")
    margen = (1.0 - ancho) / dig
    cu = 1.0 - margen * 0.5
    du = nn.mat("DIVIDE", nn.mat("SUBTRACT", u, cu), margen * 0.24)
    dv = nn.mat("DIVIDE", nn.mat("SUBTRACT", v, 0.5), 0.075)
    punto = nn.mat("LESS_THAN", nn.mat("ADD", nn.mat("MULTIPLY", du, du), nn.mat("MULTIPLY", dv, dv)), 1.0)
    mascara = nn.mat("MAXIMUM", mascara, nn.mat("MULTIPLY", punto, gest))
    for d_ in dest:
        nt.links.new(mascara, d_)


for k, guiones in (("SPD", True), ("HDG", True), ("ALT", False), ("VS", True)):
    fcu_gestionado(k, guiones)
# pantallas con tratamiento antirreflejo (menos reflejo especular sobre el LCD)
for m in bpy.data.materials:
    if m.name.startswith("MAT_CAB_Pantalla_") and m.node_tree:
        for x in m.node_tree.nodes:
            if x.type == "BSDF_PRINCIPLED":
                x.inputs["Specular IOR Level"].default_value = 0.12
                x.inputs["Coat Weight"].default_value = 0.0
m = bpy.data.materials.get("MAT_MORRO_Rotulo")
if m and m.node_tree:
    for x in m.node_tree.nodes:
        if x.type == "BSDF_PRINCIPLED":
            x.inputs["Coat Weight"].default_value = min(x.inputs["Coat Weight"].default_value, 0.3)

# ------------------------------------------------------------------ 6. cámara del vídeo (plano secuencia)
cam_d = bpy.data.cameras.new("CAM_Video")
cam_d.sensor_width = 36.0
cam_d.clip_start = 0.01
cam_d.clip_end = 1500.0
cam = ax.objeto("CAM_Video", cam_d, COL_CAM, None)
obj = ax.vacio("CAM_Video_Objetivo", COL_CAM, None, tam=0.2)
tt = cam.constraints.new("TRACK_TO")
tt.target = obj
tt.track_axis = "TRACK_NEGATIVE_Z"
tt.up_axis = "UP_Y"
sc.camera = cam

# guion: (segundo, posición, objetivo, focal, espacio) — 'L' = marco de CAB_Root, 'W' = mundo
GUION = [
    (0.0, (-41.0, -15.5, 1.6), (-29.0, 0.0, -0.4), 40, "W"),          # órbita exterior 3/4, sol bajo
    (4.0, (-39.5, -10.5, 1.0), (-28.8, 0.0, -0.5), 40, "W"),
    (8.0, (-33.5, -6.2, -0.4), (-29.0, -2.4, -0.8), 45, "W"),          # acercamiento a sondas (pitot/AoA)
    (11.0, (-30.4, -3.65, -0.62), (-28.95, -2.45, -0.83), 50, "W"),
    (14.0, (-31.6, -1.6, 0.25), (-29.3, -0.6, 0.3), 40, "W"),           # sube hacia el parabrisas
    (16.5, (-0.56, 1.85, 1.02), (-0.55, 0.9, 0.95), 30, "L"),           # delante del W1 del capitán
    (18.5, (-0.42, 1.02, 1.12), (-0.10, -0.70, 0.80), 22, "L"),         # atraviesa el parabrisas: la cabina entera
    (21.5, (-0.10, 0.30, 1.30), (-1.40, 0.10, 0.80), 22, "L"),          # giro amplio por el lado del capitán
    (24.0, (-0.40, 0.20, 1.00), (-0.55, 0.74, 0.62), 26, "L"),          # panel principal (capitán)
    (27.0, (0.0, 0.33, 0.86), (0.0, 0.74, 0.60), 28, "L"),              # panel central
    (29.5, (0.55, 0.36, 0.88), (0.55, 0.74, 0.62), 28, "L"),            # lado FO
    (32.0, (0.10, 0.40, 1.02), (0.0, 0.69, 0.80), 30, "L"),             # glareshield / FCU
    (35.0, (0.0, -0.05, 1.22), (0.0, 0.22, 1.70), 18, "L"),             # overhead: barrido (desde popa, texto legible)
    (38.5, (0.0, -0.40, 1.28), (0.0, -0.14, 1.76), 18, "L"),
    (42.0, (0.0, -1.00, 1.38), (0.0, -0.66, 1.92), 18, "L"),            # breakers
    (45.5, (0.0, -0.55, 1.05), (0.0, 0.05, 0.32), 22, "L"),             # pedestal
    (48.5, (0.0, 0.05, 0.92), (0.0, 0.45, 0.33), 22, "L"),
    (50.5, (-0.25, 0.35, 0.40), (-0.55, 1.05, 0.12), 20, "L"),          # baja bajo el panel
    (51.7, (-0.33, 0.70, 0.27), (-0.60, 1.10, 0.10), 19, "L"),
    (53.5, (-0.20, 0.90, 0.24), (-0.62, 1.12, 0.09), 18, "L"),          # pedales y raíles
    (55.0, (-0.40, 0.55, 0.30), (-0.95, 0.40, 0.45), 20, "L"),          # sale hacia la consola del capitán
    (57.0, (-0.70, 0.15, 0.85), (-0.98, 0.32, 0.55), 26, "L"),          # sidestick y consola
    (60.0, (-0.85, -0.25, 1.05), (-1.35, 0.15, 0.45), 22, "L"),         # consola lateral
    (63.0, (-0.10, 0.50, 1.15), (-0.55, -0.35, 0.65), 20, "L"),         # asientos
    (66.0, (0.20, 0.10, 1.25), (-0.85, -1.50, 1.00), 18, "L"),          # observadores
    (69.0, (0.0, -0.35, 1.30), (0.0, -1.60, 1.05), 18, "L"),            # mamparo y puerta
    (72.5, (-0.54, -0.05, 1.26), (-0.40, 1.20, 0.80), 24, "L"),         # POV del capitán
    (84.0, (-0.54, -0.02, 1.25), (-0.36, 1.20, 0.82), 24, "L"),
    (88.0, (-0.30, 0.10, 1.22), (-0.30, 1.50, 1.00), 24, "L"),          # transición día/noche
    (89.8, (-0.35, 0.55, 1.40), (-1.40, 0.80, 1.00), 22, "L"),          # mira por la ventana lateral
    (91.5, (-0.40, 0.90, 1.25), (0.10, -0.50, 0.85), 22, "L"),          # se vuelve hacia la cabina iluminada
    (93.5, (-0.45, 1.85, 1.20), (-0.20, 0.00, 0.90), 26, "L"),          # sale por el parabrisas mirando dentro
    (96.0, (-33.5, -4.0, 0.9), (-29.2, 0.0, 0.0), 32, "W"),
    (100.0, (-46.0, -16.0, 3.0), (-28.5, 0.0, -0.2), 35, "W"),          # plano final alejándose
]
DUR = GUION[-1][0]
sc.frame_start = 1
sc.frame_end = int(round(DUR * FPS)) + 1


def fr(t):
    return int(round(t * FPS)) + 1


for t, pos, mira, lente, esp in GUION:
    f = fr(t)
    cam.location = Vector(pos) if esp == "W" else L(pos)
    obj.location = Vector(mira) if esp == "W" else L(mira)
    cam_d.lens = lente
    cam.keyframe_insert("location", frame=f)
    obj.keyframe_insert("location", frame=f)
    cam_d.keyframe_insert("lens", frame=f)


def suavizar_curvas(idb):
    ad = idb.animation_data
    if not ad or not ad.action:
        return
    for fc in ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves if hasattr(ad.action, "layers") and ad.action.layers else ad.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
            k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"
        fc.update()


for idb in (cam, obj, cam_d):
    try:
        suavizar_curvas(idb)
    except Exception as e:  # noqa: BLE001
        print("aviso suavizado", e)

# ------------------------------------------------------------------ 7. animación de CAB_Control (vídeo)
def key(prop, valor, t, interp="BEZIER"):
    ctrl[prop] = float(valor)
    ctrl.keyframe_insert(f'["{prop}"]', frame=fr(t) if t < 9000 else int(t))


ESTADO_DIA = dict(Exposicion_EV=0.0, Modo_Cabina=0.0, Intensidad_Integral=0.35, Intensidad_Flood=0.25, Brillo_Pantallas=1.0, Luz_Domo=0.0,
                  Luz_Storm=0.0, Luz_Lectura=0.0, Luz_Sol=1.0, Piel_Oveja=0.0, Gases_1=0.0, Gases_2=0.0, Flaps=0.25,
                  FCU_HDG=270.0, FCU_ALT=15000.0, FCU_SPD=250.0, FCU_HDG_Gestionada=1.0, FCU_ALT_Gestionada=1.0,
                  FCU_SPD_Gestionada=1.0, Vuelo_Altitud=12460.0, Vuelo_Velocidad=252.0, Vuelo_Pitch=2.5, Vuelo_Roll=-8.0,
                  Vuelo_Rumbo=274.0, Vuelo_VS=1200.0, Motor_N1_1=84.6, Motor_N1_2=84.2, Freno_Parking=0.0, Tren=1.0,
                  Puerta=0.0, Asiento_Recorrido=0.0, Guardas=0.0, Bandeja_Rodillas=0.0, Mesa_Capitan=0.0, Mesa_FO=0.0,
                  Pedales=0.0, Prueba_Anunciadores=0.0)
ESTADO_NOCHE = dict(ESTADO_DIA, Modo_Cabina=1.0, Intensidad_Integral=1.1, Intensidad_Flood=0.9, Brillo_Pantallas=0.75,
                    Luz_Domo=0.3, Luz_Lectura=0.6, Luz_Sol=0.0, Exposicion_EV=1.0)
for k, v in ESTADO_DIA.items():
    key(k, v, 0.0)
# POV del capitán: FCU (rumbo tirado y girado, altitud), flaps, gases a TOGA y respuesta del avión
key("FCU_HDG_Gestionada", 1.0, 73.0); key("FCU_HDG_Gestionada", 0.0, 73.6)
key("FCU_HDG", 270.0, 73.6); key("FCU_HDG", 300.0, 76.0)
for i_ in range(7):                     # selector de altitud: saltos de 1000 ft, como el mando real
    key("FCU_ALT", 15000.0 + 1000.0 * i_, 76.2 + 0.36 * i_)
key("FCU_ALT_Gestionada", 1.0, 76.0); key("FCU_ALT_Gestionada", 0.0, 76.3)
key("Flaps", 0.25, 78.5); key("Flaps", 0.5, 79.6)
key("Gases_1", 0.0, 79.8); key("Gases_2", 0.0, 79.8)
key("Gases_1", 1.0, 82.0); key("Gases_2", 1.0, 82.0)
key("Motor_N1_1", 84.6, 80.2); key("Motor_N1_2", 84.2, 80.2)
key("Motor_N1_1", 97.8, 84.0); key("Motor_N1_2", 97.6, 84.0)
key("Vuelo_Rumbo", 274.0, 74.0); key("Vuelo_Rumbo", 296.0, 86.0)
key("Vuelo_Roll", -8.0, 74.0); key("Vuelo_Roll", 18.0, 77.0); key("Vuelo_Roll", 4.0, 86.0)
key("Vuelo_Altitud", 12460.0, 76.5); key("Vuelo_Altitud", 13900.0, 90.0)
key("Vuelo_VS", 1200.0, 79.0); key("Vuelo_VS", 2600.0, 83.0)
key("Vuelo_Pitch", 2.5, 79.0); key("Vuelo_Pitch", 9.5, 83.0)
key("Vuelo_Velocidad", 252.0, 80.0); key("Vuelo_Velocidad", 268.0, 88.0)
# exposición por plano: exterior de día −1,5 EV → interior 0 → noche +1 → exterior de noche +1,5
for t_, ev in ((0.0, -1.5), (14.0, -1.5), (16.5, 0.0), (32.0, 0.0), (34.5, 1.0), (42.5, 1.0), (45.0, 0.0),
                (89.0, 1.0), (91.5, 1.0), (93.5, 1.5)):
    key("Exposicion_EV", ev, t_)
# transición día → noche
for k_ in ("Modo_Cabina", "Intensidad_Integral", "Intensidad_Flood", "Brillo_Pantallas", "Luz_Domo", "Luz_Lectura", "Luz_Sol"):
    key(k_, ESTADO_DIA[k_], 84.5)
    key(k_, ESTADO_NOCHE[k_], 89.0)

# ------------------------------------------------------------------ 8. fotos: una cámara por foto con su estado
FOTOS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fotos.json")))
estados = {"dia": ESTADO_DIA, "noche": ESTADO_NOCHE,
           "dia_oveja": dict(ESTADO_DIA, Piel_Oveja=1.0),
           "noche_storm": dict(ESTADO_NOCHE, Luz_Storm=1.0)}
for f in FOTOS:
    assert set(f.get("extra", {})) <= set(ESTADO_DIA), f"extra sin estado base: {f['id']}"
for i, f in enumerate(FOTOS):
    frame = 9001 + i
    f["frame"] = frame
    cd = bpy.data.cameras.new("CAM_" + f["id"])
    cd.sensor_width = 36.0
    cd.lens = f["lente"]
    cd.clip_start = 0.01
    cd.clip_end = 1500.0
    co = ax.objeto("CAM_" + f["id"], cd, COL_CAM, None)
    p = Vector(f["pos"]) if f.get("mundo") else L(f["pos"])
    t = Vector(f["mira"]) if f.get("mundo") else L(f["mira"])
    co.location = p
    co.rotation_euler = (t - p).to_track_quat("-Z", "Y").to_euler()
    if f.get("roll"):
        co.rotation_euler.rotate_axis("Z", math.radians(f["roll"]))
    est = dict(estados[f.get("estado", "dia")])
    if f.get("mundo"):
        est["Exposicion_EV"] = -1.5 if est["Modo_Cabina"] < 0.5 else 1.5
    if "ev" in f:
        est["Exposicion_EV"] = float(f["ev"])
    for k, v in dict(est, **f.get("extra", {})).items():
        key(k, v, frame)
# el selector de altitud salta de 1000 en 1000 (sin valores intermedios en la ventana del FCU)
_ad = ctrl.animation_data
for fc in (_ad.action.layers[0].strips[0].channelbag(_ad.action_slot).fcurves if _ad.action.layers else _ad.action.fcurves):
    if fc.data_path == '["FCU_ALT"]':
        for k in fc.keyframe_points:
            if fr(76.0) <= k.co.x <= fr(79.0):
                k.interpolation = "CONSTANT"
# las claves de foto son constantes y la última clave del vídeo se mantiene hasta la primera foto
ad = ctrl.animation_data
fcs = ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves if ad.action.layers else ad.action.fcurves
for fc in fcs:
    kps = sorted(fc.keyframe_points, key=lambda k: k.co.x)
    for i, k in enumerate(kps):
        sig = kps[i + 1] if i + 1 < len(kps) else None
        if k.co.x >= 9000 or sig is None or sig.co.x >= 9000:
            k.interpolation = "CONSTANT"
    fc.update()
json.dump(FOTOS, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fotos_resueltas.json"), "w"), indent=1, ensure_ascii=False)
ax.informe(fps=FPS, frames=sc.frame_end, fotos=len(FOTOS))
ax.guardar(a.salida)
