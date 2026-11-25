# Screenshots of the Windows app for the owner's comparison with the design canvas (SPEC.md,
# module `win-shell`, scope 4): the built app is started against this checkout with its data in
# a folder of its own, its window is captured with PrintWindow, and buttons are pressed through
# UI Automation (the accessibility interface, as a screen reader would). Light and dark follow
# the user's app theme, which this script sets for its run and puts back.
#
#   powershell -File scripts/win_screens.ps1 -App <path to Stickler.exe> -Out <folder>
param(
    [Parameter(Mandatory = $true)][string]$App,
    [Parameter(Mandatory = $true)][string]$Out,
    # on the owner's PC: "light" alone, so the desktop's theme is not switched under them
    [string[]]$Looks = @("light", "dark"),
    # the consent's "Not Now" in Windows' display language ("Nicht jetzt" in German)
    [string]$NotNow = "Not Now"
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing, UIAutomationClient, UIAutomationTypes
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Screens {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
}
"@
New-Item -ItemType Directory -Force $Out | Out-Null
$dataHome = Join-Path ([IO.Path]::GetTempPath()) ("stickler-screens-" + [Guid]::NewGuid().ToString("N"))
$env:XDG_DATA_HOME = "$dataHome\data"; $env:XDG_CACHE_HOME = "$dataHome\cache"; $env:XDG_CONFIG_HOME = "$dataHome\config"
$env:STICKLER_RESULTS_CACHE = "$dataHome\results"

function Save-Window($process, $name) {
    $process.Refresh()
    $h = $process.MainWindowHandle
    if ([Screens]::IsIconic($h)) { [Screens]::ShowWindow($h, 9) | Out-Null; Start-Sleep -Milliseconds 800 }
    $r = New-Object Screens+RECT
    [Screens]::GetWindowRect($h, [ref]$r) | Out-Null
    $bitmap = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
    $g = [System.Drawing.Graphics]::FromImage($bitmap)
    $dc = $g.GetHdc()
    [Screens]::PrintWindow($h, $dc, 2) | Out-Null  # 2: the window's full content, DirectComposition included
    $g.ReleaseHdc($dc); $g.Dispose()
    $bitmap.Save((Join-Path $Out "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    "saved $name.png"
}

function Invoke-Button($process, $name) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $mine = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ProcessIdProperty), $process.Id
    $window = $root.FindFirst([System.Windows.Automation.TreeScope]::Children, $mine)
    $named = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::NameProperty), $name
    $button = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $named)
    if (-not $button) { throw "no button '$name'" }
    $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}

$theme = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
$before = (Get-ItemProperty $theme -Name AppsUseLightTheme -ErrorAction SilentlyContinue).AppsUseLightTheme
try {
    foreach ($look in @(@{ Name = "light"; Value = 1 }, @{ Name = "dark"; Value = 0 }) | Where-Object { $Looks -contains $_.Name }) {
        New-Item -Force $theme | Out-Null
        Set-ItemProperty $theme -Name AppsUseLightTheme -Value $look.Value -Type DWord
        Remove-Item -Recurse -Force $dataHome -ErrorAction SilentlyContinue
        $process = Start-Process -FilePath $App -PassThru
        Start-Sleep -Seconds 25  # the core starts through uv and asks for consent (no models here)
        Save-Window $process "W1-consent-$($look.Name)"
        Invoke-Button $process $NotNow
        Start-Sleep -Seconds 3
        Save-Window $process "W4-empty-$($look.Name)"
        Stop-Process -Id $process.Id -Force
        Start-Sleep -Seconds 2
    }
}
finally {
    if ($null -ne $before) { Set-ItemProperty $theme -Name AppsUseLightTheme -Value $before -Type DWord }
    Remove-Item -Recurse -Force $dataHome -ErrorAction SilentlyContinue
}
