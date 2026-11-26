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
        PositionSlider.AddHandler(PointerPressedEvent, new PointerEventHandler((_, _) => held = true), true);
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

    private void OnPlaybackChanged(object? sender, PropertyChangedEventArgs e) => Show();

    private void Show()
    {
        if (playback is not { } model)
        {
            return;
        }
        showing = true;
        try
        {
            IsEnabled = model.CanPlay;
            PlayIcon.Glyph = model.Playing ? "" : "";
            Call(PlayButton, strings.Text(model.Playing ? "Pause" : "Play"));
            PositionSlider.Maximum = Math.Max(model.Length, 0.01);
            if (!held)
            {
                PositionSlider.Value = model.Position;
                TimeText.Text = model.Time;
            }
            LengthText.Text = model.LengthText;
            if (BarText.Text != model.Label)
            {
                BarText.Text = model.Label;
                // Narrator reads the position as the time and the bar, told once per bar
                AutomationProperties.SetHelpText(PositionSlider, $"{model.Time}, {model.Label}");
            }
            SongVolumeSlider.Value = Math.Round(model.SongVolume * 100);
            HitsVolumeSlider.Value = Math.Round(model.HitsVolume * 100);
            HearSongButton.IsChecked = model.Hear == Hear.Song;
            HearHitsButton.IsChecked = model.Hear == Hear.Hits;
            HearBothButton.IsChecked = model.Hear == Hear.Both;
        }
        finally
        {
            showing = false;
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

    private void OnHearSong(object sender, RoutedEventArgs e) => Choose(Hear.Song);

    private void OnHearHits(object sender, RoutedEventArgs e) => Choose(Hear.Hits);

    private void OnHearBoth(object sender, RoutedEventArgs e) => Choose(Hear.Both);

    // a click on the chosen button would switch it off: the model's value is shown again
    private void Choose(Hear next)
    {
        playback?.SetHear(next);
        Show();
    }
}
