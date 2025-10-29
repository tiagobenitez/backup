import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import datetime
import os

def hacer_backup():
    usuario = entry_usuario.get().strip()
    contrasena = entry_contrasena.get().strip()
    base_datos = entry_bd.get().strip()
    destino = entry_destino.get().strip()

    if not usuario or not base_datos or not destino:
        messagebox.showerror("Error", "Completá Usuario, Base de Datos y Carpeta de destino.")
        return

    fecha = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nombre_archivo = f"{base_datos}_backup_{fecha}.sql"
    ruta_completa = os.path.join(destino, nombre_archivo)

    try:
        comando = ["mysqldump", "-u", usuario]
        if contrasena:
            comando.append(f"-p{contrasena}")
        comando.append(base_datos)

        with open(ruta_completa, "w", encoding="utf-8") as salida:
            resultado = subprocess.run(comando, stdout=salida, stderr=subprocess.PIPE, text=True)

        if resultado.returncode == 0:
            messagebox.showinfo("Éxito", f"Backup creado:\n{ruta_completa}")
        else:
            messagebox.showerror("Error", f"Ocurrió un error:\n{resultado.stderr}")

    except FileNotFoundError:
        messagebox.showerror("Error", "No se encontró 'mysqldump'. Agregalo al PATH o usa ruta completa.")
    except Exception as e:
        messagebox.showerror("Error", f"Error inesperado:\n{str(e)}")

def seleccionar_destino():
    carpeta = filedialog.askdirectory()
    if carpeta:
        entry_destino.delete(0, tk.END)
        entry_destino.insert(0, carpeta)

# 🕒 Backup automático
def iniciar_respaldo_automatico():
    try:
        minutos = int(entry_intervalo.get())
        if minutos <= 0:
            raise ValueError
        intervalo_ms = minutos * 60 * 1000  # convertir a milisegundos
        programar_backup(intervalo_ms)
        messagebox.showinfo("Automático", f"Se realizará un backup cada {minutos} minutos.")
    except ValueError:
        messagebox.showerror("Error", "Ingresá un número de minutos válido.")

def programar_backup(intervalo_ms):
    hacer_backup()  # hacer el backup ahora
    ventana.after(intervalo_ms, lambda: programar_backup(intervalo_ms))  # volver a llamarlo

# 🎨 Interfaz
ventana = tk.Tk()
ventana.title("Backup MySQL Automático")
ventana.geometry("420x400")
ventana.resizable(False, False)

tk.Label(ventana, text="Usuario MySQL:").pack(pady=5)
entry_usuario = tk.Entry(ventana, width=40)
entry_usuario.insert(0, "root")  # por defecto
entry_usuario.pack()

tk.Label(ventana, text="Contraseña:").pack(pady=5)
entry_contrasena = tk.Entry(ventana, show="*", width=40)
entry_contrasena.pack()

tk.Label(ventana, text="Base de datos:").pack(pady=5)
entry_bd = tk.Entry(ventana, width=40)
entry_bd.insert(0, "miguelhogar")  # por defecto
entry_bd.pack()

tk.Label(ventana, text="Carpeta destino:").pack(pady=5)
entry_destino = tk.Entry(ventana, width=30)
entry_destino.pack(side=tk.LEFT, padx=(20, 0))
tk.Button(ventana, text="Seleccionar", command=seleccionar_destino).pack(side=tk.RIGHT, padx=(0, 20), pady=5)

# Botón manual
tk.Button(ventana, text="Hacer Backup Ahora", command=hacer_backup, bg="#4CAF50", fg="white").pack(pady=20)

# Intervalo automático
tk.Label(ventana, text="Backup automático (cada X minutos):").pack(pady=5)
entry_intervalo = tk.Entry(ventana, width=10)
entry_intervalo.insert(0, "30")  # valor por defecto
entry_intervalo.pack()

tk.Button(ventana, text="Iniciar respaldo automático", command=iniciar_respaldo_automatico, bg="#2196F3", fg="white").pack(pady=10)

ventana.mainloop()
