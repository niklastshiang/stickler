namespace Stickler.Core;

/// <summary>The keys of the Playback menu (accelerators), without any window type.</summary>
public enum PlaybackKey
{
    Space,
    Left,
    Right,
    Home,
}

/// <summary>The Playback menu's logic (SPEC.md, module <c>win-playback</c>, scopes 5 and 6; the
/// Mac's <c>ControlsMenu</c>): its entries, their keys, what is checked, when it works and what
/// a key does. The WinUI menu binds to it and decides nothing.</summary>
public static class PlaybackMenu
{
    /// <summary>One entry: its text in the reader's language, its accelerator and the key's name
    /// for display.</summary>
    public sealed record Entry(string Title, PlaybackKey Key, string KeyName);

    /// <summary>One of the radio entries Song, Hits and Both.</summary>
    public sealed record Choice(Hear Hear, string Title, bool IsChecked);

    /// <summary>The menu's own title.</summary>
    public static string MenuTitle(Strings strings) => strings.Text("Playback");

    /// <summary>The first entry says what Space does now.</summary>
    public static string PlayTitle(PlaybackModel playback, Strings strings) =>
        strings.Text(playback.Playing ? "Pause" : "Play");

    /// <summary>Play or Pause, Previous Bar, Next Bar and Go to the Start, in the menu's order.</summary>
    public static IReadOnlyList<Entry> Entries(PlaybackModel playback, Strings strings) =>
    [
        new(PlayTitle(playback, strings), PlaybackKey.Space, "Space"),
        new(strings.Text("Previous Bar"), PlaybackKey.Left, "Left"),
        new(strings.Text("Next Bar"), PlaybackKey.Right, "Right"),
        new(strings.Text("Go to the Start"), PlaybackKey.Home, "Home"),
    ];

    /// <summary>What to hear, in the menu's order, the current one checked.</summary>
    public static IReadOnlyList<Choice> Hearing(PlaybackModel playback, Strings strings) =>
    [
        new(Hear.Song, strings.Text("Song"), playback.Hear == Hear.Song),
        new(Hear.Hits, strings.Text("Hits"), playback.Hear == Hear.Hits),
        new(Hear.Both, strings.Text("Both"), playback.Hear == Hear.Both),
    ];

    /// <summary>Only a shown result plays.</summary>
    public static bool Enabled(AppModel model) => model.Phase == Phase.Running && model.Playback.CanPlay;

    /// <summary>Whether the playback takes <paramref name="key"/>: not while a text field, a
    /// slider or a menu has the focus (<paramref name="typing"/>, which the window decides).</summary>
    public static bool Handles(PlaybackKey key, bool typing) => !typing && Enum.IsDefined(key);

    /// <summary>Does what the entry of <paramref name="key"/> does, when the menu is enabled and
    /// the key is the playback's; says whether it took the key (the window then marks the key
    /// event handled).</summary>
    public static bool Press(AppModel model, PlaybackKey key, bool typing = false)
    {
        if (!Handles(key, typing) || !Enabled(model))
        {
            return false;
        }
        var playback = model.Playback;
        switch (key)
        {
            case PlaybackKey.Space:
                playback.Toggle();
                break;
            case PlaybackKey.Left:
                playback.PreviousBar();
                break;
            case PlaybackKey.Right:
                playback.NextBar();
                break;
            default:
                playback.GoToStart();
                break;
        }
        return true;
    }
}
