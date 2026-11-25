using Microsoft.UI.Xaml;

namespace Stickler;

/// <summary>The app: one window over the core.</summary>
public partial class App : Application
{
    private MainWindow? window;

    public App() => InitializeComponent();

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        window = new MainWindow();
        window.Activate();
    }
}
