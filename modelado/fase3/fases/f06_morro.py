"""F06 — Exterior del morro (Morro_Exterior y Morro_Ventanas).

- Pintura 100 % procedural que replica la librea de Material_0 (sin textura de imagen) usando las
  coordenadas UV de la malla: vientre azul, filete dorado ancho, filete fino, contorno de la puerta
  delantera con ventanilla/manilla, microvariación, suciedad bajo las ventanas, líneas de panel y
  remaches en bump. Rótulo «AX-620» como geometría proyectada sobre la piel.
- Radomo: misma librea, costura con remaches y tiras desviadoras de rayos segmentadas.
- Sondas detalladas (envuelven las esquemáticas del exterior original, que no se toca): 3 pitots con
  base y zona calefactada, 2 TAT, 3 veletas AoA nuevas, tomas estáticas con anillo rojo y KEEP CLEAR,
  detector de hielo y antenas en la corona.
- Ventanas: un solo juego de limpiaparabrisas con motor carenado, toberas de repelente de lluvia y
  rótulos de ventana de escape.
"""
import sys, os, math, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix
import axlib as ax

a = ax.iniciar("F06")
root = ax.ROOT()
M = root.matrix_world
Mi = M.inverted()
COL_EXT = bpy.data.collections["Morro_Exterior"]
COL_VEN = bpy.data.collections["Morro_Ventanas"]
piel = bpy.data.objects["Morro_Piel"]
radomo = bpy.data.objects["Morro_Radomo"]
CURVAS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "librea_curvas.json")))
S = ax.srgb_a_lineal
AZUL = S((0.0745, 0.1529, 0.2863)) + (1,)
ORO = S((0.7843, 0.6314, 0.2941)) + (1,)
BLANCO = S((0.945, 0.949, 0.941)) + (1,)

# ------------------------------------------------------------------ 0. limpiaparabrisas duplicados (Detalles)
for n in ("CAB_Limpia_Pivote_W1_L", "CAB_Limpia_Pivote_W1_R", "CAB_Limpia_Brazo_W1_L", "CAB_Limpia_Brazo_W1_R"):
    o = bpy.data.objects.get(n)
    if o is not None:
        bpy.data.objects.remove(o, do_unlink=True)

# ------------------------------------------------------------------ 1. grupo de librea (UV → color)
g = bpy.data.node_groups.get("NG_MORRO_Librea")
if g:
    bpy.data.node_groups.remove(g)
g = bpy.data.node_groups.new("NG_MORRO_Librea", "ShaderNodeTree")
ax.marcar(g)
g.interface.new_socket("UV", in_out="INPUT", socket_type="NodeSocketVector")
for nombre, t in (("Color", "NodeSocketColor"), ("Oro", "NodeSocketFloat"), ("Azul", "NodeSocketFloat"), ("Puerta", "NodeSocketFloat")):
    g.interface.new_socket(nombre, in_out="OUTPUT", socket_type=t)
n = ax.Nodos(g)
gi = n.nodo("NodeGroupInput")
go = n.nodo("NodeGroupOutput")
u, v, _ = n.sep(gi.outputs["UV"])
d = n.mat("MINIMUM", v, n.mat("SUBTRACT", 1.0, v))
un = n.mat("DIVIDE", u, CURVAS["u_max"])
fr = []
for k in range(4):
    crudos = CURVAS["curvas"][k]
    v_ref = min(crudos, key=lambda t: abs(t[0] - 0.006))[1]
    pts = [(min(1.0, uu / CURVAS["u_max"]), min(1.0, (v_ref if uu < 0.006 else vv) / 0.5)) for uu, vv in crudos]
    fr.append(n.mat("MULTIPLY", n.curva(un, pts), 0.5))
W = 0.00035
def paso(x, f):
    return n.suave(x, n.mat("SUBTRACT", f, W), n.mat("ADD", f, W))
sa, sb, sc_, sd = (paso(d, f) for f in fr)
azul = n.mat("SUBTRACT", 1.0, sa)
oro = n.mat("ADD", n.mat("MULTIPLY", sa, n.mat("SUBTRACT", 1.0, sb)), n.mat("MULTIPLY", sc_, n.mat("SUBTRACT", 1.0, sd)))
col = n.mezcla(oro, BLANCO, ORO)
col = n.mezcla(azul, col, AZUL)
# puerta delantera (contorno, ventanilla, manilla y recuadro) en metros sobre la piel
KU, KV = 62.7, 18.5
X = n.mat("MULTIPLY", u, KU)
Y = n.mat("MULTIPLY", d, KV)
def rrect(u0, u1, d0, d1, r):
    cx, cy = (u0 + u1) / 2 * KU, (d0 + d1) / 2 * KV
    hx, hy = (u1 - u0) / 2 * KU - r, (d1 - d0) / 2 * KV - r
    qx = n.mat("SUBTRACT", n.mat("ABSOLUTE", n.mat("SUBTRACT", X, cx)), hx)
    qy = n.mat("SUBTRACT", n.mat("ABSOLUTE", n.mat("SUBTRACT", Y, cy)), hy)
    fuera = n.vmat("LENGTH", n.comb(n.mat("MAXIMUM", qx, 0.0), n.mat("MAXIMUM", qy, 0.0)))
    dentro = n.mat("MINIMUM", n.mat("MAXIMUM", qx, qy), 0.0)
    return n.mat("SUBTRACT", n.mat("ADD", fuera, dentro), r)
sdf_p = rrect(0.1136, 0.1314, 0.2028, 0.3088, 0.11)
contorno = n.mat("SUBTRACT", 1.0, n.suave(n.mat("ABSOLUTE", sdf_p), 0.004, 0.0075))
venta = n.mat("SUBTRACT", 1.0, n.suave(rrect(0.1207, 0.1243, 0.2814, 0.2990, 0.07), -0.002, 0.002))
manilla = n.mat("SUBTRACT", 1.0, n.suave(rrect(0.1163, 0.1211, 0.2604, 0.2653, 0.03), -0.002, 0.002))
recu = n.mat("SUBTRACT", 1.0, n.suave(rrect(0.1255, 0.1285, 0.2126, 0.2223, 0.01), -0.002, 0.002))
col = n.mezcla(contorno, col, S((0.586, 0.601, 0.613)) + (1,))
col = n.mezcla(venta, col, S((0.159, 0.194, 0.232)) + (1,))
col = n.mezcla(manilla, col, S((0.501, 0.512, 0.528)) + (1,))
col = n.mezcla(recu, col, S((0.666, 0.681, 0.681)) + (1,))
g.links.new(col, go.inputs["Color"])
g.links.new(oro, go.inputs["Oro"])
g.links.new(azul, go.inputs["Azul"])
g.links.new(n.mat("MAXIMUM", contorno, n.mat("MAXIMUM", venta, manilla)), go.inputs["Puerta"])


# ------------------------------------------------------------------ 2. materiales de pintura
def pintura(nombre, radomo_=False):
    m = ax.material(nombre)
    n = ax.Nodos(m.node_tree)
    uvn = n.nodo("ShaderNodeUVMap"); uvn.uv_map = "UVMap"
    lib = n.grupo("NG_MORRO_Librea", uvn.outputs[0])
    geo = n.nodo("ShaderNodeNewGeometry")
    P = geo.outputs["Position"]
    px, py, pz = n.sep(P)
    r = n.vmat("LENGTH", n.comb(0.0, py, pz))
    th = n.nodo("ShaderNodeMath", operation="ARCTAN2"); n.con(th.inputs[0], pz); n.con(th.inputs[1], py)
    s = n.mat("MULTIPLY", th.outputs[0], r)          # longitud de arco (m)
    def cerca(c, paso, desf, ancho):
        q = n.mat("ADD", c, desf)
        rr = n.mat("SUBTRACT", q, n.mat("MULTIPLY", n.mat("ROUND", n.mat("DIVIDE", q, paso)), paso))
        return n.mat("SUBTRACT", 1.0, n.suave(n.mat("ABSOLUTE", rr), ancho * 0.5, ancho)), rr
    # cuadernas (x = cte, paso 0,533 m desde la costura del radomo) y uniones longitudinales
    lin_x, rx = cerca(px, 0.533, 29.8, 0.0014)
    juntas_t = (0.42, 1.22, 2.05, -0.42, -1.22, -2.05)      # radianes
    lin_t = None
    for t0 in juntas_t:
        dl = n.mat("ABSOLUTE", n.mat("MULTIPLY", n.mat("SUBTRACT", th.outputs[0], t0), r))
        e = n.mat("SUBTRACT", 1.0, n.suave(dl, 0.0007, 0.0014))
        lin_t = e if lin_t is None else n.mat("MAXIMUM", lin_t, e)
    lineas = n.mat("MAXIMUM", lin_x, lin_t)
    # remaches: dos filas a ±16 mm de cada cuaderna (paso 25 mm en arco) y filas en las uniones
    def remache_filas(coord_perp, paso_largo, coord_largo, offs):
        acum = None
        for o in offs:
            q = n.mat("SUBTRACT", coord_perp, o)
            dl = n.mat("SUBTRACT", coord_largo, n.mat("MULTIPLY", n.mat("ROUND", n.mat("DIVIDE", coord_largo, paso_largo)), paso_largo))
            dist = n.vmat("LENGTH", n.comb(q, dl, 0.0))
            e = n.mat("SUBTRACT", 1.0, n.suave(dist, 0.0018, 0.0026))
            acum = e if acum is None else n.mat("MAXIMUM", acum, e)
        return acum
    rem_x = remache_filas(rx, 0.025, s, (0.016, -0.016))
    rem_t = None
    for t0 in juntas_t:
        dl = n.mat("MULTIPLY", n.mat("SUBTRACT", th.outputs[0], t0), r)
        e = remache_filas(dl, 0.025, px, (0.012, -0.012))
        rem_t = e if rem_t is None else n.mat("MAXIMUM", rem_t, e)
    remaches = n.mat("MAXIMUM", rem_x, rem_t)
    if radomo_:
        # sin remaches ni cuadernas en el radomo (composite); tiras desviadoras de rayos
        zc = -1.43
        th2 = n.nodo("ShaderNodeMath", operation="ARCTAN2"); n.con(th2.inputs[0], n.mat("SUBTRACT", pz, zc)); n.con(th2.inputs[1], py)
        rr2 = n.vmat("LENGTH", n.comb(0.0, py, n.mat("SUBTRACT", pz, zc)))
        ang = n.mat("MULTIPLY", th2.outputs[0], 8.0 / (2 * math.pi))
        dang = n.mat("MULTIPLY", n.mat("SUBTRACT", ang, n.mat("ROUND", ang)), n.mat("MULTIPLY", rr2, 2 * math.pi / 8.0))
        boton = n.vmat("LENGTH", n.comb(dang, n.mat("SUBTRACT", px, n.mat("MULTIPLY", n.mat("ROUND", n.mat("DIVIDE", px, 0.009)), 0.009)), 0.0))
        tira = n.mat("MULTIPLY", n.mat("SUBTRACT", 1.0, n.suave(boton, 0.0026, 0.0034)),
                     n.mat("MULTIPLY", n.suave(px, -31.30, -31.25), n.mat("SUBTRACT", 1.0, n.suave(px, -29.90, -29.85))))
        lineas = n.mat("MULTIPLY", lineas, 0.0)
        remaches = tira
    # microvariación, suciedad bajo las ventanas
    tc = n.nodo("ShaderNodeTexCoord").outputs["Object"]
    micro = n.ruido(tc, 3.0, 4.0, 0.6)
    vetas = n.ruido(n.comb(n.mat("MULTIPLY", px, 40.0), n.mat("MULTIPLY", py, 40.0), n.mat("MULTIPLY", pz, 1.5)), 2.0, 5.0, 0.6)
    zona = n.mat("MULTIPLY", n.mat("MULTIPLY", n.suave(pz, -1.05, -0.45), n.mat("SUBTRACT", 1.0, n.suave(pz, -0.25, -0.17))),
                 n.mat("MULTIPLY", n.suave(px, -29.9, -29.5), n.mat("SUBTRACT", 1.0, n.suave(px, -26.2, -25.8))))
    suc = n.mat("MULTIPLY", n.mat("MULTIPLY", zona, n.suave(vetas, 0.45, 0.75)), n.mat("MULTIPLY", n.param("Suciedad"), 0.35))
    base = lib.outputs["Color"]
    base = n.mezcla(n.mat("MULTIPLY", n.mat("SUBTRACT", micro, 0.5), 0.06), base, (0.86, 0.86, 0.86, 1), blend="MULTIPLY")
    base = n.mezcla(suc, base, (0.38, 0.36, 0.33, 1))
    base = n.mezcla(n.mat("MULTIPLY", lineas, 0.55), base, (0.25, 0.26, 0.27, 1))
    base = n.mezcla(n.mat("MULTIPLY", remaches, 0.25), base, (0.62, 0.62, 0.62, 1))
    oro = lib.outputs["Oro"]
    rough = n.mat("ADD", n.mat("ADD", 0.22, n.mat("MULTIPLY", micro, 0.08)), n.mat("MULTIPLY", suc, 0.4))
    metal = n.mat("ADD", n.mat("MULTIPLY", oro, 0.55), n.mat("MULTIPLY", remaches, 0.4 if radomo_ else 0.1))
    bump = n.nodo("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.0006
    n.con(bump.inputs["Height"], n.mat("SUBTRACT", n.mat("MULTIPLY", remaches, 0.6), n.mat("MULTIPLY", lineas, 1.0)))
    sh = ax.principled(n, base=base, rough=rough, metal=metal, normal=bump.outputs[0], coat=0.55, coat_rough=0.06)
    ax.salida_material(n, sh)
    return m


ax.asignar(piel, pintura("MAT_MORRO_Pintura"))
ax.asignar(radomo, pintura("MAT_MORRO_Radomo", radomo_=True))

# ------------------------------------------------------------------ 3. rótulo AX-620 proyectado
me = piel.data
uvs = me.uv_layers["UVMap"].data
mejor = {0: (1e9, None), 1: (1e9, None)}
for poly in me.polygons:
    for li in poly.loop_indices:
        uu, vv = uvs[li].uv
        for lado, vt in ((0, 0.2860), (1, 0.7140)):
            dd = (uu - 0.0893) ** 2 + (vv - vt) ** 2
            if dd < mejor[lado][0]:
                mejor[lado] = (dd, (me.vertices[me.loops[li].vertex_index].co.copy(), poly.normal.copy()))
for lado, (_, (p, nrm)) in mejor.items():
    pw = piel.matrix_world @ p
    nw = (piel.matrix_world.to_3x3() @ nrm).normalized()
    lectura = Vector((1, 0, 0)) if pw.y < 0 else Vector((-1, 0, 0))
    arriba = nw.cross(lectura).normalized() if pw.y < 0 else lectura.cross(nw).normalized()
    if arriba.z < 0:
        arriba = -arriba
    lectura = arriba.cross(nw).normalized()
    R = Matrix((lectura, arriba, nw)).transposed().to_4x4()
    pl = Mi @ (pw + nw * 0.0015)
    ob = ax.rotulos(f"Morro_Rotulo_AX620_{'L' if pw.y < 0 else 'R'}", [((0, 0, 0), "AX-620")], 0.19,
                    "MAT_CAB_Tinta", COL_EXT, "CAB_Root")
    bpy.context.view_layer.update()
    ob.matrix_world = Matrix.Translation(pw + nw * 0.004) @ R
    m = bpy.data.materials.get("MAT_MORRO_Rotulo") or ax.material("MAT_MORRO_Rotulo")
    n = ax.Nodos(m.node_tree)
    m.node_tree.nodes.clear()
    ax.salida_material(n, ax.principled(n, base=AZUL, rough=0.25, coat=0.55, coat_rough=0.06))
    ax.gn_set(ob.modifiers[0], "Material", m)

# ------------------------------------------------------------------ 4. sondas
def superficie(p_local, dir_local):
    """Punto y normal de la piel (Morro_Piel/Radomo) desde un punto exterior hacia dentro."""
    o = M @ Vector(p_local)
    dw = (M.to_3x3() @ Vector(dir_local)).normalized()
    mejor_ = None
    for ob in (piel, radomo):
        inv = ob.matrix_world.inverted()
        ok, loc, nor, idx = ob.ray_cast(inv @ o, (inv.to_3x3() @ dw).normalized(), distance=5.0)
        if ok:
            lw = ob.matrix_world @ loc
            dist = (lw - o).length
            if mejor_ is None or dist < mejor_[0]:
                mejor_ = (dist, lw, (ob.matrix_world.to_3x3() @ nor).normalized())
    if mejor_ is None:
        return None
    return Mi @ mejor_[1], (Mi.to_3x3() @ mejor_[2]).normalized()


m = ax.material("MAT_MORRO_Sonda")
n = ax.Nodos(m.node_tree)
tc = n.nodo("ShaderNodeTexCoord").outputs["Object"]
_, ty, _ = n.sep(tc)
calor = n.suave(ty, 0.10, 0.20)                                   # zona calefactada hacia la punta
col = n.mezcla(calor, (0.80, 0.80, 0.78, 1), (0.62, 0.52, 0.42, 1))
col = n.mezcla(n.mat("MULTIPLY", calor, n.suave(n.ruido(tc, 80.0), 0.4, 0.8)), col, (0.42, 0.40, 0.55, 1))
ax.salida_material(n, ax.principled(n, base=col, rough=n.mat("ADD", 0.18, n.mat("MULTIPLY", calor, 0.12)), metal=1.0))
m = ax.material("MAT_MORRO_Base_Sonda")
n = ax.Nodos(m.node_tree)
ax.salida_material(n, ax.principled(n, base=(0.62, 0.63, 0.64, 1), rough=0.35, metal=1.0))


def montar(nombre, bm, p, nrm, adelante=Vector((0, 1, 0)), mats=("MAT_MORRO_Base_Sonda", "MAT_MORRO_Sonda", "MAT_CAB_Goma")):
    """bm modelado con Z = normal de la piel y +Y = proa; se orienta sobre la superficie."""
    z = nrm.normalized()
    y = (adelante - z * adelante.dot(z)).normalized()
    x = y.cross(z)
    R = Matrix((x, y, z)).transposed().to_4x4()
    ob = ax.objeto(nombre, ax.bm_a_malla(nombre, bm), COL_EXT, "CAB_Root")
    ob.matrix_basis = Matrix.Translation(p) @ R
    ax.asignar(ob, *mats)
    ax.estilo(ob, bisel=0.001, segs=2)
    return ob


def placa_base(bm, radio, tornillos=6):
    ax.cilindro(bm, radio, 0.004, 40, (0, 0, 0.002), mat=0)
    ax.cilindro(bm, radio + 0.004, 0.0012, 40, (0, 0, 0.0004), mat=2)
    for k in range(tornillos):
        a_ = 2 * math.pi * k / tornillos
        ax.cilindro(bm, 0.004, 0.0015, 10, (math.cos(a_) * radio * 0.78, math.sin(a_) * radio * 0.78, 0.0045), mat=0)


# piezas sueltas de la geometría esquemática ajena (no se modifica: se envuelve)
_crudo = bpy.data.objects["Sondas_Limpiaparabrisas"]
_bm = bmesh.new(); _bm.from_mesh(_crudo.data); _bm.verts.ensure_lookup_table()
_visto, PIEZAS = set(), []
for _v in _bm.verts:
    if _v.index in _visto:
        continue
    _pila, _comp = [_v], []
    while _pila:
        _x = _pila.pop()
        if _x.index in _visto:
            continue
        _visto.add(_x.index); _comp.append(_x)
        _pila.extend(e.other_vert(_x) for e in _x.link_edges if e.other_vert(_x).index not in _visto)
    _pts = [Mi @ (_crudo.matrix_world @ q.co) for q in _comp]
    PIEZAS.append((len(_comp), Vector([min(q[i] for q in _pts) for i in range(3)]), Vector([max(q[i] for q in _pts) for i in range(3)])))
_bm.free()


def piezas_cerca(c, radio=0.30):
    c = Vector(c)
    return [pz for pz in PIEZAS if ((pz[1] + pz[2]) / 2 - c).length < radio]


def sonda_envolvente(nombre, centro_aprox, lado, tipo):
    """Sonda detallada construida sobre las cajas de las piezas esquemáticas cercanas."""
    pz = piezas_cerca(centro_aprox)
    bm = ax.bm_nuevo()
    for nv, mn, mx in pz:
        c = (mn + mx) / 2
        ext = mx - mn
        if nv >= 40:      # base: resalte cilíndrico según la normal (X)
            r = max(ext.y, ext.z) / 2 + 0.010
            h = ext.x + 0.010
            xc = c.x
            ax.cilindro(bm, r, h, 40, (xc, c.y, c.z), eje="X", mat=0)
            for k in range(8):
                a_ = 2 * math.pi * k / 8
                ax.cilindro(bm, 0.0038, h + 0.002, 10, (xc, c.y + math.cos(a_) * r * 0.80, c.z + math.sin(a_) * r * 0.80), eje="X", mat=0)
        elif nv >= 24:    # tubo (pitot) o brazo (TAT)
            eje = max(range(3), key=lambda i: ext[i])
            if tipo == "pitot" and eje == 1:
                r = max(ext.x, ext.z) / 2 + 0.005
                L = ext.y + 0.006
                ax.cilindro(bm, r, L, 40, (c.x, c.y, c.z), eje="Y", mat=1)
                ax.cilindro(bm, r, 0.045, 40, (c.x, mx.y + 0.0255, c.z), eje="Y", mat=1, r2=r * 0.55)
                ax.cilindro(bm, r * 0.30, 0.008, 16, (c.x, mx.y + 0.050, c.z), eje="Y", mat=2)
                for k in range(3):
                    ax.cilindro(bm, 0.0014, 0.004, 8, (c.x, mn.y + 0.05 + 0.014 * k, c.z - r), eje="Z", mat=2)
            else:
                ax.caja(bm, (ext.x + 0.012, ext.y + 0.012, ext.z + 0.012), c, mat=1)
                if eje == 1:
                    ax.cilindro(bm, min(ext.x, ext.z) / 2 + 0.002, 0.004, 20, (c.x, mx.y + 0.0075, c.z), eje="Y", mat=2)
        else:             # mástil con perfil aerodinámico (espesor en Z, cuerda en Y)
            cuerda = ext.y + 0.016
            grosor = ext.z + 0.012
            perfil = [(-cuerda / 2, 0.0), (-cuerda * 0.25, -grosor / 2), (cuerda * 0.30, -grosor / 2), (cuerda / 2, 0.0),
                      (cuerda * 0.30, grosor / 2), (-cuerda * 0.25, grosor / 2)]
            caras = ax.prisma(bm, perfil, mn.x - 0.004, mx.x + 0.004, mat=0)
            for v_ in {v for f in caras for v in f.verts}:
                yy, zz, xx = v_.co.x, v_.co.y, v_.co.z
                v_.co = Vector((xx, c.y + yy, c.z + zz))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ob = ax.objeto(nombre, ax.bm_a_malla(nombre, bm), COL_EXT, "CAB_Root")
    ax.asignar(ob, "MAT_MORRO_Base_Sonda", "MAT_MORRO_Sonda", "MAT_CAB_Negro_Profundo")
    ax.estilo(ob, bisel=0.0015, segs=2, angulo=40)
    return ob


sonda_envolvente("Morro_Pitot_1", (-2.40, 1.36, -0.09), -1, "pitot")
sonda_envolvente("Morro_Pitot_2", (2.40, 1.36, -0.09), 1, "pitot")
sonda_envolvente("Morro_Pitot_3", (2.05, 1.36, -1.15), 1, "pitot")
sonda_envolvente("Morro_TAT_1", (2.62, 0.03, -0.69), 1, "tat")
sonda_envolvente("Morro_TAT_2", (-2.67, -0.36, -0.68), -1, "tat")


def aoa(nombre, p_aprox, lado):
    hit = superficie(Vector(p_aprox) + Vector((lado * 0.8, 0, 0)), (-lado, 0, 0))
    p, nrm = hit
    bm = ax.bm_nuevo()
    placa_base(bm, 0.062, 8)
    ax.cilindro(bm, 0.050, 0.005, 40, (0, 0, 0.0055), mat=1)          # disco giratorio
    perfil = [(-0.005, 0.0), (0.005, 0.0), (0.004, -0.11), (-0.004, -0.11)]
    caras = ax.prisma(bm, [(-0.004, -0.02), (0.004, -0.02), (0.003, 0.03), (-0.003, 0.03)], 0.008, 0.095, mat=1)
    for v in {v for f in caras for v in f.verts}:
        t = (v.co.z - 0.008) / 0.087
        v.co.y -= t * 0.07                                             # flecha de la veleta hacia popa
    return montar(nombre, bm, p, nrm)


aoa("Morro_AoA_1", (-2.55, 0.85, -0.55), -1)
aoa("Morro_AoA_3", (-2.40, 0.55, -1.15), -1)
aoa("Morro_AoA_2", (2.55, 0.85, -0.55), 1)

# tomas estáticas con anillo rojo y KEEP CLEAR
mr = ax.material("MAT_MORRO_Rojo_Anillo")
n = ax.Nodos(mr.node_tree)
ax.salida_material(n, ax.principled(n, base=S((0.75, 0.05, 0.04)) + (1,), rough=0.3, coat=0.5))
for lado, s in (("L", -1), ("R", 1)):
    for k, y in enumerate((-0.45, -0.70)):
        p, nrm = superficie((s * 3.2, y, -0.30), (-s, 0, 0))
        bm = ax.bm_nuevo()
        ax.cilindro(bm, 0.038, 0.0016, 48, (0, 0, 0.0008), mat=0)
        for j in range(7):
            a_ = 2 * math.pi * j / 6
            r_ = 0.0 if j == 6 else 0.014
            ax.cilindro(bm, 0.0022, 0.0004, 10, (math.cos(a_) * r_, math.sin(a_) * r_, 0.0018), mat=3)
        r1 = bmesh.ops.create_circle(bm, cap_ends=False, segments=64, radius=0.070)
        r0 = bmesh.ops.create_circle(bm, cap_ends=False, segments=64, radius=0.052)
        for vv in r1["verts"] + r0["verts"]:
            vv.co.z = 0.0006
        bmesh.ops.bridge_loops(bm, edges=[e for e in bm.edges if all(abs(v.co.z - 0.0006) < 1e-6 for v in e.verts)])
        for f in bm.faces:
            if all(abs(vv.co.z - 0.0006) < 1e-6 for vv in f.verts) and len(f.verts) == 4:
                f.material_index = 2
        ob = montar(f"Morro_Toma_Estatica_{lado}{k + 1}", bm, p, nrm,
                    mats=("MAT_MORRO_Base_Sonda", "MAT_MORRO_Sonda", "MAT_MORRO_Rojo_Anillo", "MAT_CAB_Negro_Profundo"))
        ob.modifiers.clear()
        ax.rotulos(f"Morro_Toma_Estatica_{lado}{k + 1}_Txt", [((0, 0.088, 0.0012), "KEEP CLEAR"), ((0, -0.088, 0.0012), "STATIC PORT")],
                   0.016, mr, COL_EXT, ob, giros=[0.0, 0.0])
# detector de hielo
p, nrm = superficie((-3.0, 1.55, -0.95), (1, 0, 0))
bm = ax.bm_nuevo()
placa_base(bm, 0.05, 6)
ax.cilindro(bm, 0.008, 0.055, 20, (0, 0, 0.032), mat=1)
ax.esfera(bm, 0.010, (0, 0, 0.061), 16, 8, mat=1)
montar("Morro_Detector_Hielo", bm, p, nrm)
# antenas en la corona
for nombre, y, tipo in (("Morro_Antena_VHF1", -1.10, "pala"), ("Morro_Antena_GPS", -0.20, "domo"), ("Morro_Antena_ATC", 0.35, "pala_peq")):
    p, nrm = superficie((0.0, y, 5.0), (0, 0, -1))
    bm = ax.bm_nuevo()
    if tipo == "domo":
        ax.cilindro(bm, 0.085, 0.004, 48, (0, 0, 0.002), mat=0)
        ax.esfera(bm, 0.07, (0, 0, 0.004), 32, 12, mat=1, escala=(1, 1, 0.32))
        mats = ("MAT_MORRO_Base_Sonda", "MAT_CAB_Plastico_Blanco", "MAT_CAB_Goma")
    else:
        h = 0.32 if tipo == "pala" else 0.16
        placa_base(bm, 0.0, 0) if False else None
        ax.caja(bm, (0.06, 0.30 if tipo == "pala" else 0.16, 0.006), (0, 0, 0.003), mat=0)
        perfil = [(0.0, 0.11), (0.008, 0.06), (0.009, -0.05), (0.0, -0.10), (-0.009, -0.05), (-0.008, 0.06)]
        caras = ax.prisma(bm, perfil, 0.004, h, mat=1)
        for vv in {v for f in caras for v in f.verts}:
            t = (vv.co.z - 0.004) / (h - 0.004)
            vv.co.y = vv.co.y * (1 - 0.45 * t) - t * 0.07
        mats = ("MAT_MORRO_Base_Sonda", "MAT_MORRO_Pintura", "MAT_CAB_Goma")
    montar(nombre, bm, p, nrm, mats=mats)

# ------------------------------------------------------------------ 5. ventanas: motor carenado, toberas, rótulos de escape
for lado, s in (("L", -1), ("R", 1)):
    p, nrm = superficie((s * 1.02, 1.95, 1.2), (0, -0.3, -1))
    bm = ax.bm_nuevo()
    ax.esfera(bm, 0.055, (0, 0.02, 0.0), 32, 16, mat=0, escala=(0.85, 1.7, 0.42))
    montar(f"Morro_Limpia_Motor_{lado}", bm, p, nrm, mats=("MAT_MORRO_Pintura",))
    for k, dx in enumerate((-0.30, -0.55)):
        p2, n2 = superficie((s * abs(dx), 2.35, 0.62), (0, -0.55, -0.45))
        bm = ax.bm_nuevo()
        ax.cilindro(bm, 0.009, 0.004, 16, (0, 0, 0.002), mat=0)
        ax.cilindro(bm, 0.0035, 0.022, 12, (0, -0.006, 0.010), eje="Y", mat=1)
        montar(f"Morro_Tobera_Repelente_{lado}{k + 1}", bm, p2, n2, adelante=Vector((0, -1, 0)))
    # rótulos de la ventana de escape (W2 deslizante)
    p, nrm = superficie((s * 3.2, 1.05, 0.40), (-s, 0, 0))
    lectura = Vector((0, -s, 0))
    z = nrm
    y = Vector((0, 0, 1)) - z * z.z
    y.normalize()
    x = y.cross(z)
    ob = ax.rotulos(f"Morro_Rotulo_Escape_{lado}", [((0, 0.012, 0), "EMERGENCY EXIT"), ((0, -0.016, 0), "ESCAPE ROPE INSIDE")],
                    0.022, mr, COL_VEN, "CAB_Root")
    ob.matrix_basis = Matrix.Translation(p + nrm * 0.0012) @ Matrix((x, y, z)).transposed().to_4x4()

ax.informe(ok=True)
ax.guardar(a.salida)
