# ComfyUI-RotoTools: Windows folder dialog for "Load Video Batch (Folders)".
# Lets you pick several folders at once (Ctrl / Shift click) and prints their full paths, one per line.
# Prints nothing when cancelled. Started by the /rototools/batch/pick route; not meant to be run by hand.
param([string]$Start = "")

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace RotoTools {
  [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialogCls {}

  [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItem {
    void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
    void GetParent(out IShellItem ppsi);
    void GetDisplayName(uint sigdnName, [MarshalAs(UnmanagedType.LPWStr)] out string ppszName);
    void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
    void Compare(IShellItem psi, uint hint, out int piOrder);
  }

  [ComImport, Guid("B63EA76D-1F85-456F-A19C-48159EFA858B"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItemArray {
    void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppvOut);
    void GetPropertyStore(int flags, ref Guid riid, out IntPtr ppv);
    void GetPropertyDescriptionList(IntPtr keyType, ref Guid riid, out IntPtr ppv);
    void GetAttributes(int attribFlags, uint sfgaoMask, out uint psfgaoAttribs);
    void GetCount(out uint pdwNumItems);
    void GetItemAt(uint dwIndex, out IShellItem ppsi);
    void EnumItems(out IntPtr ppenumShellItems);
  }

  // IModalWindow + IFileDialog + IFileOpenDialog, in vtable order
  [ComImport, Guid("d57c7288-d4ad-4768-be02-9d969532d960"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IFileOpenDialog {
    [PreserveSig] int Show(IntPtr parent);
    void SetFileTypes(uint cFileTypes, IntPtr rgFilterSpec);
    void SetFileTypeIndex(uint iFileType);
    void GetFileTypeIndex(out uint piFileType);
    void Advise(IntPtr pfde, out uint pdwCookie);
    void Unadvise(uint dwCookie);
    void SetOptions(uint fos);
    void GetOptions(out uint pfos);
    void SetDefaultFolder(IShellItem psi);
    void SetFolder(IShellItem psi);
    void GetFolder(out IShellItem ppsi);
    void GetCurrentSelection(out IShellItem ppsi);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string pszName);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
    void GetResult(out IShellItem ppsi);
    void AddPlace(IShellItem psi, int fdap);
    void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string pszDefaultExtension);
    void Close(int hr);
    void SetClientGuid(ref Guid guid);
    void ClearClientData();
    void SetFilter(IntPtr pFilter);
    void GetResults(out IShellItemArray ppenum);
    void GetSelectedItems(out IShellItemArray ppsai);
  }

  public static class FolderPicker {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, ref Guid riid, out IShellItem item);

    const uint FOS_PICKFOLDERS = 0x20, FOS_FORCEFILESYSTEM = 0x40, FOS_ALLOWMULTISELECT = 0x200, FOS_PATHMUSTEXIST = 0x800;
    const uint SIGDN_FILESYSPATH = 0x80058000;
    const int ERROR_CANCELLED = unchecked((int)0x800704C7);
    const string TITLE = "Add video folders (Ctrl / Shift click to pick several)";

    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindowW(IntPtr cls, string title);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr pid);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();

    // ComfyUI starts this in the background, and Windows does not let a background process put a window in
    // front. So once the dialog exists: make it topmost and borrow the foreground window's input to focus it.
    static void BringToFront() {
      for (int i = 0; i < 100; i++) {
        System.Threading.Thread.Sleep(100);
        IntPtr h = FindWindowW(IntPtr.Zero, TITLE);
        if (h == IntPtr.Zero) continue;
        SetWindowPos(h, new IntPtr(-1), 0, 0, 0, 0, 0x0043);   // HWND_TOPMOST, NOMOVE | NOSIZE | SHOWWINDOW
        uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero), me = GetCurrentThreadId();
        bool attached = fg != 0 && fg != me && AttachThreadInput(me, fg, true);
        BringWindowToTop(h);
        SetForegroundWindow(h);
        if (attached) AttachThreadInput(me, fg, false);
        return;
      }
    }

    public static string[] Pick(IntPtr owner, string start) {
      var dlg = (IFileOpenDialog)new FileOpenDialogCls();
      dlg.SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_ALLOWMULTISELECT | FOS_PATHMUSTEXIST);
      dlg.SetTitle(TITLE);
      new System.Threading.Thread(BringToFront) { IsBackground = true }.Start();
      dlg.SetOkButtonLabel("Add folders");
      if (!String.IsNullOrEmpty(start)) {
        try {
          Guid iid = typeof(IShellItem).GUID;
          IShellItem si;
          SHCreateItemFromParsingName(start, IntPtr.Zero, ref iid, out si);
          dlg.SetFolder(si);
        } catch { }
      }
      int hr = dlg.Show(owner);
      if (hr == ERROR_CANCELLED) return new string[0];
      if (hr != 0) Marshal.ThrowExceptionForHR(hr);
      IShellItemArray arr;
      dlg.GetResults(out arr);
      uint n;
      arr.GetCount(out n);
      var res = new List<string>();
      for (uint i = 0; i < n; i++) {
        IShellItem it;
        arr.GetItemAt(i, out it);
        string p;
        it.GetDisplayName(SIGDN_FILESYSPATH, out p);
        res.Add(p);
      }
      return res.ToArray();
    }
  }
}
"@

# an invisible topmost owner window, so the dialog opens in front of the browser instead of behind it
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = "None"
$owner.StartPosition = "Manual"
$owner.Location = New-Object System.Drawing.Point(-32000, -32000)
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.Opacity = 0
$owner.Show()
$owner.Activate()
try {
    if ($Start -and -not (Test-Path -LiteralPath $Start -PathType Container)) { $Start = Split-Path -Parent $Start }
    foreach ($p in [RotoTools.FolderPicker]::Pick($owner.Handle, $Start)) { [Console]::Out.WriteLine($p) }
} finally {
    $owner.Close()
}
