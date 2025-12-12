

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import datetime
import os
import json
import shutil
import tempfile
import configparser
import sys
import zipfile
import uuid

# Archivo de configuración y historial
CONFIG_FILE = "config.ini"
ARCHIVO_COPIAS = "copias.json"

# -------------------------
# Traducciones (inglés -> español) y normalizaciones
# -------------------------
DIAS_ING_ES = {
    "MON": "Lunes",
    "TUE": "Martes",
    "WED": "Miércoles",
    "THU": "Jueves",
    "FRI": "Viernes",
    "SAT": "Sábado",
    "SUN": "Domingo"
}

TIPO_ING_ES = {
    "once": "Una vez",
    "daily": "Diario",
    "weekly": "Semanal",
    "hourly": "Cada X horas"
}

ESTADO_MAP = {
    "Ready": "Listo",
    "Running": "Ejecutándose",
    "Disabled": "Deshabilitada",
    # Posibles valores en Windows español
    "Listo": "Listo",
    "En ejecución": "Ejecutándose",
    "En ejecución.": "Ejecutándose",
    "Deshabilitada": "Deshabilitada",
    "Deshabilitada.": "Deshabilitada"
}

# -------------------------
# UTILIDADES DE CONFIGURACIÓN
# -------------------------
def cargar_configparser():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE, encoding="utf-8")
    return config

def guardar_configparser(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        config.write(f)

def guardar_job_config(nombre, datos: dict):
    config = cargar_configparser()
    seccion = f"job_{nombre}"
    if seccion in config:
        config.remove_section(seccion)
    config[seccion] = {}
    for k, v in datos.items():
        if isinstance(v, (list, tuple)):
            config[seccion][k] = ",".join(map(str, v))
        else:
            config[seccion][k] = "" if v is None else str(v)
    guardar_configparser(config)

def leer_job_config(nombre):
    config = cargar_configparser()
    seccion = f"job_{nombre}"
    if seccion not in config:
        return None
    data = {}
    for k, v in config[seccion].items():
        if k in ("tablas", "dias_semana"):
            data[k] = v.split(",") if v else []
        elif k in ("zip",):
            data[k] = config[seccion].getboolean(k, fallback=False)
        elif k in ("repeticion_hours",):
            try:
                data[k] = int(v)
            except:
                data[k] = None
        else:
            data[k] = v
    return data

def listar_jobs_config():
    cfg = cargar_configparser()
    jobs = []
    for s in cfg.sections():
        if s.startswith("job_"):
            jobname = s[len("job_"):]
            datos = leer_job_config(jobname)
            if datos is None:
                continue
            datos["_jobname"] = jobname
            jobs.append(datos)
    return jobs

# -------------------------
# HISTORIAL DE COPIAS
# -------------------------
def cargar_copias():
    if not os.path.exists(ARCHIVO_COPIAS):
        with open(ARCHIVO_COPIAS, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)
        return []
    try:
        with open(ARCHIVO_COPIAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        with open(ARCHIVO_COPIAS, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4, ensure_ascii=False)
        return []

def guardar_copias():
    with open(ARCHIVO_COPIAS, "w", encoding="utf-8") as f:
        json.dump(copias, f, indent=4, ensure_ascii=False)

copias = cargar_copias()

# -------------------------
# BUSCAR mysqldump / mysql EN SISTEMA
# -------------------------
def buscar_ejecutable(nombre):
    posibles = [
        rf"C:\\xampp\\mysql\\bin\\{nombre}",
        rf"C:\\Program Files\\xampp\\mysql\\bin\\{nombre}",
        rf"C:\\Program Files (x86)\\xampp\\mysql\\bin\\{nombre}",
        rf"D:\\xampp\\mysql\\bin\\{nombre}",
        rf"D:\\Program Files\\xampp\\mysql\\bin\\{nombre}",
    ]
    for ruta in posibles:
        if os.path.exists(ruta):
            return ruta

    for unidad in ["C:\\", "D:\\"]:
        for raiz, dirs, archivos in os.walk(unidad):
            if nombre in archivos:
                return os.path.join(raiz, nombre)
    return None

def obtener_ejecutable_seguro(nombre):
    encontrado = buscar_ejecutable(nombre)
    if not encontrado:
        messagebox.showerror(f"{nombre} no encontrado",
                             f"No se encontró {nombre}. Instalá XAMPP o localízalo manualmente.")
        return None
    temp_dir = os.path.join(tempfile.gettempdir(), f"{nombre}_safe")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    destino = os.path.join(temp_dir, nombre)
    try:
        if not os.path.exists(destino) or os.path.getsize(destino) != os.path.getsize(encontrado):
            shutil.copy(encontrado, destino)
    except Exception:
        return encontrado
    return destino

# -------------------------
# VALIDACIONES DE RUTAS
# -------------------------
def carpeta_valida(path):
    path = (path or "").lower().replace("/", "\\")
    prohibidas = [
        "c:\\program files",
        "c:\\program files (x86)",
        "c:\\windows",
        "c:\\programdata",
        "c:\\xampp\\mysql\\bin"
    ]
    return not any(path.startswith(p) for p in prohibidas)

# -------------------------
# FUNCIONES DE BACKUP Y ZIP
# -------------------------
def agregar_copia(usuario, contrasena, bd, ruta, hora=None):
    if hora is None:
        hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    copias.append({
        "usuario": usuario,
        "contrasena": contrasena,
        "bd": bd,
        "hora": hora,
        "ruta": ruta
    })
    guardar_copias()
    actualizar_tabla_historial()

def zip_file(path_sql, keep_original=False):
    try:
        base = os.path.splitext(path_sql)[0]
        zip_path = base + ".zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(path_sql, arcname=os.path.basename(path_sql))
        if not keep_original:
            try:
                os.remove(path_sql)
            except:
                pass
        return zip_path
    except Exception:
        return None

def ejecutar_mysqldump(usuario, contrasena, bd, tablas, destino_file):
    mysqldump = obtener_ejecutable_seguro("mysqldump.exe")
    if not mysqldump:
        return (False, "mysqldump no encontrado")

    comando = [mysqldump, "-u", usuario]
    if contrasena:
        comando.append(f"-p{contrasena}")

    if tablas:
        if isinstance(tablas, str):
            tablas = tablas.split()
        comando += [bd] + tablas
    else:
        comando.append(bd)

    try:
        with open(destino_file, "w", encoding="utf-8") as salida:
            resultado = subprocess.run(comando, stdout=salida, stderr=subprocess.PIPE, text=True)

        if resultado.returncode != 0:
            return (False, resultado.stderr)
        return (True, None)
    except Exception as e:
        return (False, str(e))

# -------------------------
# RESTAURACIÓN DE SQL
# -------------------------
def ejecutar_mysql_restore(usuario, contrasena, bd, sql_path):
    mysql_exe = obtener_ejecutable_seguro("mysql.exe")
    if not mysql_exe:
        return (False, "mysql.exe no encontrado")

    comando = [mysql_exe, "-u", usuario]
    if contrasena:
        comando.append(f"-p{contrasena}")
    comando.append(bd)

    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            resultado = subprocess.run(comando, stdin=f, stderr=subprocess.PIPE, text=True)

        if resultado.returncode != 0:
            return (False, resultado.stderr)
        return (True, None)
    except Exception as e:
        return (False, str(e))

# -------------------------
# EJECUTAR JOB AUTOMÁTICO (Programador Windows)
# -------------------------
def ejecutar_job_auto(jobname):
    datos = leer_job_config(jobname)
    if not datos:
        return

    usuario = datos.get("usuario", "")
    contrasena = datos.get("contrasena", "")
    bd = datos.get("bd", "")
    destino = datos.get("destino", "") or "."
    tablas = datos.get("tablas", []) or []
    zip_opt = datos.get("zip", False)
    tablas_param = tablas if tablas else None

    fecha = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if tablas_param:
        tablas_name = "_".join(tablas_param).replace(" ", "_")
        archivo = os.path.join(destino, f"{bd}_TABLAS_{tablas_name}_{fecha}.sql")
    else:
        archivo = os.path.join(destino, f"{bd}_backup_{fecha}.sql")

    ok, err = ejecutar_mysqldump(usuario, contrasena, bd, tablas_param, archivo)
    if not ok:
        return

    archivo_result = archivo
    if zip_opt:
        z = zip_file(archivo, keep_original=False)
        if z:
            archivo_result = z

    agregar_copia(usuario, contrasena, f"{bd}{'.' + ','.join(tablas_param) if tablas_param else ''}", archivo_result)

# -------------------------
# GESTIÓN DE TAREAS WINDOWS
# -------------------------
def crear_tarea_windows(nombre_tarea, tipo, fecha, hora, jobname, repeticion_hours=None, dias_semana=None):
    ruta_script = os.path.abspath(__file__)
    tr = f'python "{ruta_script}" --auto --jobname "{jobname}"'

    if tipo == "once":
        cmd = f'schtasks /create /tn "{nombre_tarea}" /tr "{tr}" /sc once /st {hora} /sd {fecha} /f'
    elif tipo == "daily":
        cmd = f'schtasks /create /tn "{nombre_tarea}" /tr "{tr}" /sc daily /st {hora} /f'
    elif tipo == "weekly":
        dias = ",".join(dias_semana) if dias_semana else "MON"
        cmd = f'schtasks /create /tn "{nombre_tarea}" /tr "{tr}" /sc weekly /d {dias} /st {hora} /f'
    elif tipo == "hourly":
        mo = repeticion_hours if repeticion_hours and repeticion_hours > 0 else 1
        cmd = f'schtasks /create /tn "{nombre_tarea}" /tr "{tr}" /sc hourly /mo {mo} /st {hora} /f'
    else:
        return False, "Tipo inválido"

    try:
        resultado = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if resultado.returncode != 0:
            return False, resultado.stderr
        return True, None
    except Exception as e:
        return False, str(e)

# -------------------------
# EJECUTAR / BORRAR / CAMBIAR ESTADO WINDOWS
# -------------------------
def run_tarea_windows(nombre_tarea):
    cmd = f'schtasks /run /tn "{nombre_tarea}"'
    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return (r.returncode == 0, r.stderr or r.stdout)
    except Exception as e:
        return (False, str(e))

def delete_tarea_windows(nombre_tarea):
    cmd = f'schtasks /delete /tn "{nombre_tarea}" /f'
    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return (r.returncode == 0, r.stderr or r.stdout)
    except Exception as e:
        return (False, str(e))

def change_tarea_windows_enable(nombre_tarea, enable=True):
    action = "/enable" if enable else "/disable"
    cmd = f'schtasks /change /tn "{nombre_tarea}" {action}'
    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return (r.returncode == 0, r.stderr or r.stdout)
    except Exception as e:
        return (False, str(e))

# -------------------------
# CONSULTAR PRÓXIMA EJECUCIÓN (formato ISO)
# -------------------------
def query_task_next_run(task_name):
    try:
        cmd = f'schtasks /query /tn "{task_name}" /fo LIST /v'
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if r.returncode != 0:
            return (None, None)

        out = r.stdout.splitlines()
        next_run = None
        status = None

        for line in out:
            s = line.strip()

            if s.lower().startswith("siguiente ejecución:") or s.lower().startswith("next run time:"):
                if ":" in s:
                    next_run = s.partition(":")[2].strip()
                else:
                    next_run = s.strip()

            if s.lower().startswith("estado:") or s.lower().startswith("status:"):
                if ":" in s:
                    status = s.partition(":")[2].strip()
                else:
                    status = s.strip()

        # Normalizar estado
        status_norm = None
        if status:
            for k, v in ESTADO_MAP.items():
                if k.lower() in status.lower():
                    status_norm = v
                    break
            if not status_norm:
                status_norm = status

        # Normalizar fecha a YYYY-MM-DD HH:MM
        if next_run:
            parsed = None
            nr = next_run.strip()

            formatos = [
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M"
            ]

            for fmt in formatos:
                try:
                    parsed = datetime.datetime.strptime(nr, fmt)
                    break
                except:
                    pass

            if parsed:
                next_run_fmt = parsed.strftime("%Y-%m-%d %H:%M")
            else:
                next_run_fmt = nr
        else:
            next_run_fmt = None

        return (next_run_fmt, status_norm)

    except Exception:
        return (None, None)

# -------------------------
# PROCESOS EN EJECUCIÓN
# -------------------------
def obtener_procesos_en_ejecucion():
    """
    Retorna lista de dicts con los procesos activos relevantes:
    mysqldump.exe y python.exe (tareas automáticas).
    """
    procesos = []
    try:
        out = subprocess.run("tasklist /fo csv /nh", shell=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = out.stdout.splitlines()

        for l in lines:
            parts = [p.strip().strip('"') for p in l.split('","')]
            if len(parts) >= 2:
                name = parts[0]
                pid = parts[1]

                if name.lower() in ("mysqldump.exe", "mysqldump"):
                    procesos.append({"process": name, "pid": pid, "info": "mysqldump activo"})

                if name.lower() in ("python.exe", "python"):
                    procesos.append({"process": name, "pid": pid, "info": "python.exe (posible tarea automática)"})

    except Exception:
        pass

    return procesos

# -------------------------
# SELECCIÓN DE DESTINO
# -------------------------
def seleccionar_destino():
    carpeta = filedialog.askdirectory()
    if carpeta:
        entry_destino.delete(0, tk.END)
        entry_destino.insert(0, carpeta)

# -------------------------
# ACTUALIZAR TABLA HISTORIAL
# -------------------------
def actualizar_tabla_historial():
    for fila in tabla_historial.get_children():
        tabla_historial.delete(fila)

    for i, copia in enumerate(copias, 1):
        tabla_historial.insert(
            "",
            "end",
            values=(i, copia.get("usuario"), copia.get("bd"),
                    copia.get("hora"), copia.get("ruta"))
        )

# --------------------------------------------------------------------------------
# VENTANAS SECUNDARIAS: BACKUP TABLA / PROGRAMAR / RESTAURAR
# --------------------------------------------------------------------------------
def ventana_backup_tabla():
    win = tk.Toplevel(ventana)
    win.title("📄 Backup de Tabla(s)")
    win.geometry("420x360")
    win.configure(bg="#f4f4f9")

    frame = tk.Frame(win, bg="#f4f4f9")
    frame.pack(fill="both", expand=True, padx=20, pady=20)

    tk.Label(frame, text="Base de Datos:", bg="#f4f4f9").pack(anchor="w")
    entry_db_t = ttk.Entry(frame, width=40)
    entry_db_t.pack(fill="x", pady=5)
    entry_db_t.insert(0, entry_bd.get().strip())

    tk.Label(frame, text="Nombre de la(s) Tabla(s) (separadas por espacio):", bg="#f4f4f9").pack(anchor="w")
    entry_tabla_t = ttk.Entry(frame, width=40)
    entry_tabla_t.pack(fill="x", pady=5)

    tk.Label(frame, text="Carpeta destino:", bg="#f4f4f9").pack(anchor="w")
    entry_dest_t = ttk.Entry(frame, width=40)
    entry_dest_t.pack(fill="x", pady=5)
    entry_dest_t.insert(0, entry_destino.get().strip())

    def seleccionar_dest_local():
        carpeta = filedialog.askdirectory()
        if carpeta:
            entry_dest_t.delete(0, tk.END)
            entry_dest_t.insert(0, carpeta)

    ttk.Button(frame, text="Seleccionar carpeta", command=seleccionar_dest_local).pack(pady=5)

    zip_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text="Comprimir en ZIP", variable=zip_var).pack(pady=5)

    def ejecutar_backup_tabla():
        usuario = entry_usuario.get().strip()
        contrasena = entry_contrasena.get().strip()
        bd = entry_db_t.get().strip()
        tablas_raw = entry_tabla_t.get().strip()
        destino = entry_dest_t.get().strip()
        zip_opt = zip_var.get()

        if not bd or not tablas_raw:
            messagebox.showerror("Error", "Debes ingresar base de datos y al menos una tabla.")
            return

        if not destino:
            messagebox.showerror("Error", "Seleccioná carpeta destino.")
            return

        if not carpeta_valida(destino):
            messagebox.showerror("Carpeta no permitida", "Elegí otra carpeta destino.")
            return

        tablas = tablas_raw.split()
        fecha = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        tablas_name = "_".join(tablas).replace(" ", "_")
        archivo = os.path.join(destino, f"{bd}_TABLAS_{tablas_name}_{fecha}.sql")

        ok, err = ejecutar_mysqldump(usuario, contrasena, bd, tablas, archivo)
        if not ok:
            messagebox.showerror("Error", err)
            return

        resultado_path = archivo
        if zip_opt:
            z = zip_file(archivo, keep_original=False)
            if z:
                resultado_path = z

        agregar_copia(usuario, contrasena, f"{bd}." + ",".join(tablas), resultado_path)
        messagebox.showinfo("Éxito", f"Backup de tabla(s) creado:\n{resultado_path}")
        win.destroy()

    ttk.Button(frame, text="Crear Backup de Tabla(s)", style="Green.TButton",
               command=ejecutar_backup_tabla).pack(pady=12)

# --------------------------------------------------------------------------------
def ventana_programar_backup():
    win = tk.Toplevel(ventana)
    win.title("⏰ Programar Backup (Crear Tarea de Windows)")
    win.geometry("520x460")
    win.configure(bg="#f4f4f9")

    frm = tk.Frame(win, bg="#f4f4f9")
    frm.pack(fill="both", expand=True, padx=15, pady=12)

    ttk.Label(frm, text="Tipo de programación:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
    tipo_var = tk.StringVar(value="daily")

    opciones = [
        ("Una vez (once)", "once"),
        ("Diaria (daily)", "daily"),
        ("Semanal (weekly)", "weekly"),
        ("Cada N horas (hourly)", "hourly")
    ]

    r = 1
    for txt, val in opciones:
        ttk.Radiobutton(frm, text=txt, variable=tipo_var, value=val).grid(row=r, column=0, sticky="w")
        r += 1

    ttk.Label(frm, text="Base de Datos:", font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w", padx=10)
    entry_db = ttk.Entry(frm, width=25)
    entry_db.grid(row=1, column=1, sticky="w", padx=10)
    entry_db.insert(0, entry_bd.get().strip())

    ttk.Label(frm, text="Tablas (opcional, separar por espacio):", font=("Arial", 10, "bold")).grid(row=2, column=1, sticky="w", padx=10)
    entry_tablas = ttk.Entry(frm, width=25)
    entry_tablas.grid(row=3, column=1, sticky="w", padx=10)

    ttk.Label(frm, text="Hora (HH:MM):", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(10, 0))
    entry_hora_local = ttk.Entry(frm, width=10)
    entry_hora_local.grid(row=5, column=0, sticky="w")
    entry_hora_local.insert(0, "12:00")

    ttk.Label(frm, text="Fecha (YYYY-MM-DD) [Solo once]:", font=("Arial", 10, "bold")).grid(row=6, column=0, sticky="w", pady=(10, 0))
    entry_fecha_local = ttk.Entry(frm, width=12)
    entry_fecha_local.grid(row=7, column=0, sticky="w")
    entry_fecha_local.insert(0, datetime.datetime.now().strftime("%Y-%m-%d"))

    ttk.Label(frm, text="Destino:", font=("Arial", 10, "bold")).grid(row=4, column=1, sticky="w", padx=10)
    entry_dest_local = ttk.Entry(frm, width=25)
    entry_dest_local.grid(row=5, column=1, sticky="w", padx=10)
    entry_dest_local.insert(0, entry_destino.get().strip())

    ttk.Button(frm, text="Seleccionar carpeta", command=lambda: seleccionar_dest_para(entry_dest_local)).grid(row=6, column=1, sticky="w", padx=10, pady=5)

    zip_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frm, text="Comprimir en ZIP", variable=zip_var).grid(row=8, column=1, sticky="w", padx=10, pady=5)

    ttk.Label(frm, text="Nombre de la tarea:", font=("Arial", 10, "bold")).grid(row=9, column=0, sticky="w", pady=(10,0))
    entry_nombre_tarea = ttk.Entry(frm, width=25)
    entry_nombre_tarea.grid(row=10, column=0, sticky="w")
    entry_nombre_tarea.insert(0, "BackupMySQL_" + uuid.uuid4().hex[:6])

    ttk.Label(frm, text="Repetir cada N horas:", font=("Arial", 10, "bold")).grid(row=9, column=1, sticky="w", padx=10)
    entry_repetir = ttk.Entry(frm, width=8)
    entry_repetir.grid(row=10, column=1, sticky="w", padx=10)
    entry_repetir.insert(0, "1")

    ttk.Label(frm, text="Días semana (solo weekly) - ej: MON,WED,FRI", font=("Arial", 9)).grid(
        row=11, column=0, columnspan=2, sticky="w", pady=(8,0)
    )
    entry_dias = ttk.Entry(frm, width=40)
    entry_dias.grid(row=12, column=0, columnspan=2, sticky="w", pady=5)
    entry_dias.insert(0, "MON")

    ttk.Label(frm, text="Usuario MySQL:", font=("Arial", 10, "bold")).grid(row=13, column=0, sticky="w", pady=(10,0))
    entry_usr_local = ttk.Entry(frm, width=15)
    entry_usr_local.grid(row=14, column=0, sticky="w")
    entry_usr_local.insert(0, entry_usuario.get().strip())

    ttk.Label(frm, text="Contraseña MySQL:", font=("Arial", 10, "bold")).grid(row=13, column=1, sticky="w", padx=10, pady=(10,0))
    entry_pwd_local = ttk.Entry(frm, width=15, show="*")
    entry_pwd_local.grid(row=14, column=1, sticky="w", padx=10)
    entry_pwd_local.insert(0, entry_contrasena.get().strip())

    def seleccionar_dest_para(entry_obj):
        carpeta = filedialog.askdirectory()
        if carpeta:
            entry_obj.delete(0, tk.END)
            entry_obj.insert(0, carpeta)

    def crear_programacion():
        tipo = tipo_var.get()
        bd = entry_db.get().strip()
        tablas_raw = entry_tablas.get().strip()
        tablas = tablas_raw.split() if tablas_raw else []
        hora = entry_hora_local.get().strip()
        fecha = entry_fecha_local.get().strip()
        destino = entry_dest_local.get().strip()
        zip_opt = zip_var.get()
        nombre_tarea = entry_nombre_tarea.get().strip()
        repetir = int(entry_repetir.get().strip() or 1)
        dias = [d.strip().upper() for d in entry_dias.get().split(",") if d.strip()] if entry_dias.get().strip() else []

        usuario = entry_usr_local.get().strip()
        contrasena = entry_pwd_local.get().strip()

        if not nombre_tarea:
            messagebox.showerror("Error", "Ingresá un nombre para la tarea.")
            return

        if tipo == "once" and (not fecha or fecha == ""):
            messagebox.showerror("Error", "Ingresá fecha para ejecución única.")
            return

        if not hora:
            messagebox.showerror("Error", "Ingresá hora.")
            return

        if not destino:
            messagebox.showerror("Error", "Ingresá carpeta destino.")
            return

        if not carpeta_valida(destino):
            messagebox.showerror("Carpeta no permitida", "Elegí otra carpeta destino.")
            return

        jobname = nombre_tarea.replace(" ", "_")

        datos = {
            "tipo": tipo,
            "fecha": fecha,
            "hora": hora,
            "destino": destino,
            "tablas": tablas,
            "usuario": usuario,
            "contrasena": contrasena,
            "bd": bd,
            "zip": zip_opt,
            "repeticion_hours": repetir,
            "dias_semana": dias,
            "task_name": nombre_tarea
        }

        guardar_job_config(jobname, datos)

        success, err = crear_tarea_windows(
            nombre_tarea, tipo, fecha, hora,
            jobname, repeticion_hours=repetir, dias_semana=dias
        )

        if not success:
            messagebox.showerror("Error creando tarea", err)
            return

        messagebox.showinfo(
            "Tarea creada",
            f"Tarea '{nombre_tarea}' creada correctamente en el Programador de Tareas de Windows."
        )
        win.destroy()

    ttk.Button(
        frm,
        text="Crear tarea en Windows",
        command=crear_programacion,
        style="Orange.TButton"
    ).grid(row=15, column=0, columnspan=2, pady=15)

# --------------------------------------------------------------------------------
def ventana_restaurar():
    win = tk.Toplevel(ventana)
    win.title("🔁 Restaurar SQL")
    win.geometry("420x200")
    win.configure(bg="#f4f4f9")

    frame = tk.Frame(win, bg="#f4f4f9")
    frame.pack(fill="both", expand=True, padx=20, pady=20)

    ttk.Label(frame, text="Archivo .sql para restaurar:", font=("Arial", 10, "bold")).pack(anchor="w")
    entry_sql = ttk.Entry(frame, width=50)
    entry_sql.pack(fill="x", pady=8)

    def seleccionar_file():
        f = filedialog.askopenfilename(filetypes=[("SQL files", "*.sql")])
        if f:
            entry_sql.delete(0, tk.END)
            entry_sql.insert(0, f)

    ttk.Button(frame, text="Seleccionar archivo", command=seleccionar_file).pack(pady=6)

    def ejecutar_restauracion():
        usuario = entry_usuario.get().strip()
        contrasena = entry_contrasena.get().strip()
        bd = entry_bd.get().strip()
        sql_path = entry_sql.get().strip()

        if not usuario or not bd:
            messagebox.showerror("Error", "Completá usuario y base de datos.")
            return

        if not sql_path or not os.path.exists(sql_path):
            messagebox.showerror("Error", "Seleccioná un archivo SQL válido.")
            return

        ok, err = ejecutar_mysql_restore(usuario, contrasena, bd, sql_path)
        if not ok:
            messagebox.showerror("Error restaurando", err)
            return

        messagebox.showinfo("Éxito", "Restauración completada correctamente.")
        win.destroy()

    ttk.Button(
        frame,
        text="Restaurar ahora",
        command=ejecutar_restauracion,
        style="Green.TButton"
    ).pack(pady=10)

# -------------------------
# INTERFAZ PRINCIPAL
# -------------------------
ventana = tk.Tk()
ventana.title("🛡️ Backup MySQL Pro")
ventana.geometry("980x800")
ventana.resizable(True, True)
ventana.configure(bg="#f4f4f9")

# Estilos
style = ttk.Style()
style.theme_create("ModernPro", parent="alt", settings={
    "TFrame": {"configure": {"background": "#f4f4f9"}},
    "TLabel": {"configure": {"background": "#f4f4f9", "font": ("Arial", 10)}},
    "TEntry": {"configure": {"padding": 5, "fieldbackground": "white", "relief": "flat"}},
    "TButton": {"configure": {"font": ("Arial", 10, "bold"), "padding": 8}},
    "Treeview": {"configure": {
        "background": "white",
        "foreground": "#333",
        "rowheight": 26,
        "fieldbackground": "white",
        "font": ("Arial", 9)
    }},
    "Treeview.Heading": {"configure": {
        "font": ("Arial", 10, "bold"),
        "background": "#2c3e50",
        "foreground": "white",
        "relief": "flat"
    }}
})
style.theme_use("ModernPro")

style.configure("Green.TButton", background="#4CAF50", foreground="white")
style.configure("Orange.TButton", background="#FF9800", foreground="white")
style.configure("Menu.TButton", background="#2c3e50", foreground="white", font=("Arial", 10, "bold"))
style.map("Menu.TButton", background=[('active', '#34495e')])

# -------------------------
# HEADER
# -------------------------
header_frame = ttk.Frame(ventana, padding="10 10 10 0")
header_frame.pack(fill="x")

tk.Label(
    header_frame, text="🛡️ Backup MySQL Pro",
    font=("Arial", 18, "bold"),
    bg="#f4f4f9", fg="#2c3e50"
).pack(side=tk.LEFT)

menu_btn = ttk.Menubutton(
    header_frame,
    text="⚙️ Gestor de Copias",
    style="Menu.TButton",
    direction="below"
)
menu_btn.pack(side=tk.RIGHT, padx=10)

menu = tk.Menu(menu_btn, tearoff=0, bg="#ecf0f1", fg="#333", font=("Arial", 10))
menu.add_command(label="➕  Crear Backup (Manual)", command=lambda: hacer_backup_ui(False))
menu.add_command(label="📄  Backup de Tabla(s)", command=ventana_backup_tabla)
menu.add_command(label="⏰ Programar Backup (Tarea Windows)", command=ventana_programar_backup)
menu.add_command(label="🔁 Restaurar SQL", command=ventana_restaurar)

menu_btn["menu"] = menu
# -------------------------
# Entradas principales (configuración rápida)
# -------------------------
frame_config = ttk.Frame(ventana, padding="15 15 15 5")
frame_config.pack(fill="x", padx=10)

labels = ["Usuario MySQL:", "Contraseña:", "Base de Datos:", "Carpeta destino:"]
default_values = {"Usuario MySQL:": "root", "Contraseña:": "", "Base de Datos:": "miguelhogar", "Carpeta destino:": ""}

entry_usuario = entry_contrasena = entry_bd = entry_destino = None

for i, label_text in enumerate(labels):
    ttk.Label(frame_config, text=label_text, font=("Arial", 10, "bold")).grid(row=i, column=0, sticky="w", pady=2, padx=5)
    entry_frame = ttk.Frame(frame_config)
    entry_frame.grid(row=i, column=1, sticky="ew", pady=2)
    entry = ttk.Entry(entry_frame, width=50)
    entry.insert(0, default_values[label_text])
    entry.pack(side=tk.LEFT, fill="x", expand=True)
    if label_text == "Contraseña:":
        entry.config(show="*")
    if label_text == "Carpeta destino:":
        ttk.Button(entry_frame, text="Seleccionar", command=seleccionar_destino).pack(side=tk.LEFT, padx=5)
        entry_destino = entry
    elif label_text == "Usuario MySQL:":
        entry_usuario = entry
    elif label_text == "Contraseña:":
        entry_contrasena = entry
    elif label_text == "Base de Datos:":
        entry_bd = entry

frame_config.columnconfigure(1, weight=1)

# -------------------------
# Programador rápido (botón que abre la ventana programar)
# -------------------------
frame_programacion = ttk.Frame(ventana, padding="15 0 15 10")
frame_programacion.pack(fill="x", padx=10)
ttk.Label(frame_programacion, text="📅 Programación Rápida (abre herramienta completa abajo):", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w")
ttk.Button(frame_programacion, text="Abrir programador (tareas Windows)", command=ventana_programar_backup, style="Orange.TButton").grid(row=0, column=1, sticky="e")

# -------------------------
# Acciones: botones principales
# -------------------------
frame_botones = ttk.Frame(ventana, padding="15 0 15 10")
frame_botones.pack(fill="x", padx=10)
ttk.Button(frame_botones, text="🚀 HACER BACKUP MANUAL AHORA", command=lambda: hacer_backup_ui(False), style="Green.TButton").pack(fill="x", expand=True)
ttk.Button(frame_botones, text="📄 HACER BACKUP DE UNA TABLA", command=ventana_backup_tabla, style="Green.TButton").pack(fill="x", expand=True, pady=6)

# -------------------------
# Historial de copias (superior)
# -------------------------
ttk.Label(ventana, text="Historial de Copias", font=("Arial", 12, "bold"), background="#f4f4f9", foreground="#2c3e50").pack(anchor="w", padx=15, pady=(10, 5))
columnas_hist = ("ID", "Usuario", "Base de Datos", "Fecha", "Ruta")
tabla_historial = ttk.Treeview(ventana, columns=columnas_hist, show="headings", height=8)
tabla_historial.pack(fill=tk.BOTH, padx=15, pady=(0, 10), expand=False)
for c in columnas_hist:
    tabla_historial.heading(c, text=c)
tabla_historial.column("ID", width=40, anchor="center")
tabla_historial.column("Usuario", width=90, anchor="center")
tabla_historial.column("Base de Datos", width=140, anchor="center")
tabla_historial.column("Fecha", width=160, anchor="center")
tabla_historial.column("Ruta", minwidth=200)

actualizar_tabla_historial()

# -------------------------
# NOTEBOOK inferior con 3 pestañas:
#  - Tareas programadas (tabla que listará jobs guardados en config.ini)
#  - Próximas ejecuciones (consulta schtasks)
#  - Tareas en ejecución (procesos: mysqldump / python)
# -------------------------
notebook = ttk.Notebook(ventana)
notebook.pack(fill="both", expand=True, padx=15, pady=10)

# TAB 1: TAREAS PROGRAMADAS (opción A: tabla abajo)
tab_programadas = ttk.Frame(notebook)
notebook.add(tab_programadas, text="Tareas programadas")

cols_prog = ("Nombre tarea", "Tipo", "Hora/Fecha", "Destino", "Tablas", "ZIP", "BD")
tree_prog = ttk.Treeview(tab_programadas, columns=cols_prog, show="headings", height=8)
tree_prog.pack(fill="both", expand=True, padx=10, pady=6)
for c in cols_prog:
    tree_prog.heading(c, text=c)
tree_prog.column("Nombre tarea", width=180)
tree_prog.column("Tipo", width=80)
tree_prog.column("Hora/Fecha", width=180)
tree_prog.column("Destino", width=180)
tree_prog.column("Tablas", width=160)
tree_prog.column("ZIP", width=40, anchor="center")
tree_prog.column("BD", width=100)

# botones para la tarea seleccionada
frame_prog_btns = ttk.Frame(tab_programadas)
frame_prog_btns.pack(fill="x", padx=10, pady=6)
btn_runnow = ttk.Button(frame_prog_btns, text="Ejecutar ahora", command=lambda: accion_tarea_seleccionada("run"))
btn_disable = ttk.Button(frame_prog_btns, text="Deshabilitar/Habilitar", command=lambda: accion_tarea_seleccionada("toggle"))
btn_delete = ttk.Button(frame_prog_btns, text="Eliminar tarea", command=lambda: accion_tarea_seleccionada("delete"))
btn_refresh = ttk.Button(frame_prog_btns, text="Actualizar", command=lambda: refresh_all_tabs())
btn_runnow.pack(side="left", padx=6)
btn_disable.pack(side="left", padx=6)
btn_delete.pack(side="left", padx=6)
btn_refresh.pack(side="right", padx=6)

# TAB 2: PRÓXIMAS EJECUCIONES
tab_next = ttk.Frame(notebook)
notebook.add(tab_next, text="Próximas ejecuciones")
cols_next = ("Nombre tarea", "Próxima ejecución", "Estado")
tree_next = ttk.Treeview(tab_next, columns=cols_next, show="headings", height=8)
tree_next.pack(fill="both", expand=True, padx=10, pady=6)
for c in cols_next:
    tree_next.heading(c, text=c)
tree_next.column("Nombre tarea", width=260)
tree_next.column("Próxima ejecución", width=200)
tree_next.column("Estado", width=140)

# TAB 3: TAREAS EN EJECUCIÓN
tab_running = ttk.Frame(notebook)
notebook.add(tab_running, text="Tareas en ejecución")
cols_run = ("Proceso", "PID", "Info")
tree_run = ttk.Treeview(tab_running, columns=cols_run, show="headings", height=8)
tree_run.pack(fill="both", expand=True, padx=10, pady=6)
for c in cols_run:
    tree_run.heading(c, text=c)
tree_run.column("Proceso", width=200)
tree_run.column("PID", width=80)
tree_run.column("Info", width=320)
# -------------------------
# FUNCIONES DE REFRESCO PARA LAS 3 PESTAÑAS
# -------------------------
def refresh_tab_programadas():
    for r in tree_prog.get_children():
        tree_prog.delete(r)
    jobs = listar_jobs_config()
    for j in jobs:
        task_name = j.get("task_name") or j.get("_jobname") or j.get("_job", "")
        tipo_raw = (j.get("tipo") or "").lower()
        tipo_es = TIPO_ING_ES.get(tipo_raw, tipo_raw.capitalize() if tipo_raw else "")
        hora = j.get("hora", "") or ""
        fecha = j.get("fecha", "") or ""
        destino = j.get("destino", "") or ""
        tablas = ", ".join(j.get("tablas", [])) if isinstance(j.get("tablas", []), (list, tuple)) else (j.get("tablas") or "")
        zipv = "Sí" if str(j.get("zip", False)).lower() in ("true", "1", "yes") else "No"
        bd = j.get("bd", "") or ""
        dias = j.get("dias_semana", []) or []
        dias_es = ", ".join(DIAS_ING_ES.get(d.upper(), d) for d in dias) if dias else ""

        # Construir Hora/Fecha legible
        hora_fecha = ""
        if tipo_raw == "once":
            if fecha and hora:
                try:
                    parsed = datetime.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
                    hora_fecha = parsed.strftime("%Y-%m-%d %H:%M")
                except:
                    hora_fecha = f"{fecha} {hora}"
            else:
                hora_fecha = f"{fecha} {hora}".strip()
        elif tipo_raw == "weekly":
            hora_fecha = f"{hora} ({dias_es})" if dias_es else f"{hora}"
        elif tipo_raw == "hourly":
            rep = j.get("repeticion_hours")
            try:
                rep_int = int(rep) if rep else None
            except:
                rep_int = None
            hora_fecha = f"{hora} (cada {rep_int} horas)" if rep_int else f"{hora} (Cada X horas)"
        else:
            hora_fecha = hora or ""

        display_name = task_name if task_name else j.get("_jobname")
        tree_prog.insert("", "end", values=(display_name, tipo_es, hora_fecha, destino, tablas, zipv, bd), tags=(j.get("_jobname"),))

def refresh_tab_next_runs():
    for r in tree_next.get_children():
        tree_next.delete(r)
    jobs = listar_jobs_config()
    for j in jobs:
        jobname = j.get("_jobname")
        task_name = j.get("task_name") or jobname
        next_run, status = query_task_next_run(task_name)
        # Normalizar estado a español
        status_es = "Desconocido"
        if status:
            for k, v in ESTADO_MAP.items():
                if k.lower() in status.lower():
                    status_es = v
                    break
            else:
                status_es = status
        tree_next.insert("", "end", values=(task_name, next_run or "N/A", status_es))

def refresh_tab_running():
    for r in tree_run.get_children():
        tree_run.delete(r)
    procesos = obtener_procesos_en_ejecucion()
    for p in procesos:
        tree_run.insert("", "end", values=(p.get("process"), p.get("pid"), p.get("info")))

def refresh_all_tabs():
    refresh_tab_programadas()
    refresh_tab_next_runs()
    refresh_tab_running()

# -------------------------
# ACCIONES SOBRE TAREAS (usar en botones)
# -------------------------
def obtener_tarea_seleccionada():
    sel = tree_prog.selection()
    if not sel:
        return None
    vals = tree_prog.item(sel[0], "values")
    if not vals:
        return None
    task_display = vals[0]
    cfg = cargar_configparser()
    for s in cfg.sections():
        if s.startswith("job_"):
            jobname = s[len("job_"):]
            datos = leer_job_config(jobname)
            if not datos:
                continue
            task_name = datos.get("task_name") or jobname
            if task_name == task_display or jobname == task_display:
                return (task_name, jobname)
    return (task_display, None)

def accion_tarea_seleccionada(action):
    info = obtener_tarea_seleccionada()
    if not info:
        messagebox.showerror("Error", "Seleccioná una tarea en la lista.")
        return
    task_display, jobname = info

    if action == "run":
        ok, msg = run_tarea_windows(task_display)
        if ok:
            messagebox.showinfo("Ejecutando", f"Tarea {task_display} enviada a ejecución.")
        else:
            messagebox.showerror("Error al ejecutar", str(msg))

    elif action == "delete":
        if not messagebox.askyesno("Confirmar", f"¿Eliminar la tarea {task_display} del Programador?"):
            return
        ok, msg = delete_tarea_windows(task_display)
        if ok:
            # si tenemos la job guardada en config.ini, también la borramos
            if jobname:
                cfg = cargar_configparser()
                sec = f"job_{jobname}"
                if sec in cfg:
                    cfg.remove_section(sec)
                    guardar_configparser(cfg)
            refresh_all_tabs()
            messagebox.showinfo("Eliminada", f"Tarea {task_display} eliminada.")
        else:
            messagebox.showerror("Error eliminando", str(msg))

    elif action == "toggle":
        next_run, status = query_task_next_run(task_display)
        enable = True
        if status and ("Deshabilitada" in status or "Disabled" in status):
            enable = True
        else:
            enable = False
        ok, msg = change_tarea_windows_enable(task_display, enable=enable)
        if ok:
            refresh_all_tabs()
            messagebox.showinfo("Listo", f"Tarea {task_display} actualizada.")
        else:
            messagebox.showerror("Error", str(msg))

# -------------------------
# BACKUP MANUAL (completa)
# -------------------------
def hacer_backup_ui(is_programmed=False):
    usuario = entry_usuario.get().strip()
    contrasena = entry_contrasena.get().strip()
    base_datos = entry_bd.get().strip()
    destino = entry_destino.get().strip()

    if not usuario or not base_datos:
        messagebox.showerror("Error", "Completá usuario y base de datos.")
        return
    if not destino:
        messagebox.showerror("Error", "Seleccioná carpeta destino.")
        return
    if not carpeta_valida(destino):
        messagebox.showerror("Carpeta no permitida", "Esa carpeta está protegida. Elegí otra.")
        return

    fecha_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nombre_archivo = f"{base_datos}_backup_{fecha_str}.sql"
    ruta_completa = os.path.join(destino, nombre_archivo)

    ok, err = ejecutar_mysqldump(usuario, contrasena, base_datos, None, ruta_completa)
    if not ok:
        messagebox.showerror("Error", err)
        return

    # Preguntar compresión
    if messagebox.askyesno("Comprimir", "¿Querés comprimir el archivo .sql en zip y eliminar el .sql original?"):
        z = zip_file(ruta_completa, keep_original=False)
        ruta_guardada = z if z else ruta_completa
    else:
        ruta_guardada = ruta_completa

    agregar_copia(usuario, contrasena, base_datos, ruta_guardada)
    messagebox.showinfo("Éxito", f"Backup creado:\n{ruta_guardada}")

# -------------------------
# Programación legacy (local)
# -------------------------
TAREA_PROGRAMADA = {"fecha": None, "hora": None}
def verificar_programacion_legacy():
    if TAREA_PROGRAMADA.get("fecha") and TAREA_PROGRAMADA.get("hora"):
        ahora = datetime.datetime.now()
        try:
            fecha_prog = datetime.datetime.strptime(TAREA_PROGRAMADA["fecha"], "%Y-%m-%d")
            hora_prog = datetime.datetime.strptime(TAREA_PROGRAMADA["hora"], "%H:%M").time()
            fecha_hora_prog = datetime.datetime.combine(fecha_prog, hora_prog)
            if ahora >= fecha_hora_prog:
                hacer_backup_ui(is_programmed=True)
                TAREA_PROGRAMADA["fecha"] = None
                TAREA_PROGRAMADA["hora"] = None
        except Exception:
            TAREA_PROGRAMADA["fecha"] = None
            TAREA_PROGRAMADA["hora"] = None
    ventana.after(10000, verificar_programacion_legacy)

verificar_programacion_legacy()

# -------------------------
# MODO AUTOMÁTICO: entrada desde Programador de Windows (--auto --jobname NAME)
# -------------------------
def modo_automatico_entry_and_exit():
    if "--auto" in sys.argv:
        jobname = None
        if "--jobname" in sys.argv:
            try:
                idx = sys.argv.index("--jobname")
                jobname = sys.argv[idx+1]
            except:
                jobname = None
        if not jobname:
            cfg = cargar_configparser()
            for s in cfg.sections():
                if s.startswith("job_"):
                    jobname = s[len("job_"):]
                    break
        if jobname:
            ejecutar_job_auto(jobname)
        sys.exit(0)

modo_automatico_entry_and_exit()

# -------------------------
# REFRESCO PERIÓDICO (cada 10 segundos)
# -------------------------
def periodic_refresh():
    try:
        refresh_all_tabs()
        actualizar_tabla_historial()
    except Exception:
        pass
    ventana.after(10000, periodic_refresh)

periodic_refresh()

# -------------------------
# INICIAR INTERFAZ
# -------------------------
# Hacer un primer refresco al iniciar
refresh_all_tabs()
actualizar_tabla_historial()

# Ejecutar loop principal
ventana.mainloop()
