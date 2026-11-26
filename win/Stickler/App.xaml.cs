using Microsoft.UI.Xaml;

namespace Stickler;

/// <summary>The app: one window over the core.</summary>
public partial class App : Application
{
    /// <summary>Held while the app runs, so the installer and the uninstaller ask to close it
    /// first (<c>AppMutex</c> in <c>win/installer/Stickler.iss</c>).</summary>
    internal static Mutex Running { get; } = new(false, "ng.tshia.Stickler");

    private MainWindow? window;

    public App() => InitializeComponent();

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        window = new MainWindow();
        // the title bar's and the taskbar's icon (SPEC.md, module `win-package`, scope 7)
        window.AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Stickler.ico"));
        window.Activate();
    }
}
