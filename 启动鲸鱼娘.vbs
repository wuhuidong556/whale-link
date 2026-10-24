Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "D:\deepseek工作区\whale-link"
sh.Run """C:\Users\74187\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe"" server\app.py", 0, False
WScript.Sleep 2500
sh.Run """C:\Users\74187\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe"" pet.py", 0, False
