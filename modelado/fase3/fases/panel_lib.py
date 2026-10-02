"""Constructor de paneles de cabina (overhead, pedestal, laterales) con el sistema existente.

Un Panel es una placa con su marco local (origen en el centro de la cara, X derecha, Y = arriba
del texto, Z saliendo de la cara). Los controles se añaden en milímetros y se materializan al
llamar a cerrar():
- pulsadores Airbus: un objeto por pulsador (vértice + GN_CAB_Instancias_Puntos del cuerpo +
  GN_CAB_Pulsador_Leyendas), con propiedad cab_estado (bit 0 = leyenda superior, bit 1 = inferior);
- palancas, bases, rotativos, mandos y guardas: nubes de puntos por panel con GN_CAB_Instancias_Puntos
  (cab_normal para la inclinación, cab_giro para la orientación);
- rótulos: GN_CAB_Rotulos (material MAT_CAB_Etiqueta, retroiluminado por Intensidad_Integral);
- líneas de sinóptico: tiras de malla serigrafiadas.
"""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix, Euler
import axlib as ax

MM = 0.001
AMB, BLA, AZU, VER = 0.0, 1.0, 2.0, 3.0
COL = {"A": AMB, "W": BLA, "B": AZU, "G": VER}


def _bits(sup_on, inf_on):
    return float((1 if sup_on else 0) + (2 if inf_on else 0))


class Panel:
    def __init__(self, nombre, col, padre, loc, rot, ancho, alto, grosor=0.008, material="MAT_CAB_Panel",
                 dzus=True, semilla=1, prefijo="CAB_OH_", existente=None):
        self.nombre = nombre
        self.pref = prefijo + nombre
        self.col = col
        self.w, self.h = ancho, alto
        if existente is not None:      # controles nuevos sobre una placa original
            self.placa = bpy.data.objects[existente] if isinstance(existente, str) else existente
        else:
            bm = ax.bm_nuevo()
            ax.caja(bm, (ancho, alto, grosor), (0, 0, -grosor / 2))
            self.placa = ax.objeto(self.pref, ax.bm_a_malla(self.pref, bm), col, padre, loc, rot)
            ax.asignar(self.placa, material)
            ax.estilo(self.placa, bisel=0.0012, dzus=dict(Margen=0.0085, Escala=0.8, Semilla=semilla) if dzus else None)
        self.rot_peq, self.rot_tit, self.rot_mini = [], [], []
        self.lineas = []
        self.pts = {}           # fuente → [(pos, normal, giro, escala)]
        self.n_pb = 0
        self.pbs = []

    # ---------------------------------------------------------------- utilidades
    def P(self, x, y, z=0.0):
        return Vector((x * MM, y * MM, z))

    def texto(self, x, y, t, tam="peq", giro=0.0, z=0.0):
        if not t:
            return
        dest = {"peq": self.rot_peq, "tit": self.rot_tit, "mini": self.rot_mini}[tam]
        dest.append((self.P(x, y, z), t, giro))

    def titulo(self, x, y, t, ancho_linea=None):
        """Título con raya a ambos lados (estilo Airbus)."""
        self.texto(x, y, t, "tit")
        if ancho_linea:
            mitad = len(t) * 2.2 + 3.0
            self.linea([(x - ancho_linea / 2, y), (x - mitad, y)])
            self.linea([(x + mitad, y), (x + ancho_linea / 2, y)])

    def linea(self, pts, ancho=0.6):
        self.lineas.append(([(px * MM, py * MM) for px, py in pts], ancho * MM))

    def caja_linea(self, x0, y0, x1, y1, ancho=0.5):
        self.linea([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], ancho)

    def instancia(self, fuente, x, y, normal=(0, 0, 1), giro=0.0, escala=1.0, z=0.0):
        self.pts.setdefault(fuente, []).append((self.P(x, y, z), Vector(normal).normalized(), math.radians(giro), escala))

    # ---------------------------------------------------------------- controles
    def pb(self, x, y, nombre="", sup="FAULT", inf="OFF", csup="A", cinf="W", sup_on=False, inf_on=False,
           guarda=None, etiqueta_arriba=True, id_=None):
        """Pulsador Airbus de leyenda doble. guarda: None | 'roja' | 'clara'."""
        self.n_pb += 1
        nom = f"{self.pref}_PB_{id_ or self.n_pb:02d}" if not isinstance(id_, str) else f"{self.pref}_PB_{id_}"
        me = bpy.data.meshes.new(nom)
        me.from_pydata([(0, 0, 0)], [], [])
        ob = ax.objeto(nom, me, self.col, self.placa, self.P(x, y), (0, 0, 0))
        ax.gn(ob, "GN_CAB_Instancias_Puntos", Objeto="CAB_Fuente_Pulsador_Cuerpo", Escala=1.0, Giro_Aleatorio=0.0)
        ax.gn(ob, "GN_CAB_Pulsador_Leyendas", Texto_Sup=sup, Texto_Inf=inf, Color_Sup=COL[csup], Color_Inf=COL[cinf],
              Tamano=0.0030 if max(len(sup), len(inf)) <= 5 else 0.0024, Separacion=0.0042, Altura=0.0081,
              Material="MAT_CAB_Anunciador")
        ob["cab_estado"] = _bits(sup_on, inf_on)
        ob["cab_sistema"] = self.nombre
        ob["cab_control"] = nombre or nom
        if nombre:
            self.texto(x, y + (13.5 if etiqueta_arriba else -13.5), nombre)
        if guarda:
            self.instancia("CAB_Fuente_Guarda_Roja" if guarda == "roja" else "CAB_Fuente_Guarda_Clara", x, y, escala=0.86)
        self.pbs.append(ob)
        return ob

    def sw(self, x, y, nombre="", arriba="ON", abajo="OFF", centro=None, pos=1, etiqueta=True):
        """Interruptor de palanca con pomo moleteado y collar. pos: 1 arriba, 0 centro, -1 abajo."""
        ang = {1: 24.0, 0: 0.0, -1: -24.0}[pos]
        n = (0.0, math.sin(math.radians(ang)), math.cos(math.radians(ang)))
        self.instancia("CAB_Fuente_Base_Palanca", x, y)
        self.instancia("CAB_Fuente_Palanca_Moleteada", x, y, n)
        if etiqueta and nombre:
            self.texto(x, y + 15.5, nombre)
        self.texto(x, y + 9.0, arriba, "mini")
        self.texto(x, y - 9.5, abajo, "mini")
        if centro:
            self.texto(x + 9.5, y, centro, "mini")
        # marcas de posición serigrafiadas
        self.linea([(x - 5.5, y + 6.0), (x - 3.5, y + 6.0)], 0.45)
        self.linea([(x - 5.5, y - 6.0), (x - 3.5, y - 6.0)], 0.45)

    def rot(self, x, y, nombre, posiciones, indice=0, arco=90.0, radio=15.5, etiqueta_y=None, tam="mini"):
        """Selector rotativo con posiciones serigrafiadas en arco."""
        n = len(posiciones)
        angs = [(-arco / 2 + arco * i / (n - 1)) if n > 1 else 0.0 for i in range(n)]
        for p, a in zip(posiciones, angs):
            r = radio + (1.5 if len(p) > 3 else 0.0)
            self.texto(x + r * math.sin(math.radians(a)), y + r * math.cos(math.radians(a)), p, tam)
            self.linea([(x + 9.5 * math.sin(math.radians(a)), y + 9.5 * math.cos(math.radians(a))),
                        (x + 11.5 * math.sin(math.radians(a)), y + 11.5 * math.cos(math.radians(a)))], 0.5)
        self.instancia("CAB_Fuente_Rotativo", x, y, giro=-angs[indice])
        if nombre:
            self.texto(x, y + (etiqueta_y if etiqueta_y is not None else -14.5), nombre)

    def knob(self, x, y, nombre="", izq="", der="", valor=0.5, arco=270.0, marcas=11, radio=13.0, etiqueta_y=-15.5):
        """Mando continuo moleteado con escala (p. ej. temperatura COLD–HOT)."""
        for i in range(marcas):
            a = -arco / 2 + arco * i / (marcas - 1)
            l0, l1 = (10.5, 12.5) if i % 5 else (10.0, 13.0)
            self.linea([(x + l0 * math.sin(math.radians(a)), y + l0 * math.cos(math.radians(a))),
                        (x + l1 * math.sin(math.radians(a)), y + l1 * math.cos(math.radians(a)))], 0.45)
        if izq:
            a = -arco / 2
            self.texto(x + (radio + 3) * math.sin(math.radians(a)), y + (radio + 3) * math.cos(math.radians(a)) - 2, izq, "mini")
        if der:
            a = arco / 2
            self.texto(x + (radio + 3) * math.sin(math.radians(a)), y + (radio + 3) * math.cos(math.radians(a)) - 2, der, "mini")
        self.instancia("CAB_Fuente_Knob_OH", x, y, giro=-(-arco / 2 + arco * valor))
        if nombre:
            self.texto(x, y + etiqueta_y, nombre)

    def luz(self, x, y, texto, color="A", on=False, ancho=14.0, alto=7.0):
        """Indicador fijo (no pulsable): ventana de leyenda sobre la placa."""
        self.n_pb += 1
        nom = f"{self.pref}_LT_{self.n_pb:02d}"
        me = bpy.data.meshes.new(nom)
        me.from_pydata([(0, 0, 0)], [], [])
        ob = ax.objeto(nom, me, self.col, self.placa, self.P(x, y), (0, 0, 0))
        ax.gn(ob, "GN_CAB_Instancias_Puntos", Objeto="CAB_Fuente_Indicador", Escala=1.0, Giro_Aleatorio=0.0)
        ax.gn(ob, "GN_CAB_Pulsador_Leyendas", Texto_Sup=texto, Texto_Inf="", Color_Sup=COL[color], Color_Inf=COL[color],
              Tamano=0.0024, Separacion=0.0, Altura=0.0031, Material="MAT_CAB_Anunciador")
        ob["cab_estado"] = 1.0 if on else 0.0
        return ob

    def lcd(self, x, y, ancho, alto, texto, material="MAT_CAB_Texto_Verde", tam=0.0034):
        """Pantalla LCD pequeña: cristal negro y texto emisivo."""
        bm = ax.bm_nuevo()
        ax.caja(bm, (ancho * MM, alto * MM, 0.0015), (0, 0, 0.0004))
        nom = f"{self.pref}_LCD_{len([o for o in self.placa.children if 'LCD' in o.name]) + 1}"
        ob = ax.objeto(nom, ax.bm_a_malla(nom, bm), self.col, self.placa, self.P(x, y), (0, 0, 0))
        ax.asignar(ob, "MAT_CAB_Negro_Profundo")
        ax.estilo(ob, bisel=0.0004, atributos=False)
        if texto:
            ax.rotulos(nom + "_Txt", [((0, 0, 0.0013), texto)], tam, material, self.col, ob)
        # marco del LCD
        self.caja_linea(x - ancho / 2 - 1.2, y - alto / 2 - 1.2, x + ancho / 2 + 1.2, y + alto / 2 + 1.2, 0.5)
        return ob

    # ---------------------------------------------------------------- materialización
    def cerrar(self):
        pref, col, padre = self.pref, self.col, self.placa
        for lista, tam, suf in ((self.rot_peq, 0.0032, "Rotulos"), (self.rot_tit, 0.0043, "Titulos"),
                                (self.rot_mini, 0.0027, "Posiciones")):
            if lista:
                ax.rotulos(f"{pref}_{suf}", [(p + Vector((0, 0, 0.00005)), t) for p, t, _ in lista], tam,
                           "MAT_CAB_Etiqueta", col, padre, giros=[g for _, _, g in lista] if any(g for *_, g in lista) else None)
        if self.lineas:
            bm = ax.bm_nuevo()
            for pts, w in self.lineas:
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    d = Vector((x1 - x0, y1 - y0, 0))
                    if d.length < 1e-6:
                        continue
                    nrm = Vector((-d.y, d.x, 0)).normalized() * (w / 2)
                    ext = d.normalized() * (w / 2)
                    a0 = Vector((x0, y0, 0.00012)) - ext
                    a1 = Vector((x1, y1, 0.00012)) + ext
                    vs = [bm.verts.new(a0 - nrm), bm.verts.new(a1 - nrm), bm.verts.new(a1 + nrm), bm.verts.new(a0 + nrm)]
                    bm.faces.new(vs)
            ob = ax.objeto(f"{pref}_Lineas", ax.bm_a_malla(f"{pref}_Lineas", bm, suave=False), col, padre)
            ax.asignar(ob, "MAT_CAB_Etiqueta")
        for fuente, lista in self.pts.items():
            corto = fuente.replace("CAB_Fuente_", "")
            ob = ax.puntos(f"{pref}_{corto}", [p for p, *_ in lista], col, padre,
                           atributos={"cab_normal": ("FLOAT_VECTOR", [tuple(n) for _, n, _, _ in lista]),
                                      "cab_giro": ("FLOAT", [g for _, _, g, _ in lista]),
                                      "cab_escala": ("FLOAT", [e for *_, e in lista])})
            ax.gn(ob, "GN_CAB_Instancias_Puntos", Objeto=fuente, Escala=1.0, Giro_Aleatorio=0.0)
        return self.placa


def fuentes_comunes():
    """Piezas fuente nuevas (ocultas, en CAB_Auxiliar)."""
    aux = bpy.data.collections["CAB_Auxiliar"]
    hechas = {}
    # cuerpo de pulsador sin leyendas
    src = bpy.data.objects["CAB_Fuente_Pulsador_OFF"]
    if "CAB_Fuente_Pulsador_Cuerpo" not in bpy.data.objects:
        c = src.copy()
        c.name = "CAB_Fuente_Pulsador_Cuerpo"
        for m in list(c.modifiers):
            if m.type == "NODES" and m.node_group and m.node_group.name == "GN_CAB_Pulsador_Leyendas":
                c.modifiers.remove(m)
        for cc in list(c.users_collection):
            cc.objects.unlink(c)
        aux.objects.link(c)
        ax.marcar(c)
    # indicador fijo (marco + ventana, 3 mm)
    if "CAB_Fuente_Indicador" not in bpy.data.objects:
        bm = ax.bm_nuevo()
        ax.caja(bm, (0.016, 0.009, 0.003), (0, 0, 0.0015), mat=0)
        ob = ax.objeto("CAB_Fuente_Indicador", ax.bm_a_malla("CAB_Fuente_Indicador", bm), aux, None)
        ax.asignar(ob, "MAT_CAB_Plastico_Mate", "MAT_CAB_Lente_Humo")
        ax.estilo(ob, bisel=0.0006)
        ob.hide_render = ob.hide_viewport = True
    # palanca con pomo moleteado y collar hexagonal
    if "CAB_Fuente_Palanca_Moleteada" not in bpy.data.objects:
        bm = ax.bm_nuevo()
        ax.cilindro(bm, 0.0046, 0.0024, 6, (0, 0, 0.0012), mat=1)            # tuerca/collar hexagonal
        ax.cilindro(bm, 0.0032, 0.0012, 20, (0, 0, 0.0030), mat=1)           # arandela
        ax.cilindro(bm, 0.0013, 0.0130, 12, (0, 0, 0.0095), mat=0)           # vástago
        ax.cilindro(bm, 0.0028, 0.0075, 32, (0, 0, 0.0185), mat=0, r2=0.0030)  # pomo (bate)
        ob = ax.objeto("CAB_Fuente_Palanca_Moleteada", ax.bm_a_malla("CAB_Fuente_Palanca_Moleteada", bm), aux, None)
        ax.asignar(ob, "MAT_CAB_Cromo", "MAT_CAB_Metal_Cepillado")
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width, m.segments, m.limit_method, m.angle_limit = 0.0003, 2, "ANGLE", math.radians(35)
        ax.gn(ob, "GN_CAB_Moleteado", Dientes=40.0, Profundidad=0.00018, Z_Min=0.0152, Z_Max=0.0215, Diamante=1.0, Activo=1.0)
        ax.gn(ob, "GN_CAB_Atributos")
        ob.hide_render = ob.hide_viewport = True
    for n in ("CAB_Fuente_Pulsador_Cuerpo",):
        o = bpy.data.objects[n]
        o.hide_render = o.hide_viewport = True
    return hechas
