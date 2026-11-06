// Volume d'UNE appli (mélangeur de volume Windows), utilisé par lecture_suivi.ps1 pour le lecteur de JARVIS.
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Jarvis {
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator { }

  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    [PreserveSig] int EnumAudioEndpoints(int dataFlow, int dwStateMask, out IMMDeviceCollection ppDevices);
    [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ppDevice);
  }

  [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceCollection {
    [PreserveSig] int GetCount(out uint pcDevices);
    [PreserveSig] int Item(uint nDevice, out IMMDevice ppDevice);
  }

  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    [PreserveSig] int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, [MarshalAs(UnmanagedType.IUnknown)] out object ppInterface);
  }

  [Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionManager2 {
    int NotImpl1(); int NotImpl2();
    [PreserveSig] int GetSessionEnumerator(out IAudioSessionEnumerator SessionEnum);
  }

  [Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionEnumerator {
    [PreserveSig] int GetCount(out int SessionCount);
    [PreserveSig] int GetSession(int SessionCount, out IAudioSessionControl2 Session);
  }

  [Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionControl2 {
    int NotImpl0(); int NotImpl1(); int NotImpl2(); int NotImpl3(); int NotImpl4(); int NotImpl5(); int NotImpl6();
    int NotImpl7(); int NotImpl8();
    [PreserveSig] int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
    [PreserveSig] int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string pRetVal);
    [PreserveSig] int GetProcessId(out uint pRetVal);
  }

  [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface ISimpleAudioVolume {
    [PreserveSig] int SetMasterVolume(float fLevel, ref Guid EventContext);
    [PreserveSig] int GetMasterVolume(out float pfLevel);
    [PreserveSig] int SetMute(bool bMute, ref Guid EventContext);
    [PreserveSig] int GetMute(out bool pbMute);
  }

  [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioEndpointVolume {
    int NotImpl0(); int NotImpl1(); int NotImpl2(); int NotImpl3();
    [PreserveSig] int SetMasterVolumeLevelScalar(float fLevel, ref Guid pguidEventContext);
    int NotImpl5();
    [PreserveSig] int GetMasterVolumeLevelScalar(out float pfLevel);
    int NotImpl7(); int NotImpl8(); int NotImpl9(); int NotImpl10();
    [PreserveSig] int SetMute(bool bMute, ref Guid pguidEventContext);
    [PreserveSig] int GetMute(out bool pbMute);
  }

  public static class AppVolume {
    static IAudioEndpointVolume Master() {
      var en = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
      IMMDevice dev; if (en.GetDefaultAudioEndpoint(0, 1, out dev) != 0) return null;
      Guid iid = typeof(IAudioEndpointVolume).GUID; object o;
      if (dev.Activate(ref iid, 23, IntPtr.Zero, out o) != 0) return null;
      return (IAudioEndpointVolume)o;
    }
    // volume général du PC (haut-parleurs / casque par défaut) : « vol|muet »
    public static string MasterState() {
      var m = Master(); if (m == null) return "-1|0";
      float f; m.GetMasterVolumeLevelScalar(out f); bool mu; m.GetMute(out mu);
      return (int)Math.Round(f * 100) + "|" + (mu ? 1 : 0);
    }
    public static void MasterSet(int pct) { var m = Master(); if (m == null) return; Guid g = Guid.Empty;
      m.SetMasterVolumeLevelScalar(Math.Max(0, Math.Min(100, pct)) / 100f, ref g); if (pct > 0) m.SetMute(false, ref g); }
    public static void MasterMute() { var m = Master(); if (m == null) return; Guid g = Guid.Empty; bool mu; m.GetMute(out mu); m.SetMute(!mu, ref g); }

    // toutes les applis qui ont un son ouvert : « programme|nom affiché|vol|muet » (une ligne par programme)
    public static string[] Dump() {
      var r = new System.Collections.Generic.List<string>();
      foreach (var c in AllSessions()) { uint pid = 0; string err = "";
        try { c.GetProcessId(out pid); } catch (Exception e) { err = "pid:" + e.Message; }
        string nm = ""; try { nm = Process.GetProcessById((int)pid).ProcessName; } catch (Exception e) { err += " name:" + e.Message; }
        string id = ""; try { c.GetSessionIdentifier(out id); } catch { }
        r.Add(pid + " " + nm + " " + err + " " + (id.Length > 90 ? id.Substring(id.Length - 90) : id)); }
      return r.ToArray();
    }
    public static string[] List() {
      var seen = new System.Collections.Generic.Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
      foreach (var c in AllSessions()) {
        uint pid; c.GetProcessId(out pid);
        if (pid == 0) continue;  // sons système
        try {
          var p = Process.GetProcessById((int)pid); string exe = p.ProcessName;
          if (seen.ContainsKey(exe)) continue;
          string name = exe;
          try { var d = p.MainModule.FileVersionInfo.FileDescription; if (!string.IsNullOrEmpty(d)) name = d; } catch { }
          var v = (ISimpleAudioVolume)c; float f; v.GetMasterVolume(out f); bool mu; v.GetMute(out mu);
          seen[exe] = exe + "|" + name.Replace("|", " ") + "|" + (int)Math.Round(f * 100) + "|" + (mu ? 1 : 0);
        } catch { }
      }
      var r = new string[seen.Count]; seen.Values.CopyTo(r, 0); return r;
    }

    // toutes les sessions audio (sortie par défaut) des processus portant ce nom (ex. « Deezer »)
    // sessions audio de toutes les sorties actives (une appli peut jouer sur le casque et pas sur la sortie par défaut)
    static System.Collections.Generic.List<IAudioSessionControl2> AllSessions() {
      var list = new System.Collections.Generic.List<IAudioSessionControl2>();
      var en = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
      IMMDeviceCollection col; if (en.EnumAudioEndpoints(0, 1, out col) != 0) return list;
      uint nd; col.GetCount(out nd);
      for (uint d = 0; d < nd; d++) {
        IMMDevice dev; if (col.Item(d, out dev) != 0) continue;
        Guid iid = typeof(IAudioSessionManager2).GUID; object o;
        if (dev.Activate(ref iid, 23, IntPtr.Zero, out o) != 0) continue;
        IAudioSessionEnumerator se; if (((IAudioSessionManager2)o).GetSessionEnumerator(out se) != 0) continue;
        int n; se.GetCount(out n);
        for (int i = 0; i < n; i++) { IAudioSessionControl2 c; if (se.GetSession(i, out c) == 0) list.Add(c); }
      }
      return list;
    }
    static System.Collections.Generic.List<ISimpleAudioVolume> Sessions(string exe) {
      var list = new System.Collections.Generic.List<ISimpleAudioVolume>();
      foreach (var c in AllSessions()) {
        uint pid; c.GetProcessId(out pid);
        try { if (pid != 0 && Process.GetProcessById((int)pid).ProcessName.Equals(exe, StringComparison.OrdinalIgnoreCase)) list.Add((ISimpleAudioVolume)c); }
        catch { }
      }
      return list;
    }
    // volume 0-100, ou -1 si l'appli n'a pas de son ouvert
    public static int Get(string exe) {
      foreach (var v in Sessions(exe)) { float f; v.GetMasterVolume(out f); return (int)Math.Round(f * 100); }
      return -1;
    }
    public static bool Muted(string exe) {
      foreach (var v in Sessions(exe)) { bool m; v.GetMute(out m); return m; }
      return false;
    }
    public static void Set(string exe, int pct) {
      Guid g = Guid.Empty; float f = Math.Max(0, Math.Min(100, pct)) / 100f;
      foreach (var v in Sessions(exe)) { v.SetMasterVolume(f, ref g); if (pct > 0) v.SetMute(false, ref g); }
    }
    public static void ToggleMute(string exe) {
      Guid g = Guid.Empty; bool m = !Muted(exe);
      foreach (var v in Sessions(exe)) v.SetMute(m, ref g);
    }
  }
}
