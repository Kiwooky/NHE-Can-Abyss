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
// Modern mods (New Horizon): Disc Size, Sag (tube supply droop + motor
// slip), Hold (frozen disc that still varispeeds), and Noise Mods: separate
// Disc / Hiss / Hum levels with a predictive gate that knows when every echo
// will arrive, because the envelope rides the disc next to the audio.
// ---------------------------------------------------------------------------

static const float    kPi       = 3.14159265358979f;
static const uint32_t kBufSize  = 1u << 19;      // 5.4 s at 96 kHz: loop + one older revolution
static const uint32_t kBufMask  = kBufSize - 1;
static const uint32_t kEnvDec   = 16;            // envelope track decimation
static const uint32_t kEnvSize  = kBufSize / kEnvDec;
static const uint32_t kEnvMask  = kEnvSize - 1;
static const uint32_t kTabSize  = 4096;          // disc surface, one revolution
static const uint32_t kHumSize  = 256;
static const float    kWiper    = 0.9f;          // read wiper at 324 degrees
static const uint32_t kCtl      = 16;            // control-rate block
// warble depths as fractions of the delay (stock Wobble, stock disc)
static const float    kClipBias = 0.1f * (27.0f + 0.01f) / (27.0f + 0.09f);   // softClip(0.1)
static const float    kWobRev   = 0.00045f;      // disc runout, once per revolution
static const float    kWobDrift = 0.0012f;       // belt drift, 0.37 + 0.61 Hz
static const float    kWobFlut  = 0.00004f;      // motor flutter, 3-10 Hz

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

class CanAbyssPlugin : public Plugin
{
public:
    CanAbyssPlugin()
        : Plugin(kParameterCount, 0, 0)
    {
        fParams[kTime]      = 350.0f;
        fParams[kRepeat]    = 3.0f;
        fParams[kReverb]    = 5.0f;
        fParams[kTone]      = 5.0f;
        fParams[kWobble]    = 5.0f;
        fParams[kDiscSize]  = 5.0f;
        fParams[kMix]       = 50.0f;
        fParams[kSag]       = 0.0f;
        fParams[kHold]      = 0.0f;
        fParams[kNoiseMods] = 0.0f;
        fParams[kDiscNoise] = 5.0f;
        fParams[kHiss]      = 5.0f;
        fParams[kHum]       = 5.0f;
        fParams[kHumHz]     = 60.0f;
        fParams[kTails]     = 1.0f;
        fParams[kBypass]    = 0.0f;

        buildTables();
        std::memset(fBuf, 0, sizeof(fBuf));
        std::memset(fEnv, 0, sizeof(fEnv));
        activate();
    }

protected:
    const char* getLabel()       const override { return "CanAbyss"; }
    const char* getDescription() const override { return "Electrostatic oil can delay modelled on 1960s Tel-Ray / Morley units, with modern mods."; }
    const char* getMaker()       const override { return "New Horizon Electronics"; }
    const char* getHomePage()    const override { return "https://github.com/Kiwooky/NHE-Can-Abyss"; }
    const char* getLicense()     const override { return "MIT"; }
    uint32_t    getVersion()     const override { return d_version(1, 0, 0); }
    int64_t     getUniqueId()    const override { return d_cconst('C', 'A', 'B', 'Y'); }

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
            break;
        case kRepeat:
            p.name = "Repeat"; p.symbol = "repeat"; p.ranges.def = 3.0f;
            break;
        case kReverb:
            p.name = "Reverb"; p.symbol = "reverb";
            break;
        case kTone:
            p.name = "Tone"; p.symbol = "tone";
            break;
        case kWobble:
            p.name = "Wobble"; p.symbol = "wobble";
            break;
        case kDiscSize:
            p.name = "Disc Size"; p.symbol = "disc_size";
            break;
        case kMix:
            p.name = "Mix"; p.symbol = "mix"; p.unit = "%";
            p.ranges.max = 100.0f; p.ranges.def = 50.0f;
            break;
        case kSag:
            p.name = "Sag"; p.symbol = "sag"; p.ranges.def = 0.0f;
            break;
        case kHold:
            p.hints |= kParameterIsInteger | kParameterIsBoolean;
            p.name = "Hold"; p.symbol = "hold";
            p.ranges.max = 1.0f; p.ranges.def = 0.0f;
            break;
        case kNoiseMods:
            p.hints |= kParameterIsInteger | kParameterIsBoolean;
            p.name = "Noise Mods"; p.symbol = "noise_mods";
            p.ranges.max = 1.0f; p.ranges.def = 0.0f;
            break;
        case kDiscNoise:
            p.name = "Disc"; p.symbol = "disc_noise";
            break;
        case kHiss:
            p.name = "Hiss"; p.symbol = "hiss";
            break;
        case kHum:
            p.name = "Hum"; p.symbol = "hum";
            break;
        case kHumHz: {
            p.hints |= kParameterIsInteger;
            p.name = "Hum Hz"; p.symbol = "hum_hz"; p.unit = "Hz";
            p.ranges.min = 50.0f; p.ranges.max = 60.0f; p.ranges.def = 60.0f;
            static ParameterEnumerationValue values[2];
            values[0].value = 50.0f; values[0].label = "50 Hz";
            values[1].value = 60.0f; values[1].label = "60 Hz";
            p.enumValues.count = 2;
            p.enumValues.restrictedMode = true;
            p.enumValues.values = values;
            p.enumValues.deleteLater = false;
            break;
        }
        case kTails:
            p.hints |= kParameterIsInteger | kParameterIsBoolean;
            p.name = "Tails"; p.symbol = "tails";
            p.ranges.max = 1.0f; p.ranges.def = 1.0f;
            break;
        case kBypass:
            p.initDesignation(kParameterDesignationBypass);
            break;
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
        fNoiseSm = onePoleCoef(1.0f / (2.0f * kPi * 0.050f), fSr);   // 50 ms unlock glide
        fNbFade  = onePoleCoef(1.0f / (2.0f * kPi * 0.500f), fSr);   // noise fade in bypass
        fSagAtk  = onePoleCoef(1.0f / (2.0f * kPi * 0.005f), fSr);
        fSagRel  = onePoleCoef(1.0f / (2.0f * kPi * 0.150f), fSr);
        fEnvRel  = onePoleCoef(1.0f / (2.0f * kPi * 0.030f), fSr);
        fGateAtk = onePoleCoef(1.0f / (2.0f * kPi * 0.002f), fSr);
        fGateRel = onePoleCoef(1.0f / (2.0f * kPi * 0.060f), fSr);
        fToneLp  = onePoleCoef(1500.0f, fSr);
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

        clearState();
        fFirstRun = true;
    }

    void clearState()
    {
        std::memset(fBuf, 0, sizeof(fBuf));
        std::memset(fEnv, 0, sizeof(fEnv));
        fW = 0; fEnvMax = 0.0f; fEnvW = 0; fEnvCount = 0;
        fReadLp.clear(); fResLp = 0.0f; fDcX = fDcY = 0.0f; fToneState = 0.0f;
        fY = 0.0f; fEnvD = 0.0f; fSagEnv = 0.0f;
        fOpenW = fOpenR = 1.0f;
        fTheta = 0.0f; fDp1 = 0.0f; fDp2 = 0.3f; fFl1 = fFl2 = 0.0f;
        fHumPh = 0.0f; fM = 0.0f;
        fHolding = false; fHoldMix = 0.0f;
        fClearPos = kBufSize; fCleared = false;
    }

    void run(const float** inputs, float** outputs, uint32_t frames) override
    {
        const float* in     = inputs[0];
        float*       outMix = outputs[0];
        float*       outWet = outputs[1];
        const float  sr     = fSr;

        // --- controls ------------------------------------------------------
        const float timeMs  = clampf(fParams[kTime], 40.0f, 2000.0f);
        const float xRep    = clampf(fParams[kRepeat] / 10.0f, 0.0f, 1.0f);
        const float gRepeat = 1.1f * std::pow(xRep, 1.2f);
        const float resid   = 0.85f * clampf(fParams[kReverb] / 10.0f, 0.0f, 1.0f);
        const float toneDb  = (fParams[kTone] - 5.0f) * (fParams[kTone] < 5.0f ? 1.8f : 1.2f);
        const float toneG   = std::pow(10.0f, toneDb / 20.0f);       // -9 .. +6 dB above 1.5 kHz
        const float wobK    = clampf(fParams[kWobble] / 5.0f, 0.0f, 2.0f);
        const float S       = std::pow(2.0f, (clampf(fParams[kDiscSize], 0.0f, 10.0f) - 5.0f) / 5.0f);
        const float m       = clampf(fParams[kMix] / 100.0f, 0.0f, 1.0f);
        const float mixDry  = clampf(2.0f * (1.0f - m), 0.0f, 1.0f);
        const float mixWet  = clampf(2.0f * m, 0.0f, 1.0f);
        const float xSag    = clampf(fParams[kSag] / 10.0f, 0.0f, 1.0f);
        const bool  hold    = fParams[kHold] > 0.5f;
        const bool  unlock  = fParams[kNoiseMods] > 0.5f;
        const float humHz   = fParams[kHumHz] < 55.0f ? 50.0f : 60.0f;
        const bool  tails   = fParams[kTails] > 0.5f;
        const bool  bypass  = fParams[kBypass] > 0.5f;

        // motor: target revolution in samples, inertia grows with disc mass
        const float pTarget = timeMs * 0.001f * sr / kWiper;
        const float motorK  = onePoleCoef(1.0f / (2.0f * kPi * 0.2f * S), sr);
        const float wobDepth = wobK / S;

        // noise knobs: locked = stock (5)
        const float tDisc = unlock ? clampf(fParams[kDiscNoise], 0.0f, 10.0f) : 5.0f;
        const float tHiss = unlock ? clampf(fParams[kHiss],      0.0f, 10.0f) : 5.0f;
        const float tHum  = unlock ? clampf(fParams[kHum],       0.0f, 10.0f) : 5.0f;

        const float inTarget  = bypass ? 0.0f : 1.0f;
        const float wetTarget = (bypass && !tails) ? 0.0f : 1.0f;
        const float nbTarget  = bypass ? 0.0f : 1.0f;

        if (fFirstRun) {
            // controls arrive with the first run(): start there, no glides
            fFirstRun = false;
            fP = pTarget;
            fInGain = inTarget; fWetGain = wetTarget; fNb = nbTarget;
            fKDisc = tDisc; fKHiss = tHiss; fKHum = tHum;
            fToneG = toneG;
            fHolding = hold; fHoldMix = 0.0f;
            if (hold) startHold();
        }

        // Tails off: once the wet has faded out in bypass, clear the disc in
        // slices (no 2 MB memset inside one block). Both loops are already
        // scaled by the wet gain, so nothing recirculates meanwhile.
        if (!bypass) {
            fCleared = false;
            fClearPos = kBufSize;
        } else if (!tails && !fCleared && fClearPos >= kBufSize && fWetGain < 1e-4f) {
            fClearPos = 0;
        }
        if (fClearPos < kBufSize) {
            const uint32_t n = 16384;
            std::memset(fBuf + fClearPos, 0, n * sizeof(float));
            std::memset(fEnv + fClearPos / kEnvDec, 0, (n / kEnvDec) * sizeof(float));
            fClearPos += n;
            if (fClearPos >= kBufSize) {
                fCleared = true;
                fReadLp.clear(); fResLp = 0.0f; fY = 0.0f; fEnvD = 0.0f;
            }
        }

        // hold engage / release
        if (hold && !fHolding) { fHolding = true; startHold(); }
        if (!hold && fHolding) { fHolding = false; }

        const float humInc = humHz / sr;

        for (uint32_t i = 0; i < frames; ++i) {
            // --- control rate -------------------------------------------
            if (fCtlCount == 0) {
                fCtlCount = kCtl;
                const float T = fP * kWiper / sr;           // current first-echo time, s
                const float fc = clampf(3500.0f * std::sqrt(S * 0.35f / T), 800.0f, 8000.0f);
                fReadLp.setLowpass(fc, 0.6f, sr);
                fResCoef = onePoleCoef(1.5f * fc, sr);
                noiseShape(fKDisc, fLvDisc, fFlDisc);
                noiseShape(fKHiss, fLvHiss, fFlHiss);
                noiseShape(fKHum,  fLvHum,  fFlHum);
                fInvP = 1.0f / fP;
                fSpeedShare = fPRef * fInvP;
                // flutter noise, 3-10 Hz: control rate is plenty
                fFl1 += fFlutLpC * (rnd() - fFl1);
                fFl2 += fFlutHpC * (fFl1 - fFl2);
                fFlutter = (fFl1 - fFl2) * fFlutGain;
                // read-side gate looks at the envelope arriving 3 ms ahead
                fEnvAhead = readEnv(kWiper * fP * (1.0f + fM) - 0.003f * sr);
            }
            --fCtlCount;

            const float x = in[i];

            fInGain  += fFast * (inTarget - fInGain);
            fWetGain += fFast * (wetTarget - fWetGain);
            fNb      += fNbFade * (nbTarget - fNb);
            fToneG   += fFast * (toneG - fToneG);
            fKDisc   += fNoiseSm * (tDisc - fKDisc);
            fKHiss   += fNoiseSm * (tHiss - fKHiss);
            fKHum    += fNoiseSm * (tHum - fKHum);

            // --- sag: tube supply droop + motor slip ----------------------
            const float u = fInGain * x + gRepeat * fWetGain * fY;
            const float au = std::fabs(u);
            fSagEnv += (au > fSagEnv ? fSagAtk : fSagRel) * (au - fSagEnv);
            const float sagAmt = xSag * clampf(fSagEnv * 2.5f, 0.0f, 1.0f);

            // --- motor ----------------------------------------------------
            const float pGoal = pTarget / (1.0f - 0.03f * sagAmt / S);
            fP += motorK * (pGoal - fP);
            const float P = fP;

            // mechanical warble: once per revolution + belt drift + flutter
            fTheta += fInvP;
            if (fTheta >= 1.0f) fTheta -= 1.0f;
            fDp1 += fDrift1; if (fDp1 >= 1.0f) fDp1 -= 1.0f;
            fDp2 += fDrift2; if (fDp2 >= 1.0f) fDp2 -= 1.0f;
            const float drift = 0.6f * paraSin(fDp1) + 0.4f * paraSin(fDp2);
            const float flutter = fFlutter;
            const float mPrev = fM;
            // speed changes are a fixed fraction of motor speed, so their share of
            // the delay shrinks as the delay grows (pitch wobble stays put);
            // the once-per-rev runout is already locked to the revolution
            fM = wobDepth * (kWobRev * paraSin(fTheta) + fSpeedShare * (kWobDrift * drift + kWobFlut * flutter));

            const float pMod = P * (1.0f + fM);
            const float tau  = clampf(kWiper * pMod, 4.0f, fMaxDelay);
            const float pRes = clampf(pMod, 4.0f, fMaxDelay);

            const float lvDisc = fLvDisc, flDisc = fFlDisc;
            const float lvHiss = fLvHiss, flHiss = fFlHiss;
            const float lvHum  = fLvHum,  flHum  = fFlHum;

            // --- write: tube stage + disc --------------------------------
            const float drive = 1.5f;
            const float bias  = 0.1f;               // tube bias: a touch of even harmonics
            const float w = (1.0f - 0.5f * sagAmt)
                          * (softClip(drive * u + bias) - kClipBias) * (1.0f / drive);

            // envelope of what goes onto the disc (signal only)
            const float resIn = readTapLin(fW, pRes);   // residual is low-passed anyway
            fResLp += fResCoef * (resIn - fResLp);
            const float dSig = w + resid * fWetGain * fResLp;
            const float ad = std::fabs(dSig);
            fEnvD = ad > fEnvD ? ad : fEnvD + fEnvRel * (ad - fEnvD);

            // predictive gate: noise written now travels with this signal
            const float oW = gateOpen(fEnvD);
            fOpenW += (oW > fOpenW ? fGateAtk : fGateRel) * (oW - fOpenW);
            // ... and read-side noise looks at the envelope arriving 3 ms ahead
            const float oR = fHolding ? 1.0f : gateOpen(fEnvAhead);
            fOpenR += (oR > fOpenR ? fGateAtk : fGateRel) * (oR - fOpenR);

            float hissW = 0.0f, hissR = 0.0f;
            if (lvHiss > 1e-5f) {
                const float g = fNb * lvHiss * 3.87e-4f;            // -70 dBFS total, split write/read
                hissW = g * (flHiss + (1.0f - flHiss) * fOpenW) * rnd();
                hissR = g * (flHiss + (1.0f - flHiss) * fOpenR) * rnd();
            }

            float dNew;
            float y0;
            if (!fHolding) {
                dNew = 1.6f * softClip((dSig + hissW) * (1.0f / 1.6f)) + 1e-18f;   // charge saturates
                y0 = readTap(fW, tau);
            } else {
                dNew = 0.0f;
                y0 = 0.0f;
            }

            // hold loop reader (frozen disc still varispeeds and warbles)
            if (fHolding || fHoldMix > 0.0f) {
                float yh = readAbs((float)fHoldW - fHoldP + fHoldPh);
                const float toEnd = fHoldP - fHoldPh;
                if (toEnd < fXfadeLen) {
                    const float f = 1.0f - toEnd / fXfadeLen;
                    const float yo = readAbs((float)fHoldW - 2.0f * fHoldP + fHoldPh);
                    yh += f * (yo - yh);
                }
                const float rate = fHoldP / P - kWiper * P * (fM - mPrev);
                fHoldPh += rate;
                while (fHoldPh >= fHoldP) fHoldPh -= fHoldP;
                while (fHoldPh < 0.0f) fHoldPh += fHoldP;
                if (fHolding) {
                    fHoldMix = 1.0f;
                    y0 = yh;
                } else {
                    fHoldMix -= fHoldFade;
                    if (fHoldMix < 0.0f) fHoldMix = 0.0f;
                    y0 += fHoldMix * (yh - y0);
                }
            }

            if (!fHolding) {
                fBuf[fW] = dNew;
                fEnvMax = ad > fEnvMax ? ad : fEnvMax;
                if (++fEnvCount >= kEnvDec) {
                    fEnv[fEnvW] = fEnvMax;
                    fEnvW = (fEnvW + 1) & kEnvMask;
                    fEnvMax = 0.0f; fEnvCount = 0;
                }
                fW = (fW + 1) & kBufMask;
            }

            // --- read stage: surface noise, hum, wiper bandwidth, tube ---
            float r = y0;
            if (lvDisc > 1e-5f) {
                const float tp = fTheta * (float)kTabSize;
                const uint32_t ti = (uint32_t)tp;
                const float tf = tp - (float)ti;
                const float a = fTab[ti & (kTabSize - 1)], b = fTab[(ti + 1) & (kTabSize - 1)];
                r += fNb * lvDisc * 5.0e-4f * (flDisc + (1.0f - flDisc) * fOpenR) * (a + tf * (b - a));
            }
            r = fReadLp.process(r);
            if (lvHum > 1e-5f) {
                fHumPh += humInc; if (fHumPh >= 1.0f) fHumPh -= 1.0f;
                const float hp = fHumPh * (float)kHumSize;
                const uint32_t hi = (uint32_t)hp;
                const float hf = hp - (float)hi;
                const float a = fHumTab[hi & (kHumSize - 1)], b = fHumTab[(hi + 1) & (kHumSize - 1)];
                r += fNb * lvHum * 2.5e-4f * (flHum + (1.0f - flHum) * fOpenR) * (a + hf * (b - a));
            }
            r += hissR;
            float yr = softClip(r);
            // DC blocker (the tube stages are biased)
            const float yd = yr - fDcX + (1.0f - fDcCoef) * fDcY;
            fDcX = yr; fDcY = yd;
            fY = yd;

            // --- tone (electronics EQ, out of the loop) -----------------
            fToneState += fToneLp * (yd - fToneState);
            const float wet = (fToneState + fToneG * (yd - fToneState)) * fWetGain;

            // --- outputs --------------------------------------------------
            const float dry = 1.0f + fInGain * (mixDry - 1.0f);  // bypassed: dry at unity
            outMix[i] = dry * x + mixWet * wet;
            outWet[i] = wet;
        }
    }

private:
    // 12 o'clock = stock. Right: up to +12 dB. Left: the predictive gate
    // deepens to -30 dB first (5 -> 1.5), then the source fades out (1.5 -> 0).
    static inline void noiseShape(float k, float& level, float& floorGain)
    {
        if (k >= 5.0f) {
            level = std::exp((k - 5.0f) * (12.0f / 5.0f) * 0.115129f);   // dB -> gain
            floorGain = 1.0f;
        } else if (k >= 1.5f) {
            level = 1.0f;
            floorGain = std::exp(-30.0f * ((5.0f - k) / 3.5f) * 0.115129f);
        } else {
            const float f = k / 1.5f;
            level = f * f;
            floorGain = 0.0316f;
        }
    }

    static inline float gateOpen(float env)
    {
        return clampf(env * (1.0f / 0.004f), 0.0f, 1.0f);   // fully open above -48 dBFS
    }

    inline float rnd()
    {
        fRng ^= fRng << 13; fRng ^= fRng >> 17; fRng ^= fRng << 5;
        return (float)(int32_t)fRng * (1.0f / 2147483648.0f);
    }

    // value d samples before write index w (d >= 2)
    inline float readTap(uint32_t w, float d) const
    {
        const uint32_t ip = (uint32_t)d;
        const float t = d - (float)ip;
        const uint32_t b = w - ip;
        return hermite(fBuf[(b + 1) & kBufMask], fBuf[b & kBufMask],
                       fBuf[(b - 1) & kBufMask], fBuf[(b - 2) & kBufMask], t);
    }

    // linear version for the residual tap (its loss filter hides the difference)
    inline float readTapLin(uint32_t w, float d) const
    {
        const uint32_t ip = (uint32_t)d;
        const float t = d - (float)ip;
        const uint32_t b = w - ip;
        const float a = fBuf[b & kBufMask];
        return a + t * (fBuf[(b - 1) & kBufMask] - a);
    }

    // value at absolute (possibly negative, wrapping) float index
    inline float readAbs(float pos) const
    {
        const float fl = std::floor(pos);
        const float t = pos - fl;
        const uint32_t b = (uint32_t)(int32_t)fl;
        return hermite(fBuf[(b - 1) & kBufMask], fBuf[b & kBufMask],
                       fBuf[(b + 1) & kBufMask], fBuf[(b + 2) & kBufMask], t);
    }

    inline float readEnv(float d) const
    {
        if (d < 0.0f) d = 0.0f;
        const float de = d / (float)kEnvDec;
        const uint32_t ip = (uint32_t)de;
        const float t = de - (float)ip;
        const uint32_t b = fEnvW - 1 - ip;
        const float a = fEnv[b & kEnvMask], c = fEnv[(b - 1) & kEnvMask];
        return a + t * (c - a);
    }

    void startHold()
    {
        // freeze the disc: the loop is the last revolution behind the write
        // wiper; the reader starts exactly where the read wiper was
        fHoldW  = fW;
        fHoldP  = clampf(fP, 8.0f, fMaxDelay);
        fHoldPh = fHoldP - clampf(kWiper * fP * (1.0f + fM), 4.0f, fHoldP - 1.0f);
        fHoldMix = 1.0f;
    }

    void buildTables()
    {
        // disc surface: a light grain plus sparse crackle, one revolution
        uint32_t s = 0x9E3779B9u;
        auto r = [&s]() {
            s ^= s << 13; s ^= s >> 17; s ^= s << 5;
            return (float)(int32_t)s * (1.0f / 2147483648.0f);
        };
        float lp = 0.0f, tail = 0.0f, sum = 0.0f;
        for (uint32_t i = 0; i < kTabSize; ++i) {
            lp += 0.3f * (r() - lp);
            if (std::fabs(r()) > 0.985f) tail = 6.0f * r();
            tail *= 0.6f;
            fTab[i] = 0.4f * lp + tail;
            sum += fTab[i] * fTab[i];
        }
        float mean = 0.0f;
        for (uint32_t i = 0; i < kTabSize; ++i) mean += fTab[i];
        mean /= (float)kTabSize;
        sum = 0.0f;
        for (uint32_t i = 0; i < kTabSize; ++i) { fTab[i] -= mean; sum += fTab[i] * fTab[i]; }
        const float g = 1.0f / std::sqrt(sum / (float)kTabSize + 1e-12f);
        for (uint32_t i = 0; i < kTabSize; ++i) fTab[i] *= g;

        // hum: fundamental + 3 harmonics, RMS 1
        sum = 0.0f;
        for (uint32_t i = 0; i < kHumSize; ++i) {
            const float ph = 2.0f * kPi * (float)i / (float)kHumSize;
            fHumTab[i] = std::sin(ph) + 0.5f * std::sin(2.0f * ph) + 0.3f * std::sin(3.0f * ph) + 0.15f * std::sin(4.0f * ph);
            sum += fHumTab[i] * fHumTab[i];
        }
        const float h = 1.0f / std::sqrt(sum / (float)kHumSize);
        for (uint32_t i = 0; i < kHumSize; ++i) fHumTab[i] *= h;
    }

    float fParams[kParameterCount];

    float    fBuf[kBufSize];
    float    fEnv[kEnvSize];
    float    fTab[kTabSize];
    float    fHumTab[kHumSize];
    uint32_t fW = 0, fEnvW = 0, fEnvCount = 0, fCtlCount = 0, fClearPos = kBufSize;
    float    fEnvMax = 0.0f;

    Biquad fReadLp;
    float fResLp = 0.0f, fResCoef = 0.1f;
    float fDcX = 0.0f, fDcY = 0.0f, fDcCoef = 0.0f, fToneState = 0.0f, fToneLp = 0.0f, fToneG = 1.0f;
    float fY = 0.0f, fEnvD = 0.0f, fSagEnv = 0.0f, fOpenW = 1.0f, fOpenR = 1.0f;
    float fP = 16800.0f, fTheta = 0.0f, fM = 0.0f;
    float fDp1 = 0.0f, fDp2 = 0.3f, fFl1 = 0.0f, fFl2 = 0.0f, fFlutGain = 1.0f;
    float fHumPh = 0.0f;

    bool  fHolding = false;
    uint32_t fHoldW = 0;
    float fHoldP = 0.0f, fHoldPh = 0.0f, fHoldMix = 0.0f, fHoldFade = 0.0f, fXfadeLen = 96.0f;

    float fSr = 48000.0f, fMaxDelay = 1000.0f, fPRef = 18666.0f;
    float fFast = 0.0f, fNoiseSm = 0.0f, fNbFade = 0.0f, fSagAtk = 0.0f, fSagRel = 0.0f;
    float fEnvRel = 0.0f, fGateAtk = 0.0f, fGateRel = 0.0f, fFlutLpC = 0.0f, fFlutHpC = 0.0f;
    float fInvP = 1.0f / 16800.0f, fSpeedShare = 1.0f, fFlutter = 0.0f, fEnvAhead = 0.0f;
    float fDrift1 = 0.0f, fDrift2 = 0.0f;
    float fInGain = 1.0f, fWetGain = 1.0f, fNb = 1.0f;
    float fKDisc = 5.0f, fKHiss = 5.0f, fKHum = 5.0f;
    float fLvDisc = 1.0f, fFlDisc = 1.0f, fLvHiss = 1.0f, fFlHiss = 1.0f, fLvHum = 1.0f, fFlHum = 1.0f;
    uint32_t fRng = 0x12345678u;
    bool  fFirstRun = true, fCleared = false;

    DISTRHO_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(CanAbyssPlugin)
};

Plugin* createPlugin() { return new CanAbyssPlugin(); }

END_NAMESPACE_DISTRHO
