using System.ComponentModel;
using System.Globalization;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Stickler.Core;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.System.UserProfile;
using Page = Stickler.Core.Page;

namespace Stickler;

/// <summary>The window of design screens W1–W5, W7 and W8 (SPEC.md, module <c>win-shell</c>).
/// It draws what <see cref="AppModel"/> and <see cref="WindowView"/> say and forwards every
/// click as one action; it decides nothing itself. A pure view: checked by screenshots and by
/// hand, not counted for coverage.</summary>
public sealed partial class MainWindow : Window
{
    private const string Readme = "https://github.com/niklastshiang/stickler#readme";
    private const string LicencePage = "https://github.com/niklastshiang/stickler/blob/main/LICENSE";

    private readonly Strings strings;
    private readonly AppModel model;
    private readonly Flows flows;
    private readonly Uninstalling uninstalling;
    private readonly WinAsk ask;
    private readonly DispatcherQueueTimer noticeTimer;
    private ContentDialog? setup;
    private SetupDialog shownSetup = SetupDialog.None;
    private bool closingSetup;
    private AppState? setupState;
    private IReadOnlyList<RecentRow>? shownRecent;
    private bool shownCanOpen;

    /// <summary>A question of the File or Export menu or About is on screen: WinUI allows one
    /// ContentDialog at a time, so a second flow waits, and the setup dialog comes after it.</summary>
    private bool asking;
    private int shownNotice;

    public MainWindow()
    {
        InitializeComponent();
        var languages = GlobalizationPreferences.Languages.ToList();
        strings = Strings.Load(Path.Combine(AppContext.BaseDirectory, "Strings"), languages);
        var queue = DispatcherQueue.GetForCurrentThread();
        model = new AppModel(languages, wanted => CoreLaunch.ForApp(Environment(), AppContext.BaseDirectory, windows: true, wanted, Build.Development), work => queue.TryEnqueue(() => work()));
        ask = new WinAsk(this, strings);
        flows = new Flows(model, ask, strings);
        uninstalling = new Uninstalling(model, ask, new WinUninstaller(this, strings), strings);
        noticeTimer = queue.CreateTimer();
        noticeTimer.Interval = TimeSpan.FromSeconds(8);
        noticeTimer.IsRepeating = false;
        noticeTimer.Tick += (_, _) => model.DismissNotice();
        Size();
        Words();
        model.PropertyChanged += OnModelChanged;
        Closed += OnClosed;
        Activated += OnFirstActivated;
        model.Launch();
        Render();
    }

    private static Dictionary<string, string?> Environment() =>
        System.Environment.GetEnvironmentVariables()
            .Cast<System.Collections.DictionaryEntry>()
            .ToDictionary(e => (string)e.Key, e => (string?)e.Value, StringComparer.OrdinalIgnoreCase);

    /// <summary>1000 × 700 at first, at least 640 × 480 effective pixels.</summary>
    private void Size()
    {
        var scale = NativeMethods.Scale(this);
        AppWindow.Resize(new Windows.Graphics.SizeInt32((int)(1000 * scale), (int)(700 * scale)));
        if (AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.PreferredMinimumWidth = (int)(640 * scale);
            presenter.PreferredMinimumHeight = (int)(480 * scale);
        }
    }

    /// <summary>Every fixed text, from po/ through the string tables.</summary>
    private void Words()
    {
        string T(string english) => strings.Text(english);
        FileMenu.Title = T("File");
        OpenItem.Text = T("Open…");
        RecentMenu.Text = T("Open Recent");
        ExportMenu.Text = T("Export");
        ExportMusicXmlItem.Text = ExportMusicXmlButton.Text = T("MusicXML…");
        ExportDrumTrackItem.Text = ExportDrumTrackButton.Text = T("Drum Track…");
        OpenWithItem.Text = OpenWithButton.Text = T("Open With…");
        ToolTipService.SetToolTip(ExportMusicXmlButton, T("To edit in MuseScore or another notation program"));
        ToolTipService.SetToolTip(ExportDrumTrackButton, T("As FLAC or WAV"));
        ToolTipService.SetToolTip(OpenWithButton, T("The MusicXML in another program"));
        CloseSongItem.Text = T("Close Song");
        BackUpItem.Text = T("Back Up…");
        RestoreItem.Text = T("Restore Backup…");
        RemoveItem.Text = T("Remove Downloaded Models…");
        UninstallItem.Text = T("Uninstall Stickler…");
        UninstallItem.Visibility = Shown(Uninstalling.Offered(AppContext.BaseDirectory));
        ExitItem.Text = T("Exit");
        HelpMenu.Title = T("Help");
        HelpItem.Text = T("Stickler Help");
        LicencesItem.Text = T("Licences");
        AboutItem.Text = T("About Stickler");
        OpenButton.Content = T("Open…");
        ToolTipService.SetToolTip(OpenButton, T("Open a Song"));
        ExportButton.Content = T("Export");
        DropText.Text = T("Drop a Song Here");
        OpenSongButton.Content = T("Open a Song…");
        RecentHeading.Text = T("Recent");
        CancelButton.Content = T("Cancel");
        FailedDetailsExpander.Header = StoppedDetailsExpander.Header = T("Technical Details");
        RetryButton.Content = T("Try Again");
        OpenAnotherButton.Content = T("Open Another Song…");
        StoppedTitle.Text = T("Stickler Stopped Unexpectedly");
        StoppedText.Text = T("The part of Stickler that listens to the songs has ended. A song it was writing has to be opened again; finished ones are kept.");
        StartAgainButton.Content = T("Start Again");
        NoticeTip.ActionButtonContent = T("Show in Folder");
    }

    private void OnModelChanged(object? sender, PropertyChangedEventArgs e) => Render();

    private void Render()
    {
        var state = model.State;
        var page = WindowView.Page(model);
        EmptyPage.Visibility = Shown(page == Page.Empty);
        StepsPage.Visibility = Shown(page == Page.Steps);
        FailedPage.Visibility = Shown(page == Page.Failed);
        ResultPage.Visibility = Shown(page == Page.Result);
        StoppedPage.Visibility = Shown(page == Page.Stopped);
        Header.Visibility = Shown(WindowView.ShowsHeader(model));
        Title = model.Title == "Stickler" ? "Stickler" : $"{model.Title} – Stickler";
        SongTitle.Text = model.Title;
        SongSubtitle.Text = model.Subtitle;
        SongSubtitle.Visibility = Shown(model.Subtitle.Length > 0);

        var running = model.Phase == Phase.Running;
        OpenItem.IsEnabled = OpenButton.IsEnabled = OpenSongButton.IsEnabled = running && state.Can.Open;
        ExportMenu.IsEnabled = ExportButton.IsEnabled = running && state.Can.Export;
        CloseSongItem.IsEnabled = running && state.Can.Close;
        BackUpItem.IsEnabled = RestoreItem.IsEnabled = RemoveItem.IsEnabled = UninstallItem.IsEnabled = running && state.Can.RemoveModels;
        CancelButton.IsEnabled = state.Can.Cancel;
        RetryButton.Visibility = Shown(state.Can.Retry);

        if (!ReferenceEquals(shownRecent, model.Recent) || shownCanOpen != state.Can.Open)
        {
            shownRecent = model.Recent;
            shownCanOpen = state.Can.Open;
            RecentRowsAndMenu(); // not twice a second while a download reports progress
        }
        switch (state.Screen)
        {
            case AnalysingScreen analysing:
                Steps(StepRows, analysing.Steps);
                break;
            case ExportingScreen exporting:
                Steps(StepRows, exporting.Steps);
                break;
            case FailedScreen failed:
                FailedTitle.Text = failed.Title;
                FailedDescription.Text = failed.Description;
                FailedDetails.Text = failed.Details;
                break;
            default:
                break;
        }
        if (model.End is { } end)
        {
            StoppedDetails.Text = end.TechnicalDetails;
            StoppedDetailsExpander.IsExpanded = end.NeverStarted;
        }
        Setup(WindowView.Dialog(model));
        Notice();
    }

    private static Visibility Shown(bool shown) => shown ? Visibility.Visible : Visibility.Collapsed;

    // the recent songs: rows on the empty window, and File › Open Recent

    private void RecentRowsAndMenu()
    {
        RecentRows.Children.Clear();
        RecentMenu.Items.Clear();
        foreach (var row in model.Recent)
        {
            var title = new TextBlock { Text = row.Title, TextTrimming = TextTrimming.CharacterEllipsis };
            var detail = new TextBlock { Text = row.Detail, Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"] };
            var words = new StackPanel { Opacity = row.Missing ? 0.5 : 1 };
            words.Children.Add(title);
            words.Children.Add(detail);
            var line = new Grid { ColumnSpacing = 8 };
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var open = new Button
            {
                Content = words,
                HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Left,
                IsEnabled = !row.Missing && model.State.Can.Open,
            };
            var path = row.Path;
            open.Click += (_, _) => model.Open(path);
            line.Children.Add(open);
            if (row.Missing)
            {
                var remove = new Button { Content = new FontIcon { Glyph = "", FontSize = 12 } };
                ToolTipService.SetToolTip(remove, strings.Text("Remove"));
                remove.Click += (_, _) => model.Forget(path);
                Grid.SetColumn(remove, 1);
                line.Children.Add(remove);
            }
            RecentRows.Children.Add(line);
            if (!row.Missing)
            {
                var item = new MenuFlyoutItem { Text = row.Title };
                item.Click += (_, _) => model.Open(path);
                RecentMenu.Items.Add(item);
            }
        }
        RecentPanel.Visibility = Shown(model.Recent.Count > 0);
        if (RecentMenu.Items.Count > 0)
        {
            RecentMenu.Items.Add(new MenuFlyoutSeparator());
        }
        var clear = new MenuFlyoutItem { Text = strings.Text("Clear Menu"), IsEnabled = model.Recent.Count > 0 };
        clear.Click += (_, _) => model.ClearRecent();
        RecentMenu.Items.Add(clear);
    }

    // a step list (W2, W5): done, running with a ring, waiting

    private void Steps(StackPanel into, IReadOnlyList<StepRow> steps)
    {
        into.Children.Clear();
        foreach (var step in steps)
        {
            var line = new Grid { ColumnSpacing = 12 };
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(24) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            FrameworkElement mark = step.State switch
            {
                StepProgress.Running => new ProgressRing { IsActive = true, Width = 20, Height = 20 },
                StepProgress.Done => new FontIcon { Glyph = "", Foreground = (Brush)Application.Current.Resources["AccentTextFillColorPrimaryBrush"] },
                _ => new FontIcon { Glyph = "", Foreground = (Brush)Application.Current.Resources["TextFillColorTertiaryBrush"] },
            };
            var words = new StackPanel();
            words.Children.Add(new TextBlock { Text = step.Label, TextWrapping = TextWrapping.Wrap });
            words.Children.Add(new TextBlock
            {
                Text = step.Detail,
                TextWrapping = TextWrapping.Wrap,
                Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"],
                Foreground = (Brush)Application.Current.Resources["TextFillColorSecondaryBrush"],
            });
            var status = new TextBlock
            {
                Text = WindowView.StepState(step.State, strings),
                Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"],
                VerticalAlignment = VerticalAlignment.Center,
            };
            Grid.SetColumn(words, 1);
            Grid.SetColumn(status, 2);
            line.Children.Add(mark);
            line.Children.Add(words);
            line.Children.Add(status);
            into.Children.Add(line);
        }
    }

    // W1–W3: one dialog over the dimmed empty window, its content following the state;
    // only the core's next state closes it

    private void Setup(SetupDialog wanted)
    {
        if (wanted == SetupDialog.None)
        {
            if (setup is not null)
            {
                closingSetup = true;
                setup.Hide();
                setup = null;
                closingSetup = false;
            }
            setupState = null;
            shownSetup = wanted;
            return;
        }
        if (Root.XamlRoot is null || asking)
        {
            return; // not shown yet, or a question is open: rendered again after it
        }
        if (setup is null)
        {
            setup = new ContentDialog { XamlRoot = Root.XamlRoot, DefaultButton = ContentDialogButton.Primary };
            setup.PrimaryButtonClick += OnSetupPrimary;
            setup.CloseButtonClick += OnSetupClose;
            setup.Closing += (_, args) => args.Cancel = !closingSetup;
            _ = setup.ShowAsync();
        }
        if (wanted == shownSetup && ReferenceEquals(model.State, setupState))
        {
            return; // nothing new: an opened "Technical Details" stays open
        }
        shownSetup = wanted;
        setupState = model.State;
        switch (model.State.Screen)
        {
            case ConsentScreen consent:
                SetupConsent(setup, consent);
                break;
            case SettingUpScreen settingUp:
                setup.Title = strings.Text("Downloading the Models");
                var panel = new StackPanel { Spacing = 16, MinWidth = 440 };
                panel.Children.Add(new TextBlock { Text = strings.Text("If this is interrupted, Stickler picks up where it stopped the next time you open it."), TextWrapping = TextWrapping.Wrap });
                var steps = new StackPanel { Spacing = 12 };
                Steps(steps, settingUp.Steps);
                panel.Children.Add(steps);
                setup.Content = panel;
                setup.PrimaryButtonText = "";
                setup.CloseButtonText = strings.Text("Cancel");
                setup.IsSecondaryButtonEnabled = false;
                break;
            case SetupFailedScreen failed:
                SetupFailed(setup, failed);
                break;
            default:
                break;
        }
    }

    private void SetupConsent(ContentDialog dialog, ConsentScreen consent)
    {
        dialog.Title = strings.Text("Welcome to Stickler");
        var panel = new StackPanel { Spacing = 12, MinWidth = 440 };
        panel.Children.Add(new TextBlock { Text = WindowView.ConsentIntro(consent, strings), TextWrapping = TextWrapping.Wrap });
        foreach (var item in consent.Models)
        {
            var line = new Grid { ColumnSpacing = 12 };
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            var words = new StackPanel();
            words.Children.Add(new TextBlock { Text = $"{item.Name} · {item.Does}", TextWrapping = TextWrapping.Wrap });
            words.Children.Add(new TextBlock
            {
                Text = item.Licence,
                TextWrapping = TextWrapping.Wrap,
                Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"],
                Foreground = (Brush)Application.Current.Resources["TextFillColorSecondaryBrush"],
            });
            var size = new TextBlock { Text = item.Size };
            Grid.SetColumn(size, 1);
            line.Children.Add(words);
            line.Children.Add(size);
            panel.Children.Add(line);
        }
        var total = new Grid();
        total.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        total.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        total.Children.Add(new TextBlock { Text = strings.Text("Together, on disk") });
        var sum = new TextBlock { Text = strings.Text("about {size}", ("size", consent.TotalSize)), Style = (Style)Application.Current.Resources["BodyStrongTextBlockStyle"] };
        Grid.SetColumn(sum, 1);
        total.Children.Add(sum);
        panel.Children.Add(total);
        if (WindowView.NamesNonCommercialUse(consent))
        {
            panel.Children.Add(new TextBlock
            {
                Text = strings.Text("By downloading, you accept that ADTOF’s model is used for non-commercial purposes only."),
                TextWrapping = TextWrapping.Wrap,
                Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"],
            });
        }
        dialog.Content = panel;
        dialog.PrimaryButtonText = strings.Text("Download {size}", ("size", consent.TotalSize));
        dialog.IsPrimaryButtonEnabled = model.State.Can.Agree;
        dialog.CloseButtonText = strings.Text("Not Now");
    }

    private void SetupFailed(ContentDialog dialog, SetupFailedScreen failed)
    {
        dialog.Title = strings.Text("A Download Server Is Not Answering");
        var panel = new StackPanel { Spacing = 12, MinWidth = 440 };
        panel.Children.Add(new TextBlock { Text = strings.Text("Stickler could not reach {server}. Everything that is done stays downloaded.", ("server", failed.Server)), TextWrapping = TextWrapping.Wrap });
        foreach (var step in failed.Steps)
        {
            var line = new Grid();
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            line.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            line.Children.Add(new TextBlock { Text = step.Label });
            var reached = new TextBlock { Text = strings.Text(step.State == StepProgress.Done ? "Ready" : "Not reached"), Style = (Style)Application.Current.Resources["CaptionTextBlockStyle"] };
            Grid.SetColumn(reached, 1);
            line.Children.Add(reached);
            panel.Children.Add(line);
        }
        panel.Children.Add(new Expander
        {
            Header = strings.Text("Technical Details"),
            HorizontalAlignment = HorizontalAlignment.Stretch,
            Content = new TextBlock { Text = failed.Details, FontFamily = new FontFamily("Consolas"), IsTextSelectionEnabled = true, TextWrapping = TextWrapping.Wrap },
        });
        dialog.Content = panel;
        dialog.PrimaryButtonText = strings.Text("Try Again");
        dialog.IsPrimaryButtonEnabled = model.State.Can.RetrySetup;
        dialog.CloseButtonText = strings.Text("Later");
    }

    private void OnSetupPrimary(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        args.Cancel = true; // the core's next state changes or closes the dialog
        if (shownSetup == SetupDialog.Consent)
        {
            model.Agree();
        }
        else if (shownSetup == SetupDialog.Failed)
        {
            model.RetrySetup();
        }
    }

    private void OnSetupClose(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        args.Cancel = true;
        if (shownSetup == SetupDialog.Download)
        {
            model.Cancel();
        }
        else
        {
            model.NotNow();
        }
    }

    // W7: the note after saving, under Export; other notes the same way

    private void Notice()
    {
        if (model.Notice is not { } notice)
        {
            NoticeTip.IsOpen = false;
            return;
        }
        if (model.NoticeSerial == shownNotice)
        {
            return;
        }
        shownNotice = model.NoticeSerial;
        NoticeTip.Title = notice.Text;
        NoticeTip.Tag = notice.Opens;
        NoticeTip.ActionButtonContent = notice.Opens is null ? null : strings.Text("Show in Folder");
        NoticeTip.Target = Header.Visibility == Visibility.Visible ? ExportButton : null;
        NoticeTip.IsOpen = true;
        noticeTimer.Stop();
        noticeTimer.Start();
    }

    private void OnShowInFolder(TeachingTip sender, object args)
    {
        if (sender.Tag is string file)
        {
            WinAsk.ShowInFolder(file);
        }
        noticeTimer.Stop();
        model.DismissNotice();
    }

    // what the reader does

    private async void OnOpen(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.OpenSongAsync());

    private async void OnExportMusicXml(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.ExportMusicXmlAsync());

    private async void OnExportDrumTrack(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.ExportDrumTrackAsync());

    private async void OnOpenWith(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.OpenWithAsync());

    private async void OnBackUp(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.BackUpAsync(DateOnly.FromDateTime(DateTime.Now)));

    private async void OnRestore(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.RestoreAsync());

    private async void OnRemoveModels(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.RemoveModelsAsync());

    private void OnCloseSong(object sender, RoutedEventArgs e) => model.Close();

    private void OnCancel(object sender, RoutedEventArgs e) => model.Cancel();

    private void OnRetry(object sender, RoutedEventArgs e) => model.Retry();

    private void OnStartAgain(object sender, RoutedEventArgs e) => model.StartAgain();

    private void OnExit(object sender, RoutedEventArgs e) => Close();

    private async void OnHelp(object sender, RoutedEventArgs e) => await Windows.System.Launcher.LaunchUriAsync(new Uri(Readme));

    private async void OnUninstall(object sender, RoutedEventArgs e) => await OneAtATime(() => uninstalling.RunAsync());

    /// <summary>The installed app's folder of licences (win-package); a build from the
    /// checkout shows the repository's licence page.</summary>
    private async void OnLicences(object sender, RoutedEventArgs e)
    {
        var shipped = Path.Combine(AppContext.BaseDirectory, CoreLaunch.CoreFolder, "licenses");
        _ = Directory.Exists(shipped)
            ? await Windows.System.Launcher.LaunchFolderPathAsync(shipped)
            : await Windows.System.Launcher.LaunchUriAsync(new Uri(LicencePage));
    }

    private async void OnAbout(object sender, RoutedEventArgs e) => await OneAtATime(AboutAsync);

    private async Task AboutAsync()
    {
        var panel = new StackPanel { Spacing = 8 };
        panel.Children.Add(new TextBlock { Text = "Stickler", Style = (Style)Application.Current.Resources["SubtitleTextBlockStyle"] });
        if (model.Version is { } version)
        {
            panel.Children.Add(new TextBlock { Text = version.ToString(CultureInfo.CurrentCulture) });
        }
        panel.Children.Add(new TextBlock { Text = strings.Text("Writes the drums of a song as sheet music, so you can play along."), TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "GPL-3.0-or-later" });
        panel.Children.Add(new HyperlinkButton { Content = "stickler.tshia.ng", NavigateUri = new Uri("https://stickler.tshia.ng") });
        var about = new ContentDialog
        {
            XamlRoot = Root.XamlRoot,
            Title = strings.Text("About Stickler"),
            Content = panel,
            CloseButtonText = strings.Text("Close"),
        };
        await about.ShowAsync();
    }

    private void OnDragOver(object sender, DragEventArgs e)
    {
        if (e.DataView.Contains(StandardDataFormats.StorageItems) && model.State.Can.Open)
        {
            e.AcceptedOperation = DataPackageOperation.Copy;
        }
    }

    private async void OnDrop(object sender, DragEventArgs e)
    {
        if (!e.DataView.Contains(StandardDataFormats.StorageItems))
        {
            return;
        }
        var items = await e.DataView.GetStorageItemsAsync();
        if (items.OfType<StorageFile>().FirstOrDefault() is { } file)
        {
            model.Open(file.Path);
        }
    }

    /// <summary>Runs one flow of the menus at a time and never while the setup dialog is up: a
    /// second click while a question or a reply is pending does nothing.</summary>
    private async Task OneAtATime(Func<Task> flow)
    {
        if (asking || setup is not null)
        {
            return;
        }
        asking = true;
        try
        {
            await flow();
        }
        finally
        {
            asking = false;
            Render(); // a setup dialog that waited for the question
        }
    }

    /// <summary>A setup state that came before the window was shown is drawn now.</summary>
    private void OnFirstActivated(object sender, WindowActivatedEventArgs args)
    {
        Activated -= OnFirstActivated;
        Render();
    }

    /// <summary>Quitting: the core ends politely, at most a few seconds.</summary>
    private void OnClosed(object sender, WindowEventArgs args)
    {
        model.PropertyChanged -= OnModelChanged;
        // QuitAsync: 3 s for the core to quit, then its tree ended and 2 s for that
        Task.Run(model.QuitAsync).Wait(TimeSpan.FromSeconds(8));
    }
}
