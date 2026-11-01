Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("Shell.Application")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = baseDir & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    pythonw = "pythonw.exe"
End If

cmd = """" & pythonw & """ """ & baseDir & "\app.py"""

shell.ShellExecute "cmd.exe", "/c """ & cmd & """", "", "runas", 0