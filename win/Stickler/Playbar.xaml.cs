using System.ComponentModel;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Stickler.Core;

namespace Stickler;

/// <summary>The playback bar of design screen W10 (SPEC.md, module <c>win-playback</c>, scope 4).
/// It shows what <see cref="PlaybackModel"/> says and forwards every control as one call; it
/// decides nothing but what a narrow window leaves out. A pure view: checked by screenshots and
/// by hand, not counted for coverage.</summary>
public sealed partial class Playbar : UserControl
{
    private const double RoomForBar = 760; // narrower: "Bar 2 of 110" goes (the marker shows it)
    private const double RoomForTimes = 660; // narrower still: the time and the length go

    private PlaybackModel? playback;
    private Strings strings = Strings.English;
    private bool showing; // the model's values are being put into the controls: not the reader's doing
    private bool held; // the reader drags the position: the model's ticks leave the slider alone
    private double? dragged; // where the drag is; the song goes there when it ends

    public Playbar()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Fit();
        // a slider handles the pointer itself, so these are asked for as handled events too
        PositionSlider.AddHandler(PointerPressedEvent, new PointerEventHandler(Pressed), true);
        PositionSlider.AddHandler(PointerReleasedEvent, new PointerEventHandler((_, _) => Dropped()), true);
        PositionSlider.AddHandler(PointerCaptureLostEvent, new PointerEventHandler((_, _) => Dropped()), true);
    }

    public void Attach(PlaybackModel model, Strings words)
    {
        playback = model;
        strings = words;
        string T(string english) => strings.Text(english);
        Call(PreviousButton, T("Previous Bar"));
        Call(NextButton, T("Next Bar"));
        Call(VolumeButton, T("Volume"));
        AutomationProperties.SetName(PositionSlider, T("Position"));
        AutomationProperties.SetName(HearGroup, T("What to Hear"));
        SongVolumeText.Text = T("Song");
        HitsVolumeText.Text = T("Detected hits");
        AutomationProperties.SetName(SongVolumeSlider, T("Song"));
        AutomationProperties.SetName(HitsVolumeSlider, T("Detected hits"));
        HearSongButton.Content = T("Song");
        HearHitsButton.Content = T("Hits");
        HearBothButton.Content = T("Both");
        model.PropertyChanged += OnPlaybackChanged;
        Show();
    }

    public void Detach()
    {
        if (playback is not null)
        {
            playback.PropertyChanged -= OnPlaybackChanged;
        }
    }

    private static void Call(Button button, string name)
    {
        AutomationProperties.SetName(button, name);
        ToolTipService.SetToolTip(button, name);
    }

    // Only what changed is set: the position comes twenty times a second, and a tooltip set
    // anew each time would never stay open.
    private void OnPlaybackChanged(object? sender, PropertyChangedEventArgs e) => Show(e.PropertyName);

    /// <summary>The model's values in the controls; all of them without a
    /// <paramref name="changed"/> property.</summary>
    private void Show(string? changed = null)
    {
        if (playback is not { } model)
        {
            return;
        }
        bool Is(string name) => changed is null || changed == name;
        showing = true;
        try
        {
            if (Is(nameof(PlaybackModel.CanPlay)))
            {
                IsEnabled = model.CanPlay;
            }
            if (Is(nameof(PlaybackModel.Playing)))
            {
                PlayIcon.Glyph = model.Playing ? "\uE769" : "\uE768";
                Call(PlayButton, strings.Text(model.Playing ? "Pause" : "Play"));
            }
            if (Is(nameof(PlaybackModel.Length)))
            {
                PositionSlider.Maximum = Math.Max(model.Length, 0.01);
                LengthText.Text = model.LengthText;
            }
            if ((Is(nameof(PlaybackModel.Position)) || Is(nameof(PlaybackModel.Length))) && !held)
            {
                PositionSlider.Value = model.Position;
                TimeText.Text = model.Time;
            }
            if (Is(nameof(PlaybackModel.Label)) && BarText.Text != model.Label)
            {
                BarText.Text = model.Label;
                // Narrator reads the position as the time and the bar, told once per bar
                AutomationProperties.SetHelpText(PositionSlider, $"{model.Time}, {model.Label}");
            }
            if (Is(nameof(PlaybackModel.SongVolume)))
            {
                SongVolumeSlider.Value = Math.Round(model.SongVolume * 100);
            }
            if (Is(nameof(PlaybackModel.HitsVolume)))
            {
                HitsVolumeSlider.Value = Math.Round(model.HitsVolume * 100);
            }
            if (Is(nameof(PlaybackModel.Hear)))
            {
                HearSongButton.IsChecked = model.Hear == Hear.Song;
                HearHitsButton.IsChecked = model.Hear == Hear.Hits;
                HearBothButton.IsChecked = model.Hear == Hear.Both;
            }
        }
        finally
        {
            showing = false;
        }
    }

    // Only the primary button drags: a right click takes no capture, so nothing would end it.
    private void Pressed(object sender, PointerRoutedEventArgs e)
    {
        if (e.Pointer.PointerDeviceType != Microsoft.UI.Input.PointerDeviceType.Mouse
            || e.GetCurrentPoint(PositionSlider).Properties.IsLeftButtonPressed)
        {
            held = true;
        }
    }

    /// <summary>A narrow window keeps one row and leaves out, in turn, the bar's text, then the
    /// time and the length (the Mac's rule).</summary>
    private void Fit()
    {
        BarText.Visibility = ActualWidth >= RoomForBar ? Visibility.Visible : Visibility.Collapsed;
        TimeText.Visibility = LengthText.Visibility = ActualWidth >= RoomForTimes ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnPrevious(object sender, RoutedEventArgs e) => playback?.PreviousBar();

    private void OnPlay(object sender, RoutedEventArgs e) => playback?.Toggle();

    private void OnNext(object sender, RoutedEventArgs e) => playback?.NextBar();

    /// <summary>The keys move the song at once; a drag moves it when it ends, so the sound
    /// device is not opened anew for every pixel on the way.</summary>
    private void OnPositionChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        if (showing || playback is not { } model)
        {
            return;
        }
        if (held)
        {
            dragged = e.NewValue;
            TimeText.Text = Timeline.Clock(e.NewValue);
        }
        else
        {
            model.Seek(e.NewValue);
        }
    }

    private void Dropped()
    {
        held = false;
        if (dragged is { } target)
        {
            dragged = null;
            playback?.Seek(target);
        }
    }

    private void OnSongVolumeChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        if (!showing)
        {
            playback?.SetSongVolume(e.NewValue / 100);
        }
    }

    private void OnHitsVolumeChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        if (!showing)
        {
            playback?.SetHitsVolume(e.NewValue / 100);
        }
    }

    // Checked, not Click: Narrator toggles a button without clicking it
    private void OnHearSong(object sender, RoutedEventArgs e) => Choose(Hear.Song);

    private void OnHearHits(object sender, RoutedEventArgs e) => Choose(Hear.Hits);

    private void OnHearBoth(object sender, RoutedEventArgs e) => Choose(Hear.Both);

    private void Choose(Hear next)
    {
        if (!showing)
        {
            playback?.SetHear(next);
            Show();
        }
    }

    // the chosen button was switched off: one of the three is always on, so it is shown again
    private void OnHearKept(object sender, RoutedEventArgs e)
    {
        if (!showing)
        {
            Show();
        }
    }
}
