#ifndef DISTRHO_PLUGIN_INFO_H_INCLUDED
#define DISTRHO_PLUGIN_INFO_H_INCLUDED

#define DISTRHO_PLUGIN_BRAND       "New Horizon"
#define DISTRHO_PLUGIN_NAME        "Can-Abyss Delay"
#define DISTRHO_PLUGIN_URI         "https://github.com/Kiwooky/NHE-Can-Abyss"

#define DISTRHO_PLUGIN_HAS_UI       0
#define DISTRHO_PLUGIN_IS_RT_SAFE   1
#define DISTRHO_PLUGIN_NUM_INPUTS   1
#define DISTRHO_PLUGIN_NUM_OUTPUTS  2

enum Parameters {
    kTime = 0,
    kRepeat,
    kReverb,
    kTone,
    kWobble,
    kDiscSize,
    kWear,
    kMix,
    kSag,
    kHold,
    kTails,
    kBypass,
    kParameterCount
};

#endif
