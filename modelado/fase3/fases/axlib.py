"""Utilidades comunes de las fases de construcción del AX620 (Fase 3, cabina y morro).

Convenciones del proyecto:
- Marco local de CAB_Root: X = lado del primer oficial, Y = adelante, Z = arriba; Z=0 suelo de cabina.
- Objetos nuevos: prefijo CAB_, nombres en castellano, propiedad "ax_fase" con la fase que los creó
  (las fases son idempotentes: al empezar borran lo que crearon en una ejecución anterior).
- Estilo de modificadores existente: BEVEL (ángulo) → [GN_CAB_Dzus_Esquinas] → WEIGHTED_NORMAL →
  GN_CAB_Atributos.
"""
import bpy
import bmesh
import math
import sys
import os
import json
import argparse
from mathutils import Vector, Matrix, Euler

FASE = None
SX = Matrix.Scale(-1.0, 4, (1.0, 0.0, 0.0))


# ----------------------------------------------------------------------------- ciclo de fase

def args_fase():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--extra", default="")
    return ap.parse_args(argv)


def iniciar(nombre):
    global FASE
    FASE = nombre
    a = args_fase()
    borrar_fase(nombre)
    print(f"[{nombre}] inicio", flush=True)
    return a


def guardar(ruta):
    for ob in bpy.data.objects:          # nada seleccionado ni activo raro
        ob.select_set(False)
    bpy.ops.wm.save_as_mainfile(filepath=ruta, compress=True, relative_remap=True)
    print(f"[{FASE}] guardado {ruta}", flush=True)


def borrar_fase(nombre):
    obs = [o for o in bpy.data.objects if o.get("ax_fase") == nombre]
    for o in obs:
        datos = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if datos is not None and datos.users == 0:
            try:
                getattr(bpy.data, {"MESH": "meshes", "CURVE": "curves", "CAMERA": "cameras",
                                   "LIGHT": "lights"}.get(datos.id_type, "meshes")).remove(datos)
            except Exception:
                pass
    for coleccion in (bpy.data.materials, bpy.data.node_groups):
        for idb in [i for i in coleccion if i.get("ax_fase") == nombre]:
            coleccion.remove(idb)
    for c in [c for c in bpy.data.collections if c.get("ax_fase") == nombre]:
        bpy.data.collections.remove(c)


def marcar(idb):
    idb["ax_fase"] = FASE
    return idb


# ----------------------------------------------------------------------------- escena

def ROOT():
    return bpy.data.objects["CAB_Root"]


def CTRL():
    return bpy.data.objects["CAB_Control"]


def coleccion(nombre, padre="CABINA"):
    c = bpy.data.collections.get(nombre)
    if c is None:
        c = bpy.data.collections.new(nombre)
        marcar(c)
        p = bpy.data.collections[padre] if isinstance(padre, str) else padre
        p.children.link(c)
    return c


def objeto(nombre, datos, col, padre="CAB_Root", loc=(0, 0, 0), rot=(0, 0, 0), esc=(1, 1, 1)):
    viejo = bpy.data.objects.get(nombre)
    if viejo is not None:
        if viejo.get("ax_fase") is None:
            raise RuntimeError(f"Ya existe un objeto original llamado {nombre}")
        bpy.data.objects.remove(viejo, do_unlink=True)
    ob = bpy.data.objects.new(nombre, datos)
    (bpy.data.collections[col] if isinstance(col, str) else col).objects.link(ob)
    if padre:
        ob.parent = bpy.data.objects[padre] if isinstance(padre, str) else padre
        ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.location = loc
    ob.rotation_euler = rot
    ob.scale = esc
    marcar(ob)
    return ob


def vacio(nombre, col, padre="CAB_Root", loc=(0, 0, 0), rot=(0, 0, 0), tam=0.02, tipo="PLAIN_AXES"):
    ob = objeto(nombre, None, col, padre, loc, rot)
    ob.empty_display_size = tam
    ob.empty_display_type = tipo
    return ob


def mat(nombre):
    return bpy.data.materials[nombre]


def asignar(ob, *mats):
    ob.data.materials.clear()
    for m in mats:
        ob.data.materials.append(mat(m) if isinstance(m, str) else m)


def suavizar(me):
    me.shade_smooth()


# ----------------------------------------------------------------------------- bmesh

def bm_nuevo():
    return bmesh.new()


def bm_a_malla(nombre, bm, suave=True):
    me = bpy.data.meshes.new(nombre)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]) if False else None
    bm.to_mesh(me)
    bm.free()
    if suave:
        me.shade_smooth()
    return me


def caja(bm, tam, centro=(0, 0, 0), mat=0):
    sx, sy, sz = tam
    r = bmesh.ops.create_cube(bm, size=1.0)
    vs = r["verts"]
    for v in vs:
        v.co = Vector((v.co.x * sx + centro[0], v.co.y * sy + centro[1], v.co.z * sz + centro[2]))
    caras = {f for v in vs for f in v.link_faces}
    for f in caras:
        f.material_index = mat
    return list(caras)


def cilindro(bm, r, h, segs=24, centro=(0, 0, 0), eje="Z", mat=0, r2=None, tapas=True):
    """Cilindro (o tronco de cono con r2) centrado; eje X/Y/Z."""
    res = bmesh.ops.create_cone(bm, cap_ends=tapas, cap_tris=False, segments=segs,
                                radius1=r, radius2=r if r2 is None else r2, depth=h)
    vs = res["verts"]
    rotm = {"Z": Matrix.Identity(3), "X": Matrix.Rotation(math.radians(90), 3, "Y"),
            "Y": Matrix.Rotation(math.radians(-90), 3, "X")}[eje]
    for v in vs:
        v.co = rotm @ v.co + Vector(centro)
    caras = {f for v in vs for f in v.link_faces}
    for f in caras:
        f.material_index = mat
    return list(caras)


def esfera(bm, r, centro=(0, 0, 0), u=16, v=10, mat=0, escala=(1, 1, 1)):
    res = bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r)
    for vv in res["verts"]:
        vv.co = Vector((vv.co.x * escala[0], vv.co.y * escala[1], vv.co.z * escala[2])) + Vector(centro)
    caras = {f for vv in res["verts"] for f in vv.link_faces}
    for f in caras:
        f.material_index = mat
    return list(caras)


def prisma(bm, pts2d, z0, z1, mat=0, tapas=True):
    """Extruye un polígono XY (antihorario) entre z0 y z1."""
    ab = [bm.verts.new((x, y, z0)) for x, y in pts2d]
    ar = [bm.verts.new((x, y, z1)) for x, y in pts2d]
    caras = []
    n = len(pts2d)
    for i in range(n):
        j = (i + 1) % n
        caras.append(bm.faces.new((ab[i], ab[j], ar[j], ar[i])))
    if tapas:
        caras.append(bm.faces.new(list(reversed(ab))))
        caras.append(bm.faces.new(ar))
    for f in caras:
        f.material_index = mat
    return caras


def rect_redondeado(w, h, r, segs=4, cx=0.0, cy=0.0):
    """Contorno antihorario de un rectángulo de esquinas redondeadas."""
    r = min(r, w / 2 - 1e-5, h / 2 - 1e-5)
    pts = []
    for (ox, oy, a0) in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                         (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(segs + 1):
            a = math.radians(a0 + 90 * k / segs)
            pts.append((cx + ox + r * math.cos(a), cy + oy + r * math.sin(a)))
    return pts


def transformar(bm, caras_o_verts, M):
    vs = set()
    for x in caras_o_verts:
        if isinstance(x, bmesh.types.BMFace):
            vs.update(x.verts)
        else:
            vs.add(x)
    for v in vs:
        v.co = M @ v.co


# ----------------------------------------------------------------------------- modificadores

def estilo(ob, bisel=0.0012, segs=2, angulo=35.0, dzus=None, atributos=True, wn=True, subsurf=0,
           solidify=0.0, perfil=0.6):
    if solidify:
        m = ob.modifiers.new("Solidify", "SOLIDIFY")
        m.thickness = solidify
        m.offset = -1.0
    if bisel:
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = bisel
        m.segments = segs
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(angulo)
        m.profile = perfil
        m.use_clamp_overlap = True
        m.miter_outer = "MITER_ARC"
        m.harden_normals = False
    if subsurf:
        m = ob.modifiers.new("Subdivision", "SUBSURF")
        m.levels = 1
        m.render_levels = subsurf
    if dzus:
        gn(ob, "GN_CAB_Dzus_Esquinas", Objeto="CAB_Fuente_Dzus", **dzus)
    if wn:
        m = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
        m.mode = "FACE_AREA"
        m.weight = 50
        m.keep_sharp = True
        m.thresh = 0.01
    if atributos:
        gn(ob, "GN_CAB_Atributos")
    return ob


def _socket(grupo, nombre):
    for it in grupo.interface.items_tree:
        if it.item_type == "SOCKET" and it.in_out == "INPUT" and it.name == nombre:
            return it
    raise KeyError(f"{grupo.name} no tiene la entrada {nombre}")


def gn(ob, grupo, nombre=None, **vals):
    g = bpy.data.node_groups[grupo] if isinstance(grupo, str) else grupo
    m = ob.modifiers.new(nombre or g.name, "NODES")
    m.node_group = g
    for k, v in vals.items():
        gn_set(m, k, v)
    return m


def gn_set(m, nombre, valor):
    it = _socket(m.node_group, nombre)
    pi = getattr(m.properties.inputs, it.identifier)
    t = it.socket_type
    if t == "NodeSocketObject" and isinstance(valor, str):
        valor = bpy.data.objects[valor]
    elif t == "NodeSocketMaterial" and isinstance(valor, str):
        valor = bpy.data.materials[valor]
    elif t == "NodeSocketCollection" and isinstance(valor, str):
        valor = bpy.data.collections[valor]
    pi.value = valor


def gn_get(m, nombre):
    it = _socket(m.node_group, nombre)
    return getattr(m.properties.inputs, it.identifier).value


def gn_ruta(m, nombre):
    """Ruta RNA de una entrada del modificador GN (para drivers)."""
    it = _socket(m.node_group, nombre)
    return f'modifiers["{m.name}"].properties.inputs.{it.identifier}.value'


# ----------------------------------------------------------------------------- drivers

def driver(idb, ruta, expr, variables, indice=-1, objetivo=None):
    """variables: {nombre: propiedad de CAB_Control} o {nombre: (id, data_path)}."""
    fc = idb.driver_add(ruta, indice) if indice >= 0 else idb.driver_add(ruta)
    for mod in list(fc.modifiers):
        fc.modifiers.remove(mod)
    d = fc.driver
    d.type = "SCRIPTED"
    for v in list(d.variables):
        d.variables.remove(v)
    for nombre, prop in variables.items():
        v = d.variables.new()
        v.name = nombre
        v.type = "SINGLE_PROP"
        if isinstance(prop, tuple):
            v.targets[0].id_type = prop[0].id_type if hasattr(prop[0], "id_type") else "OBJECT"
            v.targets[0].id = prop[0]
            v.targets[0].data_path = prop[1]
        else:
            v.targets[0].id = objetivo or CTRL()
            v.targets[0].data_path = f'["{prop}"]'
    d.expression = expr
    return fc


def propiedad(nombre, valor, minimo, maximo, desc):
    c = CTRL()
    c[nombre] = float(valor)
    ui = c.id_properties_ui(nombre)
    ui.update(min=minimo, max=maximo, soft_min=minimo, soft_max=maximo, description=desc)
    # también como salida de NG_CAB_Parametros para los materiales
    g = bpy.data.node_groups["NG_CAB_Parametros"]
    if not any(it.item_type == "SOCKET" and it.in_out == "OUTPUT" and it.name == nombre for it in g.interface.items_tree):
        g.interface.new_socket(nombre, in_out="OUTPUT", socket_type="NodeSocketFloat")
        n = g.nodes.new("ShaderNodeValue")
        n.name = n.label = f"P_{nombre}"
        n.location = (0, -60 * len(g.nodes))
        out = next(x for x in g.nodes if x.type == "GROUP_OUTPUT")
        g.links.new(n.outputs[0], out.inputs[nombre])
        driver(g, f'nodes["P_{nombre}"].outputs[0].default_value', "p", {"p": nombre})


def limitar_rot(ob, x=None, y=None, z=None):
    c = ob.constraints.new("LIMIT_ROTATION")
    c.owner_space = "LOCAL"
    c.use_transform_limit = True
    for eje, lim in (("x", x), ("y", y), ("z", z)):
        if lim is not None:
            setattr(c, f"use_limit_{eje}", True)
            setattr(c, f"min_{eje}", math.radians(lim[0]))
            setattr(c, f"max_{eje}", math.radians(lim[1]))
    return c


def limitar_loc(ob, x=None, y=None, z=None):
    c = ob.constraints.new("LIMIT_LOCATION")
    c.owner_space = "LOCAL"
    c.use_transform_limit = True
    for eje, lim in (("x", x), ("y", y), ("z", z)):
        if lim is not None:
            setattr(c, f"use_min_{eje}", True)
            setattr(c, f"use_max_{eje}", True)
            setattr(c, f"min_{eje}", lim[0])
            setattr(c, f"max_{eje}", lim[1])
    return c


# ----------------------------------------------------------------------------- rótulos

def puntos(nombre, coords, col, padre, loc=(0, 0, 0), rot=(0, 0, 0), atributos=None):
    """Malla de vértices sueltos con atributos de punto opcionales {nombre: (tipo, [valores])}."""
    me = bpy.data.meshes.new(nombre)
    me.from_pydata([tuple(c) for c in coords], [], [])
    for an, (tipo, vals) in (atributos or {}).items():
        a = me.attributes.new(an, tipo, "POINT")
        if tipo == "FLOAT_VECTOR":
            a.data.foreach_set("vector", [x for v in vals for x in v])
        elif tipo == "FLOAT_COLOR":
            a.data.foreach_set("color", [x for v in vals for x in v])
        else:
            a.data.foreach_set("value", list(vals))
    return objeto(nombre, me, col, padre, loc, rot)


def rotulos(nombre, items, tamano, material, col, padre, loc=(0, 0, 0), rot=(0, 0, 0),
            alin_izq=False, grosor=0.0, giros=None):
    """items: [((x, y, z), "TEXTO"), ...] en el marco del padre (o de loc/rot)."""
    items = [(p, t) for p, t in items if t]
    if not items:
        return None
    attrs = {"cab_giro": ("FLOAT", [math.radians(g) for g in giros])} if giros else None
    ob = puntos(nombre, [p for p, _ in items], col, padre, loc, rot, attrs)
    gn(ob, "GN_CAB_Rotulos", Lista="|".join(t for _, t in items), Tamano=tamano, Grosor=grosor,
       Material=material, Alineacion_Izq=alin_izq)
    return ob


# ----------------------------------------------------------------------------- espejado (lado FO)

def espejar_datos(datos):
    """Refleja en X local los datos (malla o curva) conservando la orientación de las caras."""
    if isinstance(datos, bpy.types.Mesh):
        bm = bmesh.new()
        bm.from_mesh(datos)
        for v in bm.verts:
            v.co.x = -v.co.x
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:], flip_multires=False)
        bm.to_mesh(datos)
        bm.free()
    elif isinstance(datos, bpy.types.Curve):
        for sp in datos.splines:
            for p in sp.bezier_points:
                for attr in ("co", "handle_left", "handle_right"):
                    c = getattr(p, attr)
                    setattr(p, attr, Vector((-c.x, c.y, c.z)))
            for p in sp.points:
                p.co = (-p.co[0], p.co[1], p.co[2], p.co[3])


# ----------------------------------------------------------------------------- nodos

class Nodos:
    """Constructor compacto de árboles de nodos (shader o geometría).

    n = Nodos(arbol); s = n.mat("MULTIPLY", a, 2.0) → devuelve el socket de salida.
    Las entradas pueden ser sockets, números, tuplas o None.
    """

    def __init__(self, arbol, limpiar=False):
        self.t = arbol
        self.x = 0
        if limpiar:
            arbol.nodes.clear()

    def nodo(self, tipo, **props):
        n = self.t.nodes.new(tipo)
        n.location = (self.x, 0)
        self.x += 40
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def con(self, entrada, valor):
        if valor is None:
            return
        if isinstance(valor, bpy.types.NodeSocket):
            self.t.links.new(valor, entrada)
        else:
            try:
                entrada.default_value = valor
            except (TypeError, ValueError):
                entrada.default_value = tuple(valor) if hasattr(valor, "__len__") else (valor,) * len(entrada.default_value)

    def entradas(self, n, *args, **kw):
        ins = [s for s in n.inputs if s.enabled]
        for s, v in zip(ins, args):
            self.con(s, v)
        for k, v in kw.items():
            self.con(n.inputs[k], v)
        return n

    def mat(self, op, a=None, b=None, c=None, clamp=False):
        es_geo = self.t.bl_idname == "GeometryNodeTree"
        n = self.nodo("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.con(n.inputs[0], a)
        self.con(n.inputs[1], b)
        self.con(n.inputs[2], c)
        return n.outputs[0]

    def vmat(self, op, a=None, b=None, c=None, salida=0):
        n = self.nodo("ShaderNodeVectorMath", operation=op)
        self.con(n.inputs[0], a)
        self.con(n.inputs[1], b)
        if c is not None:
            self.con(n.inputs[2], c)
        if op in ("DOT_PRODUCT", "DISTANCE", "LENGTH"):
            return n.outputs["Value"]
        return n.outputs["Vector"]

    def rango(self, v, a0, a1, b0=0.0, b1=1.0, clamp=True, interp="LINEAR"):
        n = self.nodo("ShaderNodeMapRange", interpolation_type=interp, clamp=clamp)
        self.entradas(n, v, a0, a1, b0, b1)
        return n.outputs[0]

    def suave(self, v, a0, a1):
        return self.rango(v, a0, a1, 0.0, 1.0, True, "SMOOTHSTEP")

    def mezcla(self, f, a, b, tipo="RGBA", blend="MIX", clamp=True):
        n = self.nodo("ShaderNodeMix", data_type=tipo, blend_type=blend, clamp_factor=clamp)
        if tipo == "RGBA":
            self.con(n.inputs[0], f)
            self.con(n.inputs[6], a)
            self.con(n.inputs[7], b)
            return n.outputs[2]
        if tipo == "FLOAT":
            self.con(n.inputs[0], f)
            self.con(n.inputs[2], a)
            self.con(n.inputs[3], b)
            return n.outputs[0]
        self.con(n.inputs[0], f)
        self.con(n.inputs[4], a)
        self.con(n.inputs[5], b)
        return n.outputs[1]

    def sep(self, v):
        n = self.nodo("ShaderNodeSeparateXYZ")
        self.con(n.inputs[0], v)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def comb(self, x=0.0, y=0.0, z=0.0):
        n = self.nodo("ShaderNodeCombineXYZ")
        self.entradas(n, x, y, z)
        return n.outputs[0]

    def rgb(self, c):
        n = self.nodo("ShaderNodeRGB")
        n.outputs[0].default_value = (c[0], c[1], c[2], 1.0)
        return n.outputs[0]

    def valor(self, v):
        n = self.nodo("ShaderNodeValue")
        n.outputs[0].default_value = v
        return n.outputs[0]

    def ruido(self, v, escala, detalle=2.0, rugosidad=0.5, dim="3D", salida="Fac", w=None, distorsion=0.0):
        n = self.nodo("ShaderNodeTexNoise", noise_dimensions=dim)
        self.con(n.inputs["Vector"], v)
        if w is not None:
            self.con(n.inputs["W"], w)
        self.con(n.inputs["Scale"], escala)
        self.con(n.inputs["Detail"], detalle)
        self.con(n.inputs["Roughness"], rugosidad)
        self.con(n.inputs["Distortion"], distorsion)
        return n.outputs[salida]

    def voronoi(self, v, escala, feature="F1", salida="Distance", aleatorio=1.0, dist="EUCLIDEAN"):
        n = self.nodo("ShaderNodeTexVoronoi", feature=feature, distance=dist)
        self.con(n.inputs["Vector"], v)
        self.con(n.inputs["Scale"], escala)
        self.con(n.inputs["Randomness"], aleatorio)
        return n.outputs[salida]

    def grupo(self, nombre, *args, **kw):
        n = self.nodo("ShaderNodeGroup" if self.t.bl_idname == "ShaderNodeTree" else "GeometryNodeGroup")
        n.node_tree = bpy.data.node_groups[nombre]
        self.entradas(n, *args, **kw)
        return n

    def attr(self, nombre, tipo="GEOMETRY", salida="Fac"):
        n = self.nodo("ShaderNodeAttribute", attribute_name=nombre, attribute_type=tipo)
        return n.outputs[salida]

    def param(self, nombre):
        if not hasattr(self, "_param"):
            self._param = self.grupo("NG_CAB_Parametros")
        return self._param.outputs[nombre]

    def curva(self, v, pts, lineal=False):
        n = self.nodo("ShaderNodeFloatCurve")
        self.con(n.inputs["Value"], v)
        c = n.mapping.curves[0]
        while len(c.points) > 2:
            c.points.remove(c.points[-1])
        c.points[0].location = pts[0]
        c.points[1].location = pts[-1]
        for p in pts[1:-1]:
            c.points.new(*p)
        for p in c.points:
            p.handle_type = "VECTOR" if lineal else "AUTO_CLAMPED"
        n.mapping.clip_min_x, n.mapping.clip_max_x = 0.0, 1.0
        n.mapping.use_clip = False
        n.mapping.update()
        return n.outputs[0]


def material(nombre, reemplazar=True):
    m = bpy.data.materials.get(nombre)
    if m is not None and reemplazar:
        m.node_tree.nodes.clear()
    elif m is None:
        m = bpy.data.materials.new(nombre)
        m.use_nodes = True
        m.node_tree.nodes.clear()
        marcar(m)
    return m


def salida_material(n, superficie, desplazamiento=None, volumen=None):
    o = n.nodo("ShaderNodeOutputMaterial")
    n.con(o.inputs["Surface"], superficie)
    if desplazamiento is not None:
        n.con(o.inputs["Displacement"], desplazamiento)
    return o


def principled(n, base=None, rough=0.5, metal=0.0, normal=None, emision=None, fuerza_em=0.0,
               transmision=0.0, ior=1.45, alpha=1.0, coat=0.0, coat_rough=0.03, spec=0.5):
    p = n.nodo("ShaderNodeBsdfPrincipled")
    n.con(p.inputs["Base Color"], base if base is not None else (0.8, 0.8, 0.8, 1))
    n.con(p.inputs["Roughness"], rough)
    n.con(p.inputs["Metallic"], metal)
    n.con(p.inputs["IOR"], ior)
    n.con(p.inputs["Alpha"], alpha)
    n.con(p.inputs["Transmission Weight"], transmision)
    n.con(p.inputs["Coat Weight"], coat)
    n.con(p.inputs["Coat Roughness"], coat_rough)
    n.con(p.inputs["Specular IOR Level"], spec)
    if normal is not None:
        n.con(p.inputs["Normal"], normal)
    if emision is not None:
        n.con(p.inputs["Emission Color"], emision)
        n.con(p.inputs["Emission Strength"], fuerza_em)
    return p.outputs[0]


def srgb_a_lineal(c):
    def f(x):
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return tuple(f(x) for x in c)


def informe(**kw):
    print("[INFORME] " + json.dumps(kw, ensure_ascii=False), flush=True)
