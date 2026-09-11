Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\Semester 5\AI\my_ai"
WshShell.Run "pythonw.exe run.py", 0
Set WshShell = Nothing
