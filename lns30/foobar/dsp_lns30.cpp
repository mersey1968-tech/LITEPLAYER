#include "stdafx.h"
#include "lns30.hpp"
#include <vector>

// Early listening-test wrapper. Quantization is applied within foobar2000's
// floating-point DSP chain; output must be tested for subsequent processing.
class dsp_lns30 : public dsp_impl_base {
public:
    explicit dsp_lns30(const dsp_preset &) {}
    static GUID g_get_guid() {
        return {0x750e5431,0x85a5,0x45d0,{0x9b,0xa8,0x52,0xd5,0x24,0xe6,0x78,0xd1}};
    }
    static void g_get_name(pfc::string_base &out) {
        out = "LNS30 Experimental 20-bit (705.6k+)";
    }
    static bool g_get_default_preset(dsp_preset &out) {
        dsp_preset_builder builder;
        builder.finish(g_get_guid(),out);
        return true;
    }
    static bool g_have_config_popup() {return false;}
    bool on_chunk(audio_chunk *chunk, abort_callback &) {
        const auto rate=chunk->get_srate();
        const auto ch=chunk->get_channels();
        if(rate != lastRate || ch != lastChannels) {
            flush();
            lastRate=rate;
            lastChannels=ch;
        }
        // Deliberate bypass until an appropriate high-rate resampler is in front.
        if(rate < 705600 || ch == 0 || ch > 32) return true;
        if(shapers.size() != ch) {
            shapers.clear();
            for(unsigned i=0;i<ch;++i)
                shapers.emplace_back(lns30::Shaper::Mode::Shaped30,
                    0x9e3779b97f4a7c15ULL + 0xbf58476d1ce4e5b9ULL*i);
        }
        audio_sample *data=chunk->get_data();
        const auto samples=chunk->get_sample_count();
        for(size_t i=0;i<samples;++i) for(unsigned c=0;c<ch;++c) {
            const size_t at=i*ch+c;
            data[at]=(audio_sample)lns30::Shaper::unpack(
                shapers[c].process((double)data[at]));
        }
        return true;
    }
    void flush() {shapers.clear();}
    void on_endofplayback(abort_callback &) {}
    void on_endoftrack(abort_callback &) {}
    double get_latency() {return 0;}
    bool need_track_change_mark() {return false;}
private:
    unsigned lastRate=0,lastChannels=0;
    std::vector<lns30::Shaper> shapers;
};
static dsp_factory_nopreset_t<dsp_lns30> g_lns30_dsp_factory;
