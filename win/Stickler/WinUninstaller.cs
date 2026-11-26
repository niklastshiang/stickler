using System.ComponentModel;
using System.Diagnostics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Stickler.Core;

namespace Stickler;

/// <summary>"Uninstall Stickler…" on Windows (<see cref="IUninstaller"/>): the installer's
/// uninstaller started silently from the app's folder, a ContentDialog, the window closed. A
/// pure view: tested by hand and by the release workflow's start test.</summary>
internal sealed class WinUninstaller(Window window, Strings strings) : IUninstaller
{
    public bool StartUninstaller()
    {
        var start = new ProcessStartInfo(Uninstalling.UninstallerPath(AppContext.BaseDirectory))
        {
            UseShellExecute = false,
        };
        foreach (var argument in Uninstalling.SilentSwitches)
        {
            start.ArgumentList.Add(argument);
        }
        try
        {
            using var started = Process.Start(start);
            return started is not null;
        }
        catch (Win32Exception)
        {
            return false; // refused: an antivirus holding back a new program ("Access denied")
        }
    }

    public async Task TellAsync(string text)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = window.Content.XamlRoot,
            Title = "Stickler",
            Content = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap },
            CloseButtonText = strings.Text("Close"),
            DefaultButton = ContentDialogButton.Close,
        };
        await dialog.ShowAsync();
    }

    /// <summary>The window closes and the process ends for certain: the uninstaller waits for it
    /// only so long, and what the app still held would stay behind in its folder.</summary>
    public void EndApp()
    {
        window.Close();
        Application.Current.Exit();
    }
}
