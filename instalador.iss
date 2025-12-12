; ===========================
; INSTALADOR BACKUP MYSQL PRO
; ===========================

[Setup]
AppName=Backup MySQL Pro
AppVersion=1.1
AppPublisher=Backup MySQL Pro
DefaultDirName={autopf}\BackupMySQLPro
DefaultGroupName=Backup MySQL Pro
OutputBaseFilename=Instalador_BackupMySQLPro
Compression=lzma
SolidCompression=yes
LanguageDetectionMethod=locale
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

;----------------------------------------
; ARCHIVOS A INSTALAR
;----------------------------------------
[Files]
; Ejecutable principal (generado con PyInstaller)
Source: "BackupMySQLPro.exe"; DestDir: "{app}"; Flags: ignoreversion

; Archivo de configuración
Source: "config.ini"; DestDir: "{app}"; Flags: ignoreversion

; Historial de copias (si no existe, se copia vacío)
Source: "copias.json"; DestDir: "{app}"; Flags: ignoreversion

;----------------------------------------
; ACCESOS DIRECTOS
;----------------------------------------
[Icons]
Name: "{commondesktop}\Backup MySQL Pro"; Filename: "{app}\BackupMySQLPro.exe"
Name: "{group}\Backup MySQL Pro"; Filename: "{app}\BackupMySQLPro.exe"

;----------------------------------------
; POST INSTALACIÓN
;----------------------------------------
[Run]
Filename: "{app}\BackupMySQLPro.exe"; \
Description: "Iniciar Backup MySQL Pro ahora"; \
Flags: nowait postinstall skipifsilent shellexec


