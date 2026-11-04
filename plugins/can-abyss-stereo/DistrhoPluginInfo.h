#ifndef DISTRHO_PLUGIN_INFO_H_INCLUDED
#define DISTRHO_PLUGIN_INFO_H_INCLUDED

#define DISTRHO_PLUGIN_BRAND       "New Horizon"
#define DISTRHO_PLUGIN_NAME        "Can-Abyss Delay Stereo"
#define DISTRHO_PLUGIN_URI         "https://github.com/Kiwooky/NHE-Can-Abyss-Stereo"

#define DISTRHO_PLUGIN_HAS_UI       0
#define DISTRHO_PLUGIN_IS_RT_SAFE   1
#define DISTRHO_PLUGIN_NUM_INPUTS   2
#define DISTRHO_PLUGIN_NUM_OUTPUTS  2

// Port order is MOD's settings-panel order: grouped, and within a group by index.
enum Parameters {
    kTime = 0,      // Delay
    kRepeat,
    kHold,
    kSpread,        // settings only (not on the face)
    kReverb,        // Colour
    kTone,
    kDiscSize,
    kWobble,        // Vibe
    kWear,
    kSag,
    kCeiling,       // Mix
    kSafety,
    kTails,
    kMix,
    kBypass,
    kParameterCount
};

enum PortGroups {
    kGroupDelay = 0,
    kGroupColour,
    kGroupVibe,
    kGroupMix,
    kGroupCount
};

#endif
