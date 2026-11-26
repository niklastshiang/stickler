namespace Stickler.Core;

/// <summary>What only Windows does for "Uninstall Stickler…": start the installer's
/// uninstaller, say something, end the app. The app answers with Windows; the tests with a fake.</summary>
public interface IUninstaller
{
    /// <summary>Starts the uninstaller silently; false when Windows refuses to start it (an
    /// antivirus that holds back a new program, as on the owner's PC).</summary>
    bool StartUninstaller();

    /// <summary>A message with a single button to close it.</summary>
    Task TellAsync(string text);

    /// <summary>Ends the app.</summary>
    void EndApp();
}

/// <summary>File › "Uninstall Stickler…" (SPEC.md, module <c>win-package</c>, scope 5; release
/// 10, scope B): the sizes, the question with the box off, then the core removes Stickler's
/// folders and replies once they are gone; the core is stopped, the uninstaller removes the
/// program silently (it waits for the app to end), and the app ends. If Windows does not start
/// the uninstaller, the app says that the data is gone and where the program can be removed.</summary>
public sealed class Uninstalling
{
    /// <summary>The uninstaller asks nothing and keeps the data (the core removed it already).</summary>
    public static readonly IReadOnlyList<string> SilentSwitches = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"];

    private readonly AppModel model;
    private readonly IAsk ask;
    private readonly IUninstaller windows;
    private readonly Strings strings;

    public Uninstalling(AppModel model, IAsk ask, IUninstaller windows, Strings strings)
    {
        this.model = model;
        this.ask = ask;
        this.windows = windows;
        this.strings = strings;
    }

    /// <summary>The uninstaller Inno Setup writes next to the app.</summary>
    public static string UninstallerPath(string appFolder) => Path.Combine(appFolder, "unins000.exe");

    /// <summary>Whether the menu offers "Uninstall Stickler…": only an installed app, whose
    /// folder has its core and its uninstaller (not a build from the checkout).</summary>
    public static bool Offered(string appFolder) =>
        CoreLaunch.HasInstalledCore(appFolder) && File.Exists(UninstallerPath(appFolder));

    public async Task RunAsync()
    {
        if (await model.UninstallSizesAsync().ConfigureAwait(true) is not { } sizes)
        {
            return;
        }
        var everything = await ask.ConfirmWithBoxAsync(
            strings.Text("Uninstall Stickler?"),
            sizes.KeepText,
            strings.Text("Uninstall"),
            strings.Text("Also remove my settings, recent songs and corrections")).ConfigureAwait(true);
        if (everything is not { } all || !await model.UninstallAsync(all).ConfigureAwait(true))
        {
            return; // Cancel, or the core refused (its notice says why): nothing is removed
        }
        await model.QuitAsync().ConfigureAwait(true);
        if (!windows.StartUninstaller())
        {
            await windows.TellAsync(
                strings.Text("Stickler’s data is removed. Remove the program later in Settings › Apps.")).ConfigureAwait(true);
        }
        windows.EndApp();
    }
}
