' Lancia Vega: server Python (con UTF-8) in background + browser sulla loading
' Portable: usa la cartella in cui si trova questo file, non un percorso fisso.
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

' Determina la cartella in cui si trova questo .vbs
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

' Path al python in venv e al server
pythonExe = scriptDir & "\venv\Scripts\pythonw.exe"
serverPy = scriptDir & "\server.py"
loadingPage = "file:///" & Replace(scriptDir & "\ui\loading.html", "\", "/")

' 1. Avvia Python in background con -X utf8 (critico)
WshShell.Run """" & pythonExe & """ -X utf8 """ & serverPy & """", 0, False

' 2. Apri il browser sulla loading page
Dim edge, chrome, browserCmd
edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"

If fso.FileExists(chrome) Then
    browserCmd = """" & chrome & """ --app=" & loadingPage & " --start-fullscreen --window-size=1920,1080"
ElseIf fso.FileExists(edge) Then
    browserCmd = """" & edge & """ --app=" & loadingPage & " --start-fullscreen --window-size=1920,1080"
Else
    browserCmd = loadingPage
End If
WshShell.Run browserCmd, 1, False
