#include "DistrhoPlugin.hpp"

#include <cmath>
#include <cstring>
#include <cstdint>

START_NAMESPACE_DISTRHO

// ---------------------------------------------------------------------------
// Can-Abyss Delay - a model of the 1960s electrostatic "oil can" delay
// (Ray Lubow / Tel-Ray: Ad-N-Echo, Morley).
//
// A motor and rubber belt spin a disc in a can of dielectric oil. A write
// wiper deposits the signal as charge; a read wiper picks it up later.
// There is no erase head: leftover charge comes round again every
// revolution, fainter and blurrier each pass. That residual is the oil
// can's half-reverb smear, and it is modelled literally:
//
//   D(t) = write(in + Repeat * y) + Reverb * loss(D(t - P))     disc
//   y(t) = read(D(t - 0.9 P))                                   read wiper
//
// P is one revolution. Time sets the motor speed, so the read point follows
// the motor (with inertia), sweeps bend pitch like tape, and the mechanical
// warble (once per revolution, belt drift, flutter) scales with disc speed.
// Bandwidth follows surface speed: long times and small discs are darker.
//
// Modern mods (New Horizon): Disc Size, Wear (a worn disc: speed and level
// irregularities locked to disc position, so they repeat every revolution),
// Sag (tube supply droop + motor slip) and Hold (a frozen disc that still
// varispeeds). Clean: no hiss or hum, by design.
//
// STEREO: two discs on one motor shaft. Left and right each have their own
// disc, charge, residual wash, tube stages and repeat loop; the motor (Time,
// inertia, warble, sag slip) and the tube supply (sag droop) are shared, so the
// sides stay in step and wobble together. Spread turns the right disc's read
// wiper back from 324 to 216 degrees: the right echo comes earlier (2/3 of
// Time at 100%) and reads a different patch of a worn disc. The Safety limiter
// is linked. Same signal on both inputs with Spread at 0 = the mono plugin's
// Mix Out on both sides, sample for sample.
// ---------------------------------------------------------------------------

static const float    kPi       = 3.14159265358979f;
static const uint32_t kBufSize  = 1u << 19;      // 5.4 s at 96 kHz: loop + one older revolution
static const uint32_t kBufMask  = kBufSize - 1;
static const uint32_t kTabSize  = 1024;          // disc wear profile, one revolution
static const float    kWiper    = 0.9f;          // read wiper at 324 degrees
static const uint32_t kCtl      = 16;            // control-rate block
// warble depths as fractions of the delay (stock Wobble, stock disc)
static const float    kClipBias = 0.1f * (27.0f + 0.01f) / (27.0f + 0.09f);   // softClip(0.1)
static const float    kWobRev   = 0.00045f;      // disc runout, once per revolution
static const float    kWobDrift = 0.0012f;       // belt drift, 0.37 + 0.61 Hz
static const float    kWobFlut  = 0.00004f;      // motor flutter, 3-10 Hz
static const float    kWearPitch = 0.0012f;      // worn disc at Wear 10: speed irregularity
static const float    kWearDip   = 0.5f;         // ... and up to -6 dB level dips
static const float    kApG      = 0.6f;
static const float    kResKeep  = 0.20f;         // share of Reverb that survives the back-off
static const uint32_t kApSize   = 1024;          // residual diffusers (<= 10 ms at 96 kHz)
static const uint32_t kLaSize   = 256;           // limiter lookahead (<= 2.6 ms at 96 kHz)



static inline float clampf(float x, float lo, float hi)
{
    return x < lo ? lo : (x > hi ? hi : x);
}

static inline float onePoleCoef(float hz, float sr)
{
    return 1.0f - std::exp(-2.0f * kPi * hz / sr);
}

// Rational tanh approximation; |x| < 3 accurate, saturates beyond.
static inline float softClip(float x)
{
    if (x >  3.0f) return  1.0f;
    if (x < -3.0f) return -1.0f;
    const float x2 = x * x;
    return x * (27.0f + x2) / (27.0f + 9.0f * x2);
}

// 2x oversampled saturators: linear-interpolated midpoint, nonlinearity at
// both points, 2-tap average back down. Cheap, and it stops the loop
// re-sharpening (and aliasing) its own edges on every pass.
static inline float writeCurve(float u)
{
    return (softClip(1.5f * u + 0.1f) - kClipBias) * (1.0f / 1.5f);   // tube: drive 1.5, bias 0.1
}
static inline float discCurve(float d) { return 1.6f * softClip(d * (1.0f / 1.6f)); }

// soft knee: linear below k, smoothly approaching k + r (never above)
static inline float softKnee(float x, float k, float r)
{
    const float a = std::fabs(x);
    if (a <= k) return x;
    const float y = k + r * softClip((a - k) / r);   // slope 1 at the knee, never above k + r
    return x < 0.0f ? -y : y;
}

// Parabolic sine of a phase in [0, 1).
static inline float paraSin(float p)
{
    const float t = p < 0.5f ? p : p - 1.0f;          // [-0.5, 0.5)
    return 8.0f * t * (1.0f - 2.0f * std::fabs(t));
}

static inline float hermite(float xm1, float x0, float x1, float x2, float t)
{
    const float c1 = 0.5f * (x1 - xm1);
    const float c2 = xm1 - 2.5f * x0 + 2.0f * x1 - 0.5f * x2;
    const float c3 = 0.5f * (x2 - xm1) + 1.5f * (x0 - x1);
    return ((c3 * t + c2) * t + c1) * t + x0;
}

struct Biquad
{
    float b0 = 1.0f, b1 = 0.0f, b2 = 0.0f, a1 = 0.0f, a2 = 0.0f;
    float z1 = 0.0f, z2 = 0.0f;

    void setLowpass(float f0, float q, float sr)
    {
        f0 = clampf(f0, 10.0f, 0.45f * sr);
        const float w = 2.0f * kPi * f0 / sr;
        const float c = std::cos(w), s = std::sin(w);
        const float alpha = s / (2.0f * q);
        const float a0 = 1.0f + alpha;
        b0 = (1.0f - c) * 0.5f / a0;
        b1 = (1.0f - c) / a0;
        b2 = b0;
        a1 = -2.0f * c / a0;
        a2 = (1.0f - alpha) / a0;
    }
    inline float process(float x)
    {
        const float y = b0 * x + z1;
        z1 = b1 * x - a1 * y + z2;
        z2 = b2 * x - a2 * y;
        return y;
    }
    void clear() { z1 = z2 = 0.0f; }
};

// ---------------------------------------------------------------------------

static const uint32_t kDiscs = 2;

struct Disc
{
    float    buf[kBufSize];
    Biquad   readLp;
    float    resLp = 0.0f, dcX = 0.0f, dcY = 0.0f, toneState = 0.0f;
    float    y = 0.0f, u = 0.0f, uPrev = 0.0f, dPrev = 0.0f, rPrev = 0.0f, regLp = 0.0f;
    float    m = 0.0f, mPrev = 0.0f, toned = 0.0f, wetLa = 0.0f;
    float    ap1[kApSize], ap2[kApSize], laY[kLaSize], laT[kLaSize];
    float    holdPh = 0.0f;

    void clear()
    {
        std::memset(buf, 0, sizeof(buf));
        readLp.clear(); resLp = 0.0f; dcX = dcY = 0.0f; toneState = 0.0f;
        y = u = 0.0f; uPrev = dPrev = rPrev = 0.0f; regLp = 0.0f;
        m = mPrev = 0.0f; toned = wetLa = 0.0f;
        std::memset(ap1, 0, sizeof(ap1)); std::memset(ap2, 0, sizeof(ap2));
        std::memset(laY, 0, sizeof(laY)); std::memset(laT, 0, sizeof(laT));
        holdPh = 0.0f;
    }

    // value d samples before write index w (d >= 2)
    inline float readTap(uint32_t w, float d) const
    {
        const uint32_t ip = (uint32_t)d;
        const float t = d - (float)ip;
        const uint32_t b = w - ip;
        return hermite(buf[(b + 1) & kBufMask], buf[b & kBufMask],
                       buf[(b - 1) & kBufMask], buf[(b - 2) & kBufMask], t);
    }
    inline float readTapLin(uint32_t w, float d) const
    {
        const uint32_t ip = (uint32_t)d;
        const float t = d - (float)ip;
        const uint32_t b = w - ip;
        const float a = buf[b & kBufMask];
        return a + t * (buf[(b - 1) & kBufMask] - a);
    }
    inline float readAbs(float pos) const
    {
        const float fl = std::floor(pos);
        const float t = pos - fl;
        const uint32_t b = (uint32_t)(int32_t)fl;
        return hermite(buf[(b - 1) & kBufMask], buf[b & kBufMask],
                       buf[(b + 1) & kBufMask], buf[(b + 2) & kBufMask], t);
    }
};

class CanAbyssStereoPlugin : public Plugin
{
public:
    CanAbyssStereoPlugin()
        : Plugin(kParameterCount, 0, 0)
    {
        fParams[kTime]      = 350.0f;
        fParams[kRepeat]    = 3.0f;
        fParams[kHold]      = 0.0f;
        fParams[kSpread]    = 0.0f;
        fParams[kReverb]    = 5.0f;
        fParams[kTone]      = 5.0f;
        fParams[kDiscSize]  = 5.0f;
        fParams[kWobble]    = 5.0f;
        fParams[kWear]      = 3.0f;
        fParams[kSag]       = 0.0f;
        fParams[kCeiling]   = -6.0f;
        fParams[kSafety]    = 1.0f;
        fParams[kTails]     = 1.0f;
        fParams[kMix]       = 50.0f;
        fParams[kBypass]    = 0.0f;

        buildTables();
        for (uint32_t c = 0; c < kDiscs; ++c) fD[c].clear();
        activate();
    }

protected:
    const char* getLabel()       const override { return "CanAbyssStereo"; }
    const char* getDescription() const override { return "Electrostatic oil can delay modelled on 1960s Tel-Ray / Morley units, with modern mods. Stereo: two discs on one motor."; }
    const char* getMaker()       const override { return "New Horizon Electronics"; }
    const char* getHomePage()    const override { return "https://github.com/Kiwooky/NHE-Can-Abyss-Stereo"; }
    const char* getLicense()     const override { return "MIT"; }
    uint32_t    getVersion()     const override { return d_version(1, 0, 0); }
    int64_t     getUniqueId()    const override { return d_cconst('C', 'A', 'B', 'S'); }

    void initAudioPort(bool input, uint32_t index, AudioPort& port) override
    {
        port.groupId = kPortGroupStereo;
        Plugin::initAudioPort(input, index, port);
    }

    void initParameter(uint32_t index, Parameter& p) override
    {
        p.hints = kParameterIsAutomatable;
        p.ranges.min = 0.0f;
        p.ranges.max = 10.0f;
        p.ranges.def = 5.0f;

        switch (index) {
        case kTime:
            p.hints |= kParameterIsLogarithmic;
            p.name = "Time"; p.symbol = "time"; p.unit = "ms";
            p.ranges.min = 40.0f; p.ranges.max = 2000.0f; p.ranges.def = 350.0f;
            p.groupId = kGroupDelay;
            break;
        case kRepeat:
            p.name = "Repeat"; p.symbol = "repeat"; p.ranges.def = 3.0f;
            p.groupId = kGroupDelay;
            break;
        case kHold:
            p.hints |= kParameterIsInteger | kParameterIsBoolean;
            p.name = "Hold"; p.symbol = "hold";
            p.ranges.max = 1.0f; p.ranges.def = 0.0f;
            p.groupId = kGroupDelay;
            break;
        case kSpread:
            p.name = "Spread"; p.symbol = "spread"; p.unit = "%";
            p.ranges.max = 100.0f; p.ranges.def = 0.0f;
            p.groupId = kGroupDelay;
            break;
        case kReverb:
            p.name = "Reverb"; p.symbol = "reverb";
            p.groupId = kGroupColour;
            break;
        case kTone:
            p.name = "Tone"; p.symbol = "tone";
            p.groupId = kGroupColour;
            break;
        case kDiscSize:
            p.name = "Disc Size"; p.symbol = "disc_size";
            p.groupId = kGroupColour;
            break;
        case kWobble:
            p.name = "Wobble"; p.symbol = "wobble";
            p.groupId = kGroupVibe;
            break;
        case kWear:
            p.name = "Wear"; p.symbol = "wear"; p.ranges.def = 3.0f;
            p.groupId = kGroupVibe;
            break;
        case kSag:
            p.name = "Sag"; p.symbol = "sag"; p.ranges.def = 0.0f;
            p.groupId = kGroupVibe;
            break;
        case kCeiling:
            p.name = "Ceiling"; p.symbol = "ceiling"; p.unit = "dB";
            p.ranges.min = -24.0f; p.ranges.max = 0.0f; p.ranges.def = -6.0f;
            p.groupId = kGroupMix;
            break;
        case kSafety:
            p.hints |= kParameterIsInteger | kParameterIsBoolean;
            p.name = "Safety"; p.symbol = "safety";
            p.ranges.max = 1.0f; p.ranges.def = 1.0f;
            p.groupId = kGroupMix;
            break;
        case kTails:
            p.hints |= kParameterIsInteger | kParameterIsBoolean;
            p.name = "Tails"; p.symbol = "tails";
            p.ranges.max = 1.0f; p.ranges.def = 1.0f;
            p.groupId = kGroupMix;
            break;
        case kMix:
            p.name = "Mix"; p.symbol = "mix"; p.unit = "%";
            p.ranges.max = 100.0f; p.ranges.def = 50.0f;
            p.groupId = kGroupMix;
            break;
        case kBypass:
            p.initDesignation(kParameterDesignationBypass);
            break;
        }
    }

    void initPortGroup(uint32_t groupId, PortGroup& g) override
    {
        switch (groupId) {
        case kGroupDelay:  g.name = "Delay";  g.symbol = "delay";  break;
        case kGroupColour: g.name = "Colour"; g.symbol = "colour"; break;
        case kGroupVibe:   g.name = "Vibe";   g.symbol = "vibe";   break;
        case kGroupMix:    g.name = "Mix";    g.symbol = "output"; break;
        }
    }

    float getParameterValue(uint32_t index) const override
    {
        return (index < kParameterCount) ? fParams[index] : 0.0f;
    }

    void setParameterValue(uint32_t index, float value) override
    {
        if (index < kParameterCount) fParams[index] = value;
    }

    void activate() override
    {
        fSr = (float)getSampleRate();
        if (fSr <= 0.0f) fSr = 48000.0f;

        fFast    = onePoleCoef(1.0f / (2.0f * kPi * 0.010f), fSr);   // 10 ms
        fSagAtk  = onePoleCoef(1.0f / (2.0f * kPi * 0.005f), fSr);
        fSagRel  = onePoleCoef(1.0f / (2.0f * kPi * 0.150f), fSr);
        fLimAtk  = onePoleCoef(1.0f / (2.0f * kPi * 0.0005f), fSr);  // 0.5 ms, inside the 2 ms lookahead
        fLa      = (uint32_t)(0.002f * fSr + 0.5f);
        if (fLa > kLaSize - 1) fLa = kLaSize - 1;
        fAp1D    = (uint32_t)(0.0031f * fSr);
        fAp2D    = (uint32_t)(0.0073f * fSr);
        fRegCoef = onePoleCoef(6000.0f, fSr);
        fLimRel  = onePoleCoef(1.0f / (2.0f * kPi * 0.150f), fSr);   // 150 ms
        fToneLp  = onePoleCoef(1200.0f, fSr);
        fDcCoef  = onePoleCoef(20.0f, fSr);
        fFlutLpC = onePoleCoef(10.0f, fSr / (float)kCtl);
        fFlutHpC = onePoleCoef(3.0f, fSr / (float)kCtl);
        fFlutGain = 1.0f / std::sqrt(fFlutLpC / (2.0f - fFlutLpC) / 3.0f);
        fDrift1  = 0.37f / fSr;
        fDrift2  = 0.61f / fSr;
        fMaxDelay = (float)(kBufSize / 2) - 8.0f;    // keep room for the hold seam
        fXfadeLen = 0.002f * fSr;                    // hold loop seam
        fPRef     = 0.35f * fSr / kWiper;            // stock revolution (350 ms echo)
        fHoldFade = 1.0f / (0.020f * fSr);           // hold release crossfade
        fSpreadK  = onePoleCoef(1.0f / (2.0f * kPi * 0.2f), fSr);  // the wiper arm moves, it doesn't jump

        clearState();
        fFirstRun = true;
    }

    void clearState()
    {
        for (uint32_t c = 0; c < kDiscs; ++c) fD[c].clear();
        fW = 0;
        fSagEnv = 0.0f; fLimEnv = 0.0f; fLimG = 1.0f;
        fApW = 0; fLaW = 0; fResidS = 0.0f;
        fTheta = 0.0f; fDp1 = 0.0f; fDp2 = 0.3f; fFl1 = fFl2 = 0.0f;
        fHolding = false; fHoldMix = 0.0f;
        fClearPos = kBufSize; fCleared = false;
    }

    void run(const float** inputs, float** outputs, uint32_t frames) override
    {
        const float  sr = fSr;

        // --- controls (as the mono plugin) ----------------------------------
        const float timeMs  = clampf(fParams[kTime], 40.0f, 2000.0f);
        const float xRep    = clampf(fParams[kRepeat] / 10.0f, 0.0f, 1.0f);
        const float gRepeat = xRep <= 0.8f ? std::pow(xRep / 0.8f, 1.2f)
                                           : 1.0f + (xRep - 0.8f) * 2.0f;
        const float resid   = 0.85f * clampf(fParams[kReverb] / 10.0f, 0.0f, 1.0f);
        const float residEff = std::fmin(resid, std::fmax(0.80f * (1.0f - gRepeat), 0.0f) + kResKeep * resid);

        const float td = clampf(fParams[kTone], 0.0f, 10.0f) - 5.0f;
        const float tn = std::fabs(td) < 0.4f ? 0.0f : (td - (td > 0.0f ? 0.4f : -0.4f)) / 4.6f;   // -1 .. 1
        const float hiDb = tn < 0.0f ? 24.0f * tn : 9.0f * tn;
        const float loDb = tn < 0.0f ? -3.0f * tn : -6.0f * tn;
        const float toneHi = std::pow(10.0f, hiDb / 20.0f);
        const float toneLo = std::pow(10.0f, loDb / 20.0f);

        const float kw = clampf(fParams[kWobble], 0.0f, 10.0f);
        const float wobK = kw <= 5.0f ? kw / 5.0f : 1.0f + 3.0f * std::pow((kw - 5.0f) / 5.0f, 1.5f);
        const float ks = clampf(fParams[kDiscSize], 0.0f, 10.0f);
        const float S  = ks < 5.0f ? std::pow(2.0f, (ks - 5.0f) / 2.5f) : std::pow(2.0f, (ks - 5.0f) / 5.0f);
        const float xw = clampf(fParams[kWear] / 10.0f, 0.0f, 1.0f);
        const float wearP = kWearPitch * xw * xw / S;
        const float wearA = kWearDip * xw * xw;

        const float m       = clampf(fParams[kMix] / 100.0f, 0.0f, 1.0f);
        const float mixDry  = clampf(2.0f * (1.0f - m), 0.0f, 1.0f);
        const float mixWet  = clampf(2.0f * m, 0.0f, 1.0f);
        const float xSag    = clampf(fParams[kSag] / 10.0f, 0.0f, 1.0f);
        const bool  hold    = fParams[kHold] > 0.5f;
        const bool  tails   = fParams[kTails] > 0.5f;
        const bool  safety  = fParams[kSafety] > 0.5f;
        const float ceilTarget = safety ? std::pow(10.0f, clampf(fParams[kCeiling], -24.0f, 0.0f) / 20.0f) : 8.0f;
        const bool  bypass  = fParams[kBypass] > 0.5f;
        // Spread: right read wiper from 324 down to 216 degrees
        const float spreadT = clampf(fParams[kSpread] / 100.0f, 0.0f, 1.0f);

        const float pTarget = timeMs * 0.001f * sr / kWiper;
        const float motorK  = onePoleCoef(1.0f / (2.0f * kPi * 0.2f * S), sr);
        const float wobDepth = wobK / S;
        const float slipMax  = clampf(0.05f / S, 0.0f, 0.15f);

        const float inTarget  = bypass ? 0.0f : 1.0f;
        const float wetTarget = (bypass && !tails) ? 0.0f : 1.0f;

        if (fFirstRun) {
            fFirstRun = false;
            fP = pTarget;
            fInGain = inTarget; fWetGain = wetTarget;
            fToneHi = toneHi; fToneLo = toneLo;
            fCeil = ceilTarget;
            fResidS = residEff;
            fSpread = spreadT;
            fHolding = hold; fHoldMix = 0.0f;
            if (hold) startHold();
        }

        // Tails off: clear both discs in slices once the wet has faded out
        if (!bypass) {
            fCleared = false;
            fClearPos = kBufSize;
        } else if (!tails && !fCleared && fClearPos >= kBufSize && fWetGain < 1e-4f) {
            fClearPos = 0;
        }
        if (fClearPos < kBufSize) {
            const uint32_t n = 16384;
            for (uint32_t c = 0; c < kDiscs; ++c)
                std::memset(fD[c].buf + fClearPos, 0, n * sizeof(float));
            fClearPos += n;
            if (fClearPos >= kBufSize) {
                fCleared = true;
                for (uint32_t c = 0; c < kDiscs; ++c) { fD[c].readLp.clear(); fD[c].resLp = 0.0f; fD[c].y = 0.0f; }
            }
        }

        if (hold && !fHolding) { fHolding = true; startHold(); }
        if (!hold && fHolding) { fHolding = false; }

        for (uint32_t i = 0; i < frames; ++i) {
            if (fCtlCount == 0) {
                fCtlCount = kCtl;
                const float T = fP * kWiper / sr;
                const float fc = clampf(3500.0f * std::sqrt(S * 0.35f / T), 800.0f, 5500.0f);
                for (uint32_t c = 0; c < kDiscs; ++c) fD[c].readLp.setLowpass(fc, 0.6f, sr);
                fResCoef = onePoleCoef(1.5f * fc, sr);
                fInvP = 1.0f / fP;
                fSpeedShare = fPRef * fInvP;
                fFl1 += fFlutLpC * (rnd() - fFl1);
                fFl2 += fFlutHpC * (fFl1 - fFl2);
                fFlutter = (fFl1 - fFl2) * fFlutGain;
            }
            --fCtlCount;

            fInGain  += fFast * (inTarget - fInGain);
            fWetGain += fFast * (wetTarget - fWetGain);
            fToneHi  += fFast * (toneHi - fToneHi);
            fToneLo  += fFast * (toneLo - fToneLo);
            fCeil    += fFast * (ceilTarget - fCeil);
            fSpread  += fSpreadK * (spreadT - fSpread);

            // --- sag: one tube supply for both sides --------------------
            float au = 0.0f;
            for (uint32_t c = 0; c < kDiscs; ++c) {
                Disc& d = fD[c];
                d.u = fInGain * inputs[c][i] + gRepeat * fWetGain * d.y;
                au = std::fmax(au, std::fabs(d.u));
            }
            fSagEnv += (au > fSagEnv ? fSagAtk : fSagRel) * (au - fSagEnv);
            const float sagAmt = xSag * clampf(fSagEnv * 10.0f, 0.0f, 1.0f);

            // --- one motor ------------------------------------------------
            const float pGoal = pTarget / (1.0f - slipMax * sagAmt);
            fP += motorK * (pGoal - fP);
            const float P = fP;

            fTheta += fInvP;
            if (fTheta >= 1.0f) fTheta -= 1.0f;

            fDp1 += fDrift1; if (fDp1 >= 1.0f) fDp1 -= 1.0f;
            fDp2 += fDrift2; if (fDp2 >= 1.0f) fDp2 -= 1.0f;
            const float drift = 0.6f * paraSin(fDp1) + 0.4f * paraSin(fDp2);
            const float warb = wobDepth * (kWobRev * paraSin(fTheta) + fSpeedShare * (kWobDrift * drift + kWobFlut * fFlutter));

            fResidS += fFast * (residEff - fResidS);
            const float wiperR = kWiper - 0.3f * fSpread;
            const float w0 = 1.0f - 0.75f * sagAmt;              // supply droop
            const uint32_t laRo = (fLaW - fLa) & (kLaSize - 1);

            for (uint32_t c = 0; c < kDiscs; ++c) {
                Disc& d = fD[c];
                const float wiper = c == 0 ? kWiper : wiperR;
                // the wear under this disc's read wiper: the right pickup sits
                // further round, so it reads another patch of the disc
                float th = fTheta + (kWiper - wiper);
                if (th >= 1.0f) th -= 1.0f;
                const float tp = th * (float)kTabSize;
                const uint32_t ti = (uint32_t)tp;
                const float tf = tp - (float)ti;
                const float wsp = fWearSpd[ti & (kTabSize - 1)] + tf * (fWearSpd[(ti + 1) & (kTabSize - 1)] - fWearSpd[ti & (kTabSize - 1)]);
                const float wlv = fWearLvl[ti & (kTabSize - 1)] + tf * (fWearLvl[(ti + 1) & (kTabSize - 1)] - fWearLvl[ti & (kTabSize - 1)]);

                d.mPrev = d.m;
                d.m = warb + wearP * wsp;

                const float pMod = P * (1.0f + d.m);
                const float tau  = clampf(wiper * pMod - (float)fLa, 4.0f, fMaxDelay);
                const float pRes = clampf(pMod - (float)(fAp1D + fAp2D), 4.0f, fMaxDelay);

                const float w = w0 * 0.5f * (writeCurve(0.5f * (d.u + d.uPrev)) + writeCurve(d.u));
                d.uPrev = d.u;

                const float resIn = d.readTapLin(fW, pRes);
                d.resLp += fResCoef * (resIn - d.resLp);
                float rv = d.resLp;
                {
                    const float b1 = d.ap1[(fApW - fAp1D) & (kApSize - 1)];
                    const float v1 = rv - kApG * b1;
                    d.ap1[fApW] = v1; rv = kApG * v1 + b1;
                    const float b2 = d.ap2[(fApW - fAp2D) & (kApSize - 1)];
                    const float v2 = rv - kApG * b2;
                    d.ap2[fApW] = v2; rv = kApG * v2 + b2;
                }
                const float dSig = w + fResidS * fWetGain * rv;

                float y0 = 0.0f;
                if (!fHolding)
                    y0 = d.readTap(fW, tau);

                if (fHolding || fHoldMix > 0.0f) {
                    float yh = d.readAbs((float)fHoldW - fHoldP + d.holdPh);
                    const float toEnd = fHoldP - d.holdPh;
                    if (toEnd < fXfadeLen) {
                        const float f = 1.0f - toEnd / fXfadeLen;
                        const float yo = d.readAbs((float)fHoldW - 2.0f * fHoldP + d.holdPh);
                        yh += f * (yo - yh);
                    }
                    const float rate = fHoldP / P - wiper * P * (d.m - d.mPrev);
                    d.holdPh += rate;
                    while (d.holdPh >= fHoldP) d.holdPh -= fHoldP;
                    while (d.holdPh < 0.0f) d.holdPh += fHoldP;
                    if (fHolding) {
                        y0 = yh;
                    } else {
                        y0 += (fHoldMix - fHoldFade < 0.0f ? 0.0f : fHoldMix - fHoldFade) * (yh - y0);
                    }
                }

                if (!fHolding) {
                    d.buf[fW] = 0.5f * (discCurve(0.5f * (dSig + d.dPrev)) + discCurve(dSig)) + 1e-18f;
                    d.dPrev = dSig;
                }

                float r = y0 * (1.0f - wearA * wlv);
                r = d.readLp.process(r);
                const float yr = 0.5f * (softClip(0.5f * (r + d.rPrev)) + softClip(r));
                d.rPrev = r;
                const float yd = yr - d.dcX + (1.0f - fDcCoef) * d.dcY;
                d.dcX = yr; d.dcY = yd;

                d.toneState += fToneLp * (yd - d.toneState);
                d.toned = (fToneLo * d.toneState + fToneHi * (yd - d.toneState)) * fWetGain;

                d.laY[fLaW] = yd;
                d.laT[fLaW] = d.toned;
                const float yLoop = d.laY[laRo];
                d.wetLa = d.laT[laRo];
                d.regLp += fRegCoef * (yLoop - d.regLp);
                d.y = d.regLp;
            }

            // shared indices move once per sample, for both discs
            fApW = (fApW + 1) & (kApSize - 1);
            fLaW = (fLaW + 1) & (kLaSize - 1);
            if (!fHolding) fW = (fW + 1) & kBufMask;
            if (fHolding) fHoldMix = 1.0f;
            else if (fHoldMix > 0.0f) { fHoldMix -= fHoldFade; if (fHoldMix < 0.0f) fHoldMix = 0.0f; }

            // --- Safety: one limiter for both sides (the image stays put) --
            float at = 0.0f;
            for (uint32_t c = 0; c < kDiscs; ++c) at = std::fmax(at, std::fabs(fD[c].toned));
            fLimEnv += (at > fLimEnv ? fLimAtk : fLimRel) * (at - fLimEnv);
            const float gT = fLimEnv > fCeil ? fCeil / fLimEnv : 1.0f;
            fLimG += (gT < fLimG ? fLimAtk : fLimRel) * (gT - fLimG);

            const float dry = 1.0f + fInGain * (mixDry - 1.0f);  // bypassed: dry at unity
            for (uint32_t c = 0; c < kDiscs; ++c) {
                const float wet = softKnee(fD[c].wetLa * fLimG, 0.85f * fCeil, 0.15f * fCeil);
                outputs[c][i] = softKnee(dry * inputs[c][i] + mixWet * wet, 0.89f, 0.1f);
            }
        }
    }

private:
    inline float rnd()
    {
        fRng ^= fRng << 13; fRng ^= fRng >> 17; fRng ^= fRng << 5;
        return (float)(int32_t)fRng * (1.0f / 2147483648.0f);
    }

    void startHold()
    {
        fHoldW  = fW;
        fHoldP  = clampf(fP, 8.0f, fMaxDelay);
        const float wiperR = kWiper - 0.3f * fSpread;
        for (uint32_t c = 0; c < kDiscs; ++c) {
            const float wiper = c == 0 ? kWiper : wiperR;
            fD[c].holdPh = fHoldP - clampf(wiper * fP * (1.0f + fD[c].m) - (float)fLa, 4.0f, fHoldP - 1.0f);
        }
        fHoldMix = 1.0f;
    }

    void buildTables()
    {
        uint32_t s = 0x9E3779B9u;
        auto r = [&s]() {
            s ^= s << 13; s ^= s >> 17; s ^= s << 5;
            return (float)(int32_t)s * (1.0f / 2147483648.0f);
        };
        float amp[7], ph[7];
        for (int h = 0; h < 7; ++h) { amp[h] = r() / (float)(h + 2); ph[h] = r() * kPi; }
        float sum = 0.0f;
        for (uint32_t i = 0; i < kTabSize; ++i) {
            const float a = 2.0f * kPi * (float)i / (float)kTabSize;
            float v = 0.0f;
            for (int h = 0; h < 7; ++h) v += amp[h] * std::sin((float)(h + 2) * a + ph[h]);
            fWearSpd[i] = v;
            sum += v * v;
        }
        const float g = 1.0f / std::sqrt(sum / (float)kTabSize + 1e-12f);
        for (uint32_t i = 0; i < kTabSize; ++i) fWearSpd[i] *= g;

        for (uint32_t i = 0; i < kTabSize; ++i) fWearLvl[i] = 0.0f;
        for (int d = 0; d < 9; ++d) {
            const float c = 0.5f * (r() + 1.0f) * (float)kTabSize;
            const float wdt = 6.0f + 30.0f * 0.5f * (r() + 1.0f);
            const float depth = 0.3f + 0.7f * 0.5f * (r() + 1.0f);
            for (uint32_t i = 0; i < kTabSize; ++i) {
                float dx = std::fabs((float)i - c);
                if (dx > (float)kTabSize * 0.5f) dx = (float)kTabSize - dx;
                const float e = dx / wdt;
                const float v = depth * std::exp(-e * e);
                if (v > fWearLvl[i]) fWearLvl[i] = v;
            }
        }
    }

    float fParams[kParameterCount];
    Disc  fD[kDiscs];
    float fWearSpd[kTabSize];
    float fWearLvl[kTabSize];
    uint32_t fW = 0, fCtlCount = 0, fClearPos = kBufSize;

    float fResCoef = 0.1f, fDcCoef = 0.0f, fToneLp = 0.0f;
    float fToneHi = 1.0f, fToneLo = 1.0f;
    float fSagEnv = 0.0f, fLimEnv = 0.0f, fCeil = 0.5f, fLimAtk = 0.0f, fLimRel = 0.0f, fLimG = 1.0f;
    uint32_t fApW = 0, fAp1D = 149, fAp2D = 350, fLaW = 0, fLa = 96;
    float fRegCoef = 0.5f, fResidS = 0.0f;
    float fP = 16800.0f, fTheta = 0.0f;
    float fDp1 = 0.0f, fDp2 = 0.3f, fFl1 = 0.0f, fFl2 = 0.0f, fFlutGain = 1.0f;
    float fSpread = 0.0f, fSpreadK = 0.0f;

    bool  fHolding = false;
    uint32_t fHoldW = 0;
    float fHoldP = 0.0f, fHoldMix = 0.0f, fHoldFade = 0.0f, fXfadeLen = 96.0f;

    float fSr = 48000.0f, fMaxDelay = 1000.0f, fPRef = 18666.0f;
    float fFast = 0.0f, fSagAtk = 0.0f, fSagRel = 0.0f;
    float fFlutLpC = 0.0f, fFlutHpC = 0.0f;
    float fInvP = 1.0f / 16800.0f, fSpeedShare = 1.0f, fFlutter = 0.0f;
    float fDrift1 = 0.0f, fDrift2 = 0.0f;
    float fInGain = 1.0f, fWetGain = 1.0f;
    uint32_t fRng = 0x12345678u;
    bool  fFirstRun = true, fCleared = false;

    DISTRHO_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(CanAbyssStereoPlugin)
};

Plugin* createPlugin() { return new CanAbyssStereoPlugin(); }

END_NAMESPACE_DISTRHO
