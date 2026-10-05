/*
 * Minimal offline LV2 host for testing DPF plugins (lv2apply can't: DPF
 * requires the options + urid:map features, which lv2apply doesn't supply).
 *
 * Build:  gcc -O2 -I<DPF>/distrho/src -I<DPF>/distrho/src/lv2 lv2host.c -o lv2host -ldl
 *         (32-bit ARM: arm-linux-gnueabihf-gcc ... then run with
 *          qemu-arm -L /usr/arm-linux-gnueabihf ./lv2host ...)
 *
 * Usage:  lv2host plugin_dsp.so in.raw out.raw samplerate n_in n_out ctl0 ctl1 ... [@sample:port=value ...]
 *   in.raw  : float32 interleaved, n_in channels
 *   out.raw : float32 interleaved, n_out channels
 *   ctlN    : values for control ports in index order (ports n_in+n_out ...)
 *   @S:P=V  : at sample S set control port index P to V; repeatable (up to 64),
 *             applied at the start of the 256-frame block containing S
 */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lv2/lv2.h"
#include "lv2/atom.h"
#include "lv2/options.h"
#include "lv2/urid.h"
#include "lv2/buf-size.h"
#include "lv2/parameters.h"
static const char* uris[128]; static int nuris = 0;
static LV2_URID map(LV2_URID_Map_Handle h, const char* u) {
    (void)h; for (int i = 0; i < nuris; i++) if (!strcmp(uris[i], u)) return i + 1;
    uris[nuris] = strdup(u); return ++nuris; }
int main(int c, char** v) {
    if (c < 7) { fprintf(stderr, "usage: see header\n"); return 1; }
    void* lib = dlopen(v[1], RTLD_NOW); if (!lib) { puts(dlerror()); return 1; }
    const LV2_Descriptor* d = ((LV2_Descriptor_Function)dlsym(lib, "lv2_descriptor"))(0);
    double sr = atof(v[4]); int ni = atoi(v[5]), no = atoi(v[6]);
    FILE* f = fopen(v[2], "rb"); fseek(f, 0, 2); long n = ftell(f) / 4 / ni; rewind(f);
    float* in = malloc(n * ni * 4); if (fread(in, 4, n * ni, f) != (size_t)(n * ni)) return 1; fclose(f);
    float** ib = malloc(ni * sizeof(float*)); float** ob = malloc(no * sizeof(float*));
    int bs = 256; for (int i = 0; i < ni; i++) ib[i] = malloc(bs * 4); for (int i = 0; i < no; i++) ob[i] = malloc(bs * 4);
    float* out = malloc(n * no * 4); float srf = sr; int32_t bsi = bs;
    LV2_URID_Map m = { 0, map }; LV2_URID fl = map(0, LV2_ATOM__Float), it = map(0, LV2_ATOM__Int);
    LV2_Options_Option opts[] = {
        { LV2_OPTIONS_INSTANCE, 0, map(0, LV2_PARAMETERS__sampleRate), 4, fl, &srf },
        { LV2_OPTIONS_INSTANCE, 0, map(0, LV2_BUF_SIZE__maxBlockLength), 4, it, &bsi },
        { LV2_OPTIONS_INSTANCE, 0, map(0, LV2_BUF_SIZE__nominalBlockLength), 4, it, &bsi },
        { 0, 0, 0, 0, 0, 0 } };
    LV2_Feature fm = { LV2_URID__map, &m }, fo = { LV2_OPTIONS__options, opts };
    const LV2_Feature* feats[] = { &fm, &fo, 0 };
    LV2_Handle h = d->instantiate(d, sr, "", feats); if (!h) { puts("instantiate failed"); return 1; }
    float ctl[64]; int nc = 0;
    long evS[64]; int evP[64]; float evV[64]; int ne = 0;
    for (int a = 7; a < c; a++) {
        if (v[a][0] == '@') { if (ne < 64 && sscanf(v[a], "@%ld:%d=%f", &evS[ne], &evP[ne], &evV[ne]) == 3) ne++; }
        else { ctl[nc] = atof(v[a]); d->connect_port(h, ni + no + nc, &ctl[nc]); nc++; } }
    for (int i = 0; i < ni; i++) d->connect_port(h, i, ib[i]);
    for (int i = 0; i < no; i++) d->connect_port(h, ni + i, ob[i]);
    d->activate(h);
    for (long p = 0; p < n; p += bs) {
        long k = (n - p < bs) ? n - p : bs;
        for (int e = 0; e < ne; e++)
            if (evS[e] >= 0 && p + k > evS[e]) { ctl[evP[e] - ni - no] = evV[e]; evS[e] = -1; }
        for (long s = 0; s < k; s++) for (int i = 0; i < ni; i++) ib[i][s] = in[(p + s) * ni + i];
        d->run(h, k);
        for (long s = 0; s < k; s++) for (int i = 0; i < no; i++) out[(p + s) * no + i] = ob[i][s]; }
    f = fopen(v[3], "wb"); fwrite(out, 4, n * no, f); fclose(f);
    d->deactivate(h); d->cleanup(h); return 0; }
