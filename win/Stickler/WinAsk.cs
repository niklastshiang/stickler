using System.Diagnostics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Stickler.Core;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.System;
using WinRT.Interop;

namespace Stickler;

/// <summary>The questions only Windows answers (<see cref="IAsk"/>): its file dialogs, a
/// ContentDialog for each question (W7's dialogs, Windows' button order: the main one on the
/// left, Cancel on the right), Explorer and "Open with". A pure view: tested by hand.</summary>
internal sealed class WinAsk(Window window, Strings strings) : IAsk
{
    private IntPtr Handle => WindowNative.GetWindowHandle(window);

    /// <summary>Set, it answers a save dialog for its file's ending without a window: the
    /// runner's screenshots save the PDF there (owner, 2026-11-26: Windows' dialog cannot be
    /// driven by a script; the dialog itself is the same as the MusicXML's and is checked by
    /// hand). A dialog for another ending opens as always.</summary>
    public const string SaveAsVariable = "STICKLER_SAVE_AS";

    public async Task<string?> SaveFileAsync(string name, IReadOnlyList<string> endings)
    {
        if (System.Environment.GetEnvironmentVariable(SaveAsVariable) is { Length: > 0 } given
            && endings.Contains(Path.GetExtension(given).TrimStart('.'), StringComparer.OrdinalIgnoreCase))
        {
            return given;
        }
        var picker = new FileSavePicker { SuggestedFileName = Path.GetFileNameWithoutExtension(name) };
        string[] wanted = endings.Count > 0 ? [.. endings] : [Path.GetExtension(name).TrimStart('.')];
        foreach (var ending in wanted)
        {
            picker.FileTypeChoices.Add(ending.ToUpperInvariant(), ["." + ending]);
        }
        InitializeWithWindow.Initialize(picker, Handle);
        var file = await picker.PickSaveFileAsync();
        return file?.Path;
    }

    public async Task<string?> OpenFileAsync(IReadOnlyList<string> endings)
    {
        var picker = new FileOpenPicker();
        foreach (var ending in endings)
        {
            picker.FileTypeFilter.Add("." + ending);
        }
        if (endings.Count == 0)
        {
            picker.FileTypeFilter.Add("*");
        }
        InitializeWithWindow.Initialize(picker, Handle);
        var file = await picker.PickSingleFileAsync();
        return file?.Path;
    }

    public async Task<bool> ConfirmAsync(string title, string text, string action)
    {
        var dialog = Dialog(title, new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap }, action);
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    public async Task<bool?> ConfirmWithBoxAsync(string title, string text, string action, string box)
    {
        var check = new CheckBox { Content = box };
        var content = new StackPanel { Spacing = 12 };
        content.Children.Add(new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap });
        content.Children.Add(check);
        var dialog = Dialog(title, content, action);
        return await dialog.ShowAsync() == ContentDialogResult.Primary ? check.IsChecked == true : null;
    }

    public async Task OpenWithAsync(string file)
    {
        var options = new LauncherOptions { DisplayApplicationPicker = true };
        InitializeWithWindow.Initialize(options, Handle);
        await Launcher.LaunchFileAsync(await StorageFile.GetFileFromPathAsync(file), options);
    }

    /// <summary>Explorer with <paramref name="file"/> selected ("Show in Folder").</summary>
    public static void ShowInFolder(string file) =>
        Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{file}\"") { UseShellExecute = false })?.Dispose();

    private ContentDialog Dialog(string title, object content, string action) => new()
    {
        XamlRoot = window.Content.XamlRoot,
        Title = title,
        Content = content,
        PrimaryButtonText = action,
        CloseButtonText = strings.Text("Cancel"),
        DefaultButton = ContentDialogButton.Primary,
    };
}
