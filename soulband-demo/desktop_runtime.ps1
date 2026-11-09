# Restore normal image labels on this venv's desktop runtime. A Low image label
# lowers Python's token and is rejected by Chromium's image-load mitigations.
# Do not change DACLs, user data, system directories, or Chromium sandbox flags.
function Get-SoulbandFileIntegrity {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not ('Soulband.FileIntegrity' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
namespace Soulband {
    public static class FileIntegrity {
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        static extern uint GetNamedSecurityInfoW(string name, int type, uint info,
            IntPtr owner, IntPtr group, IntPtr dacl, out IntPtr sacl, out IntPtr descriptor);
        [DllImport("advapi32.dll", SetLastError=true)]
        static extern bool GetAce(IntPtr acl, uint index, out IntPtr ace);
        [DllImport("advapi32.dll")]
        static extern IntPtr GetSidSubAuthorityCount(IntPtr sid);
        [DllImport("advapi32.dll")]
        static extern IntPtr GetSidSubAuthority(IntPtr sid, uint index);
        [DllImport("kernel32.dll")]
        static extern IntPtr LocalFree(IntPtr memory);
        public static int Read(string path) {
            IntPtr acl, descriptor;
            uint error = GetNamedSecurityInfoW(path, 1, 0x10, IntPtr.Zero,
                IntPtr.Zero, IntPtr.Zero, out acl, out descriptor);
            if (error != 0) throw new Win32Exception((int)error, path);
            try {
                if (acl == IntPtr.Zero) return 8192; // Unlabelled objects default to Medium.
                int count = (ushort)Marshal.ReadInt16(acl, 4);
                for (uint i = 0; i < count; i++) {
                    IntPtr ace;
                    if (!GetAce(acl, i, out ace)) throw new Win32Exception(Marshal.GetLastWin32Error());
                    if (Marshal.ReadByte(ace) != 0x11) continue;
                    IntPtr sid = IntPtr.Add(ace, 8);
                    byte subCount = Marshal.ReadByte(GetSidSubAuthorityCount(sid));
                    if (subCount > 0) return Marshal.ReadInt32(GetSidSubAuthority(sid, (uint)(subCount - 1)));
                }
                return 8192;
            } finally { LocalFree(descriptor); }
        }
    }
}
'@
    }
    return [Soulband.FileIntegrity]::Read([IO.Path]::GetFullPath($Path))
}

function Repair-SoulbandDesktopRuntime {
    param([Parameter(Mandatory = $true)][string]$Python)
    $desktopPython = [IO.Path]::GetFullPath($Python)
    $desktopScripts = Split-Path -Parent $desktopPython
    if ((Split-Path -Leaf $desktopScripts) -ne 'Scripts' -or
        (Split-Path -Leaf $desktopPython) -ne 'python.exe') {
        throw 'Desktop runtime repair requires a Windows venv Scripts/python.exe.'
    }
    $desktopQt = Join-Path (Split-Path -Parent $desktopScripts) 'Lib\site-packages\PySide6'
    $desktopRepaired = 0
    foreach ($desktopDirectory in @($desktopScripts, $desktopQt)) {
        if (-not (Test-Path -LiteralPath $desktopDirectory -PathType Container)) { continue }
        if ((Get-SoulbandFileIntegrity -Path $desktopDirectory) -lt 8192) {
            & icacls.exe $desktopDirectory /setintegritylevel '(OI)(CI)M' | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Cannot restore runtime label: $desktopDirectory" }
            $desktopRepaired++
        }
    }
    $desktopImages = @($desktopPython, (Join-Path $desktopScripts 'pythonw.exe'))
    if (Test-Path -LiteralPath $desktopQt) {
        $desktopImages += @(Get-ChildItem -LiteralPath $desktopQt -Recurse -File |
            Where-Object { $_.Extension -in @('.exe', '.dll', '.pyd') } |
            Select-Object -ExpandProperty FullName)
    }
    foreach ($desktopImage in $desktopImages) {
        if (-not (Test-Path -LiteralPath $desktopImage -PathType Leaf)) { continue }
        if ((Get-SoulbandFileIntegrity -Path $desktopImage) -lt 8192) {
            & icacls.exe $desktopImage /setintegritylevel M | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Cannot restore runtime image label: $desktopImage" }
            $desktopRepaired++
        }
    }
    if ($desktopRepaired -gt 0) { Write-Host 'Restored desktop runtime to normal Windows Medium integrity.' }
}
