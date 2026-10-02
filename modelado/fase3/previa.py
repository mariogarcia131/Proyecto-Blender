"""Previsualizaciones rápidas (≤ 960×540) de cámaras de foto y del vídeo, en una sola sesión."""
import bpy, sys, time, json, os
argv = sys.argv[sys.argv.index("--") + 1:]
lista = json.load(open(argv[0]))            # [[camara, frame, etiqueta], ...]
out = argv[1]; ancho = int(argv[2]); alto = int(argv[3]); spp = int(argv[4])
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene; r = sc.render; c = sc.cycles
r.resolution_x, r.resolution_y, r.resolution_percentage = ancho, alto, 100
c.samples = spp; c.use_adaptive_sampling = True; c.adaptive_threshold = 0.05
c.use_denoising = True; c.denoiser = "OPENIMAGEDENOISE"; r.use_persistent_data = True
r.threads_mode = "FIXED"; r.threads = 4
r.image_settings.file_format = "JPEG"; r.image_settings.quality = 92
for cam, frame, et in lista:
    sc.camera = bpy.data.objects[cam]; sc.frame_set(int(frame))
    r.filepath = os.path.join(out, et + ".jpg"); t = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"PREVIA {et} {time.time() - t:.1f} s", flush=True)
