namespace Stickler;

/// <summary>What kind of build this is (SPEC.md, module <c>win-package</c>, scope 2).</summary>
internal static class Build
{
    /// <summary>Whether this build may run the core of a Stickler checkout
    /// (<c>STICKLER_CHECKOUT</c> or a checkout above the app) when no core is installed next to
    /// it: every build but the one the installer ships, which is built with
    /// <c>-p:SticklerInstalled=true</c> and only ever runs its own core.</summary>
#if INSTALLED
    public static bool Development => false;
#else
    public static bool Development => true;
#endif
}
