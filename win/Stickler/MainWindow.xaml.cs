using System.ComponentModel;
using System.Globalization;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Stickler.Audio;
using Stickler.Core;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.System.UserProfile;
using Page = Stickler.Core.Page;

namespace Stickler;

/// <summary>The window of design screens W1–W5, W7, W8, W10 and W11 (SPEC.md, modules
/// <c>win-shell</c>, <c>win-playback</c> and <c>win-corrections</c>).
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
    private readonly Player player;
    private readonly string windowSettings; // where "the corrections pane is open" is kept
    private bool correctionsShown;
    private bool renderingCorrections; // the button is being set from the state: not the reader's doing
    private readonly DispatcherQueueTimer noticeTimer;
    private ContentDialog? setup;
    private SetupDialog shownSetup = SetupDialog.None;
    private bool closingSetup;
    private AppState? setupState;
    private StackPanel? downloadSteps; // the download dialog's rows, kept while it is open
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
        player = Sound.Player(error => strings.Text("The song cannot be played: {reason}", ("reason", Reason(error))));
        model = new AppModel(languages, wanted => CoreLaunch.ForApp(Environment(), AppContext.BaseDirectory, windows: true, wanted, Build.Development), work => queue.TryEnqueue(() => work()), player);
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
        model.Sheet.PropertyChanged += OnSheetChanged;
        model.Playback.PropertyChanged += OnPlaybackChanged;
        SheetPane.Attach(model.Sheet, model.Playback, strings, reason => model.Tell(new Notice(reason, null)), key => PlaybackMenu.Press(model, key));
        PlayPane.Attach(model.Playback, strings);
        CorrectionsPaneView.Attach(model, strings);
        windowSettings = WindowSettings.PathFor(Environment());
        correctionsShown = WindowSettings.Load(windowSettings).CorrectionsShown;
        Keys();
        Root.KeyDown += OnKey;
        Closed += OnClosed;
        Activated += OnFirstActivated;
        model.Launch();
        Render();
    }

    /// <summary>Why the player failed, in words: a PC without a sound output answers "Element
    /// not found" (0x80070490, seen on GitHub's runner), which says nothing to a reader.</summary>
    private string Reason(Exception error) =>
        error is System.Runtime.InteropServices.COMException { HResult: unchecked((int)0x80070490) }
            ? strings.Text("No sound output was found.")
            : error.Message;

    private static Dictionary<string, string?> Environment() =>
        System.Environment.GetEnvironmentVariables()
            .Cast<System.Collections.DictionaryEntry>()
            .ToDictionary(e => (string)e.Key, e => (string?)e.Value, StringComparer.OrdinalIgnoreCase);

    /// <summary>1000 × 700 at first, at least 640 × 480 effective pixels.</summary>
    private void Size()
    {
        var scale = NativeMethods.Scale(this);
        AppWindow.Resize(new Windows.Graphics.SizeInt32((int)(1000 * scale), (int)(700 * scale)));
        // Windows places a new window before it has this size: on a small screen the playback
        // bar then lay below the screen's edge, so the window is moved back into the work area.
        var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Nearest).WorkArea;
        var x = Math.Max(area.X, Math.Min(AppWindow.Position.X, area.X + area.Width - AppWindow.Size.Width));
        var y = Math.Max(area.Y, Math.Min(AppWindow.Position.Y, area.Y + area.Height - AppWindow.Size.Height));
        AppWindow.Move(new Windows.Graphics.PointInt32(x, y));
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
        ExportPdfItem.Text = ExportPdfButton.Text = T("Sheet Music (PDF)…");
        ToolTipService.SetToolTip(ExportPdfButton, T("To print or to read on a tablet"));
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
        ViewMenu.Title = T("View");
        ZoomInItem.Text = T("Zoom In");
        ZoomOutItem.Text = T("Zoom Out");
        ActualSizeItem.Text = T("Actual Size");
        CorrectionsItem.Text = T("Corrections");
        AutomationProperties.SetName(CorrectionsButton, T("Corrections"));
        ToolTipService.SetToolTip(CorrectionsButton, T("Corrections"));
        PlaybackMenuBar.Title = PlaybackMenu.MenuTitle(strings);
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

    private void OnSheetChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(SheetModel.CanZoom))
        {
            Render();
        }
    }

    private void OnPlaybackChanged(object? sender, PropertyChangedEventArgs e)
    {
        // not the position, twenty times a second
        if (e.PropertyName is nameof(PlaybackModel.Playing) or nameof(PlaybackModel.CanPlay) or nameof(PlaybackModel.Hear))
        {
            RenderPlayback();
        }
    }

    /// <summary>The corrections pane, its button and its View entry (W11) as
    /// <see cref="CorrectionsPane"/> says them; the ring turns while the notes are written.</summary>
    private void RenderCorrections()
    {
        var enabled = CorrectionsPane.Enabled(model);
        var presented = CorrectionsPane.Presented(correctionsShown, model);
        CorrectionsButton.IsEnabled = CorrectionsItem.IsEnabled = enabled;
        renderingCorrections = true;
        CorrectionsButton.IsChecked = CorrectionsItem.IsChecked = presented;
        renderingCorrections = false;
        CorrectionsPaneView.Visibility = Shown(presented);
        if (CorrectionsPane.Controls(model) is { } controls)
        {
            CorrectionsPaneView.Show(controls);
        }
        var correcting = CorrectionsPane.Correcting(model);
        CorrectingRing.IsActive = correcting;
        CorrectingRing.Visibility = Shown(correcting);
    }

    /// <summary>View › Corrections (Ctrl+Shift+C): open or closed, kept for the next start.</summary>
    private void OnCorrections(object sender, RoutedEventArgs e) =>
        ShowCorrections(!CorrectionsPane.Presented(correctionsShown, model));

    /// <summary>The button beside Export, pressed or toggled by Narrator.</summary>
    private void OnCorrectionsToggled(object sender, RoutedEventArgs e)
    {
        if (!renderingCorrections)
        {
            ShowCorrections(CorrectionsButton.IsChecked == true);
        }
    }

    private void ShowCorrections(bool wanted)
    {
        correctionsShown = wanted;
        new WindowSettings(correctionsShown).Save(windowSettings);
        RenderCorrections();
    }

    /// <summary>The Playback menu (W10) as <see cref="PlaybackMenu"/> says it: the first entry
    /// names what Space does now, the keys are shown as text (they are the window's, see
    /// <see cref="OnKey"/>).</summary>
    private void RenderPlayback()
    {
        MenuFlyoutItem[] items = [PlayItem, PreviousBarItem, NextBarItem, GoToStartItem];
        var entries = PlaybackMenu.Entries(model.Playback, strings);
        var enabled = PlaybackMenu.Enabled(model);
        for (var i = 0; i < items.Length; i++)
        {
            items[i].Text = entries[i].Title;
            items[i].KeyboardAcceleratorTextOverride = strings.Text(entries[i].KeyName); // the key's name in the reader's language
            items[i].IsEnabled = enabled;
        }
        RadioMenuFlyoutItem[] hearing = [HearSongItem, HearHitsItem, HearBothItem];
        var choices = PlaybackMenu.Hearing(model.Playback, strings);
        for (var i = 0; i < hearing.Length; i++)
        {
            hearing[i].Text = choices[i].Title;
            hearing[i].IsChecked = choices[i].IsChecked;
            hearing[i].IsEnabled = enabled;
        }
    }

    /// <summary>Space, Left, Right and Home play and move (W10) wherever the focus is in the
    /// window, unless the focused control uses the key itself: a button's Space never arrives
    /// here, and a slider, a switch, the menu bar and a text field are left alone.</summary>
    private void OnKey(object sender, KeyRoutedEventArgs e)
    {
        PlaybackKey? key = e.Key switch
        {
            Windows.System.VirtualKey.Space => PlaybackKey.Space,
            Windows.System.VirtualKey.Left => PlaybackKey.Left,
            Windows.System.VirtualKey.Right => PlaybackKey.Right,
            Windows.System.VirtualKey.Home => PlaybackKey.Home,
            _ => null,
        };
        if (key is not { } pressed || Modified())
        {
            return;
        }
        if (pressed == PlaybackKey.Space && e.KeyStatus.WasKeyDown)
        {
            e.Handled = true; // a held Space is one press, not a play and a pause per repeat
            return;
        }
        // a control that uses these keys itself keeps them, also where it leaves the event unhandled
        var typing = KeepsItsKeys(FocusManager.GetFocusedElement(Root.XamlRoot) as DependencyObject);
        e.Handled = PlaybackMenu.Press(model, pressed, typing);
    }

    /// <summary>Whether the focus is in a control that uses Space or the arrows itself, or in a
    /// part of one (the menu bar's focus is on a button inside its item).</summary>
    private static bool KeepsItsKeys(DependencyObject? focused)
    {
        for (var at = focused; at is not null; at = VisualTreeHelper.GetParent(at))
        {
            if (at is TextBox or PasswordBox or RichEditBox or AutoSuggestBox or Slider or ToggleSwitch or MenuBarItem or MenuBar)
            {
                return true;
            }
        }
        return false;
    }

    private static bool Modified()
    {
        static bool Down(Windows.System.VirtualKey key) =>
            Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(key).HasFlag(Windows.UI.Core.CoreVirtualKeyStates.Down);
        return Down(Windows.System.VirtualKey.Control) || Down(Windows.System.VirtualKey.Menu) || Down(Windows.System.VirtualKey.Shift);
    }

    /// <summary>View's keys (W8): Ctrl+Plus, Ctrl+Minus and Ctrl+0, also on the keypad; the
    /// menu shows Windows' own names for them.</summary>
    private void Keys()
    {
        static KeyboardAccelerator Key(int key) => new()
        {
            Key = (Windows.System.VirtualKey)key,
            Modifiers = Windows.System.VirtualKeyModifiers.Control,
            IsEnabled = true,
        };
        ZoomInItem.KeyboardAccelerators.Add(Key(187)); // the + key (VK_OEM_PLUS)
        ZoomInItem.KeyboardAccelerators.Add(Key((int)Windows.System.VirtualKey.Add));
        ZoomInItem.KeyboardAcceleratorTextOverride = strings.Text("Ctrl+Plus");
        ZoomOutItem.KeyboardAccelerators.Add(Key(189)); // the - key (VK_OEM_MINUS)
        ZoomOutItem.KeyboardAccelerators.Add(Key((int)Windows.System.VirtualKey.Subtract));
        ZoomOutItem.KeyboardAcceleratorTextOverride = strings.Text("Ctrl+Minus");
        ActualSizeItem.KeyboardAccelerators.Add(Key((int)Windows.System.VirtualKey.Number0));
        ActualSizeItem.KeyboardAccelerators.Add(Key((int)Windows.System.VirtualKey.NumberPad0));
        ActualSizeItem.KeyboardAcceleratorTextOverride = strings.Text("Ctrl+0");
    }

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
        SheetPane.SongTitle = model.Title;
        SongSubtitle.Text = model.Subtitle;
        SongSubtitle.Visibility = Shown(model.Subtitle.Length > 0);

        var running = model.Phase == Phase.Running;
        ZoomInItem.IsEnabled = ZoomOutItem.IsEnabled = ActualSizeItem.IsEnabled = running && model.Sheet.CanZoom;
        OpenItem.IsEnabled = OpenButton.IsEnabled = OpenSongButton.IsEnabled = running && state.Can.Open;
        ExportMenu.IsEnabled = ExportButton.IsEnabled = WindowView.CanExport(model); // not while a correction is written
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
        RenderPlayback();
        RenderCorrections();
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
        if (Updated(into, steps))
        {
            return; // the rows stay: a running step's ring keeps turning (owner, 2026-11-26)
        }
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
            line.Tag = step.State;
            into.Children.Add(line);
        }
    }

    /// <summary>The same steps in the same states as shown: only their words change (a
    /// download's "650 MB of 1.3 GB" twice a second), so the rows and a running ring stay
    /// instead of starting again with every state. False when a row must be drawn anew.</summary>
    private bool Updated(StackPanel into, IReadOnlyList<StepRow> steps)
    {
        if (into.Children.Count != steps.Count)
        {
            return false;
        }
        for (var i = 0; i < steps.Count; i++)
        {
            if (into.Children[i] is not Grid { Tag: StepProgress shown } || shown != steps[i].State)
            {
                return false;
            }
        }
        for (var i = 0; i < steps.Count; i++)
        {
            var line = (Grid)into.Children[i];
            var words = (StackPanel)line.Children[1];
            ((TextBlock)words.Children[0]).Text = steps[i].Label;
            ((TextBlock)words.Children[1]).Text = steps[i].Detail;
            ((TextBlock)line.Children[2]).Text = WindowView.StepState(steps[i].State, strings);
        }
        return true;
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
            downloadSteps = null;
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
        var downloading = shownSetup == SetupDialog.Download && downloadSteps is not null;
        shownSetup = wanted;
        setupState = model.State;
        switch (model.State.Screen)
        {
            case ConsentScreen consent:
                SetupConsent(setup, consent);
                break;
            case SettingUpScreen settingUp when downloading:
                Steps(downloadSteps!, settingUp.Steps); // the same dialog: its rows and ring stay
                break;
            case SettingUpScreen settingUp:
                setup.Title = strings.Text("Downloading the Models");
                var panel = new StackPanel { Spacing = 16, MinWidth = 440 };
                panel.Children.Add(new TextBlock { Text = strings.Text("If this is interrupted, Stickler picks up where it stopped the next time you open it."), TextWrapping = TextWrapping.Wrap });
                var steps = new StackPanel { Spacing = 12 };
                Steps(steps, settingUp.Steps);
                panel.Children.Add(steps);
                downloadSteps = steps;
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

    private async void OnExportPdf(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.ExportPdfAsync(PrintAsync));

    /// <summary>The A4 pages printed by the sheet's second WebView2, the Leipzig font with them.</summary>
    private async Task<bool> PrintAsync(A4Pages pages, string path)
    {
        var font = await File.ReadAllBytesAsync(Path.Combine(AppContext.BaseDirectory, "Leipzig.ttf"));
        return await SheetPane.PrintAsync(SheetHtml.A4Document(pages, font), path);
    }

    private void OnZoomIn(object sender, RoutedEventArgs e) => model.Sheet.ZoomIn();

    private void OnZoomOut(object sender, RoutedEventArgs e) => model.Sheet.ZoomOut();

    private void OnActualSize(object sender, RoutedEventArgs e) => model.Sheet.ActualSize();

    private async void OnExportMusicXml(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.ExportMusicXmlAsync());

    private async void OnExportDrumTrack(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.ExportDrumTrackAsync());

    private async void OnOpenWith(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.OpenWithAsync());

    private async void OnBackUp(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.BackUpAsync(DateOnly.FromDateTime(DateTime.Now)));

    private async void OnRestore(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.RestoreAsync());

    private async void OnRemoveModels(object sender, RoutedEventArgs e) => await OneAtATime(() => flows.RemoveModelsAsync());

    private void OnPlay(object sender, RoutedEventArgs e) => PlaybackMenu.Press(model, PlaybackKey.Space);

    private void OnPreviousBar(object sender, RoutedEventArgs e) => PlaybackMenu.Press(model, PlaybackKey.Left);

    private void OnNextBar(object sender, RoutedEventArgs e) => PlaybackMenu.Press(model, PlaybackKey.Right);

    private void OnGoToStart(object sender, RoutedEventArgs e) => PlaybackMenu.Press(model, PlaybackKey.Home);

    private void OnHearSong(object sender, RoutedEventArgs e) => model.Playback.SetHear(Hear.Song);

    private void OnHearHits(object sender, RoutedEventArgs e) => model.Playback.SetHear(Hear.Hits);

    private void OnHearBoth(object sender, RoutedEventArgs e) => model.Playback.SetHear(Hear.Both);

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
        catch (Exception error) when (error is System.Runtime.InteropServices.COMException or InvalidOperationException or UnauthorizedAccessException or IOException)
        {
            // a dialog Windows could not show, a file it could not hand over: said, not fatal
            model.Tell(new Notice(error.Message, null));
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
        model.Sheet.PropertyChanged -= OnSheetChanged;
        model.Playback.PropertyChanged -= OnPlaybackChanged;
        PlayPane.Detach();
        player.Dispose(); // the sound stops at once, before the core is waited for
        // QuitAsync: 3 s for the core to quit, then its tree ended and 2 s for that
        Task.Run(model.QuitAsync).Wait(TimeSpan.FromSeconds(8));
    }
}
