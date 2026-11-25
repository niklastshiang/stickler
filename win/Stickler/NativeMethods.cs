using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;
using WinRT.Interop;

namespace Stickler;

/// <summary>The one Win32 call the window needs: its display's scale, to size it in effective pixels.</summary>
internal static partial class NativeMethods
{
    public static double Scale(Window window)
    {
        var dpi = GetDpiForWindow(WindowNative.GetWindowHandle(window));
        return dpi > 0 ? dpi / 96.0 : 1.0;
    }

    [LibraryImport("user32.dll")]
    private static partial uint GetDpiForWindow(IntPtr hwnd);
}
