' Silent GUI launcher ¡ª no console window.
' Prefer this file. Æô¶¯GUI.bat only forwards here (may flash cmd ~0.1s).

Option Explicit

Dim sh, fso, root, app, ico, lnk, pyw
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
app = root & "\gui\app.py"
ico = root & "\assets\app_icon.ico"
lnk = root & "\HotelPriceAnalyzer.lnk"

If Not fso.FileExists(app) Then
  MsgBox "GUI file not found:" & vbCrLf & app, vbCritical, "Hotel Price Analyzer"
  WScript.Quit 1
End If

pyw = FindPythonw()
If pyw = "" Then
  MsgBox "pythonw.exe not found." & vbCrLf & _
    "Install Python 3 and check 'Add python.exe to PATH'.", _
    vbCritical, "Hotel Price Analyzer"
  WScript.Quit 1
End If

On Error Resume Next
Dim sc
Set sc = sh.CreateShortcut(lnk)
sc.TargetPath = pyw
sc.Arguments = Chr(34) & app & Chr(34)
sc.WorkingDirectory = root
If fso.FileExists(ico) Then sc.IconLocation = ico & ",0"
sc.WindowStyle = 1
sc.Description = "Hotel Price Analyzer"
sc.Save
On Error GoTo 0

sh.Run Chr(34) & pyw & Chr(34) & " " & Chr(34) & app & Chr(34), 0, False
WScript.Quit 0


Function FindPythonw()
  Dim cand, i, parts, pathEnv, base, bases
  FindPythonw = ""

  pathEnv = sh.ExpandEnvironmentStrings("%PATH%")
  parts = Split(pathEnv, ";")
  For i = 0 To UBound(parts)
    base = Trim(parts(i))
    If base <> "" Then
      If Right(base, 1) <> "\" Then base = base & "\"
      cand = base & "pythonw.exe"
      If fso.FileExists(cand) Then
        FindPythonw = cand
        Exit Function
      End If
    End If
  Next

  bases = Array( _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313"), _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312"), _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python311"), _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python310"), _
    "C:\Python312", _
    "C:\Python311", _
    "C:\Program Files\Python312", _
    "C:\Program Files\Python311" _
  )
  For i = 0 To UBound(bases)
    cand = bases(i) & "\pythonw.exe"
    If fso.FileExists(cand) Then
      FindPythonw = cand
      Exit Function
    End If
  Next

  For i = 0 To UBound(parts)
    base = Trim(parts(i))
    If base <> "" Then
      If Right(base, 1) <> "\" Then base = base & "\"
      If fso.FileExists(base & "python.exe") Then
        cand = base & "pythonw.exe"
        If fso.FileExists(cand) Then
          FindPythonw = cand
          Exit Function
        End If
      End If
    End If
  Next
End Function
