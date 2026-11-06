# Raccourci « JARVIS » dans le menu Démarrer, avec l'icône de JARVIS et la même identité (AppUserModelID) que sa
# fenêtre : Windows s'en sert pour la barre des tâches. Épingler JARVIS affiche alors son logo (et pas celui de
# Python), et cliquer sur l'épingle ouvre ou réveille JARVIS. Lancé automatiquement par jarvis_window.py.
$ErrorActionPreference = "Stop"
$voice = $PSScriptRoot
$pyw = Join-Path (Split-Path $voice -Parent) "src\.venv\Scripts\pythonw.exe"
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "JARVIS.lnk"

Add-Type -Language CSharp -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")] class CShellLink {}
[ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IShellLinkW {
  void GetPath(IntPtr a, int b, IntPtr c, int d); void GetIDList(out IntPtr p); void SetIDList(IntPtr p);
  void GetDescription(IntPtr a, int b); void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetWorkingDirectory(IntPtr a, int b); void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetArguments(IntPtr a, int b); void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetHotkey(out short h); void SetHotkey(short h); void GetShowCmd(out int c); void SetShowCmd(int c);
  void GetIconLocation(IntPtr a, int b, out int c); void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
  void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, int r); void Resolve(IntPtr h, int f);
  void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
}
[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore {
  void GetCount(out uint c); void GetAt(uint i, out PropKey k); void GetValue(ref PropKey k, out PropVariant v);
  void SetValue(ref PropKey k, ref PropVariant v); void Commit();
}
[StructLayout(LayoutKind.Sequential, Pack = 4)] public struct PropKey { public Guid fmtid; public uint pid; }
[StructLayout(LayoutKind.Explicit)] public struct PropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }

public static class JarvisShortcut {
  public static void Create(string lnk, string target, string args, string dir, string icon, string appId) {
    var link = (IShellLinkW)new CShellLink();
    link.SetPath(target); link.SetArguments(args); link.SetWorkingDirectory(dir);
    link.SetIconLocation(icon, 0); link.SetDescription("JARVIS, assistant vocal");
    var store = (IPropertyStore)link;
    var key = new PropKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };
    var v = new PropVariant { vt = 31, p = Marshal.StringToCoTaskMemUni(appId) };  // VT_LPWSTR
    store.SetValue(ref key, ref v); store.Commit();
    Marshal.FreeCoTaskMem(v.p);
    ((IPersistFile)link).Save(lnk, true);
  }
}
'@
[JarvisShortcut]::Create($lnk, $pyw, "`"$(Join-Path $voice 'jarvis_voice.py')`"", $voice, (Join-Path $voice "jarvis.ico"), "JARVIS.VoiceAssistant")
Write-Output $lnk
