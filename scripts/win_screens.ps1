# Screenshots of the Windows app for the owner's comparison with the design canvas (SPEC.md,
# module `win-shell`, scope 4): the built app is started against this checkout with its data in
# a folder of its own, its window is captured with PrintWindow, and buttons are pressed through
# UI Automation (the accessibility interface, as a screen reader would). Light and dark follow
# the user's app theme, which this script sets for its run and puts back.
#
#   powershell -File scripts/win_screens.ps1 -App <path to Stickler.exe> -Out <folder>
#
# The sheet music (module `win-sheet`, W6) comes from the stand-in models of
# scripts/bridge_stand_ins.py: a recent song is opened through UI Automation, the window is
# captured once the pages are there, and the PDF is saved through Export's menu and the save
# dialog into -Out (checked by scripts/check_pdf.py).
param(
    [Parameter(Mandatory = $true)][string]$App,
    [Parameter(Mandatory = $true)][string]$Out,
    # on the owner's PC: "light" alone, so the desktop's theme is not switched under them
    [string[]]$Looks = @("light", "dark"),
    # the consent's "Not Now" in Windows' display language ("Nicht jetzt" in German)
    [string]$NotNow = "Not Now",
    # the words of Export's PDF entry and the save dialog's button, in Windows' display language
    # (its ellipsis written as a code: Windows PowerShell reads a file without a BOM in the ANSI code page)
    [string]$PdfEntry = "Sheet Music (PDF)" + [char]0x2026,
    [string]$Export = "Export",
    # leave out the sheet's screens (they set up the stand-in models first)
    [switch]$NoSheet,
    # only the sheet's screens (on a PC whose models are there, no consent comes)
    [switch]$SheetOnly
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing, System.Windows.Forms, UIAutomationClient, UIAutomationTypes
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

# the first element named $name in the process's windows (a menu's flyout or the save dialog
# is a window of its own), waiting up to $seconds for it
function Find-Named($process, $name, $seconds = 20) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $mine = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ProcessIdProperty), $process.Id
    $named = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::NameProperty), $name
    $until = (Get-Date).AddSeconds($seconds)
    do {
        foreach ($window in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $mine)) {
            $found = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $named)
            if ($found) { return $found }
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $until)
    throw "nothing named '$name'"
}

# presses $element, or the nearest element around it that can be pressed (a recent song's
# button holds its title as text), once it is enabled (up to $seconds: the core may still start)
function Invoke-Element($element, $seconds = 60) {
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $until = (Get-Date).AddSeconds($seconds)
    while ($element) {
        while (-not $element.Current.IsEnabled -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 500 }
        $pattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $pattern.Invoke(); return }
        if ($element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) { $pattern.Expand(); return }
        $element = $walker.GetParent($element)
    }
    throw "nothing to press"
}

# Windows' save dialog of the process: the file name typed into its box (1001), then Save (1)
function Save-As($process, $path) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $mine = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ProcessIdProperty), $process.Id
    $box = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::AutomationIdProperty), "1001"
    $until = (Get-Date).AddSeconds(20)
    do {
        foreach ($window in $root.FindAll([System.Windows.Automation.TreeScope]::Children, $mine)) {
            $name = $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $box)
            if ($name) {
                $name.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($path)
                # Enter in the name box, as a person saves (pressing Save through UI Automation
                # left Windows 11's dialog open, 2026-11-26)
                $name.SetFocus()
                Start-Sleep -Milliseconds 300
                [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
                return
            }
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $until)
    throw "no save dialog"
}

# the stand-in models and their song, set up once (uv, offline)
function Get-StandIns {
    $folder = Join-Path ([IO.Path]::GetTempPath()) ("stickler-screens-models-" + [Guid]::NewGuid().ToString("N"))
    $line = & uv run python scripts/bridge_stand_ins.py $folder | Select-Object -Last 1
    $line | ConvertFrom-Json
}

# W6: a recent song opened, its sheet captured; in light also the View menu and the PDF
function Save-Sheet($look, $standIns) {
    Remove-Item -Recurse -Force $dataHome -ErrorAction SilentlyContinue
    $recent = "$dataHome\data\stickler"
    New-Item -ItemType Directory -Force $recent | Out-Null
    $today = (Get-Date).ToString("yyyy-MM-dd")
    $entry = @(@{ path = $standIns.song; title = "Groove"; artist = ""; opened = $today })
    [IO.File]::WriteAllText("$recent\recent.json", (ConvertTo-Json -InputObject $entry))  # UTF-8 without a BOM
    # STICKLER_ADAPTERS: the app's core takes the stand-ins as they are (no consent, no download)
    $env:STICKLER_ADAPTERS = $standIns.models
    $process = Start-Process -FilePath $App -PassThru
    try {
        Invoke-Element (Find-Named $process "Groove" 60)
        # a result enables Export; then the engraving and WebView2's first start
        $exportButton = Find-Named $process $Export 60
        $until = (Get-Date).AddSeconds(180)
        while (-not $exportButton.Current.IsEnabled -and (Get-Date) -lt $until) { Start-Sleep -Seconds 1 }
        if (-not $exportButton.Current.IsEnabled) { Save-Window $process "W6-sheet-$look-no-result"; throw "no result" }
        Start-Sleep -Seconds 10
        Save-Window $process "W6-sheet-$look"
        if ($look -eq "light") {
            $pdf = Join-Path $Out "W6-sheet.pdf"
            # Export's menu, its PDF entry (opened again once if the menu was slow to come)
            $entry = $null
            foreach ($try in 1, 2) {
                Invoke-Element (Find-Named $process $Export)
                try { $entry = Find-Named $process $PdfEntry 10; break } catch { if ($try -eq 2) { throw } }
            }
            Invoke-Element $entry
            Save-As $process $pdf
            $until = (Get-Date).AddSeconds(90)  # WebView2's second view starts, prints, the file moves
            while (-not (Test-Path $pdf) -and (Get-Date) -lt $until) { Start-Sleep -Seconds 1 }
            Start-Sleep -Seconds 2
            Save-Window $process "W7-pdf-saved-$look"  # the note after saving, or why it failed
            "saved W6-sheet.pdf: $(Test-Path $pdf)"
        }
    }
    catch {
        Save-Window $process "W6-sheet-$look-failed"
        throw
    }
    finally {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Remove-Item Env:STICKLER_ADAPTERS -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

$theme = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
$before = (Get-ItemProperty $theme -Name AppsUseLightTheme -ErrorAction SilentlyContinue).AppsUseLightTheme
try {
    foreach ($look in @(@{ Name = "light"; Value = 1 }, @{ Name = "dark"; Value = 0 }) | Where-Object { $Looks -contains $_.Name -and -not $SheetOnly }) {
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
    if (-not $NoSheet) {
        $standIns = Get-StandIns
        foreach ($look in @(@{ Name = "light"; Value = 1 }, @{ Name = "dark"; Value = 0 }) | Where-Object { $Looks -contains $_.Name }) {
            Set-ItemProperty $theme -Name AppsUseLightTheme -Value $look.Value -Type DWord
            Save-Sheet $look.Name $standIns
        }
    }
}
finally {
    if ($null -ne $before) { Set-ItemProperty $theme -Name AppsUseLightTheme -Value $before -Type DWord }
    Remove-Item -Recurse -Force $dataHome -ErrorAction SilentlyContinue
}
