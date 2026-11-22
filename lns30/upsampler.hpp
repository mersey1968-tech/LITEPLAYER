#pragma once
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>
#include <stdexcept>

// Preliminary streaming polyphase windowed-sinc 16x / 32x resampler.
// This is a numerical test vehicle, not yet a proven transparent upsampler.
namespace lns30 {
class PolyphaseUpsampler {
public:
    explicit PolyphaseUpsampler(unsigned factor, unsigned taps=128, double cutoff=0.96)
      : factor_(factor), taps_(taps), history_(taps,0.0), index_(0) {
        if ((factor != 16 && factor != 32) || taps < 8 || taps%2 ||
            cutoff <= 0 || cutoff > 1.0)
            throw std::invalid_argument("Unsupported resampler configuration");
        const double pi=3.14159265358979323846;
        coefficients_.resize(size_t(factor_)*taps_);
        for(unsigned p=0;p<factor_;++p) {
            double sum=0;
            for(unsigned k=0;k<taps_;++k) {
                // Lag k from most recent input. Delay = taps/2-1 input frames.
                const double d=double(k)-double(taps_/2-1)+double(p)/factor_;
                const double x=pi*cutoff*d;
                const double sinc=std::abs(x)<1e-13?1.0:std::sin(x)/x;
                const double window=0.35875-0.48829*std::cos(2*pi*k/(taps_-1))
                    +0.14128*std::cos(4*pi*k/(taps_-1))
                    -0.01168*std::cos(6*pi*k/(taps_-1));
                const double h=cutoff*sinc*window;
                coefficients_[size_t(p)*taps_+k]=h;
                sum+=h;
            }
            for(unsigned k=0;k<taps_;++k)
                coefficients_[size_t(p)*taps_+k]/=sum;
        }
    }
    void reset(){std::fill(history_.begin(),history_.end(),0.0);index_=0;}
    unsigned factor() const {return factor_;}
    unsigned taps() const {return taps_;}
    // out must hold at least factor() doubles. Stream retains filter delay.
    void push(double input,double *out) {
        history_[index_]=std::isfinite(input)?input:0;
        index_=(index_+1)%taps_;
        for(unsigned p=0;p<factor_;++p) {
            double acc=0;
            for(unsigned k=0;k<taps_;++k) {
                const size_t i=(index_+taps_-1-k)%taps_;
                acc+=history_[i]*coefficients_[size_t(p)*taps_+k];
            }
            out[p]=acc;
        }
    }
private:
    unsigned factor_,taps_;
    std::vector<double> history_,coefficients_;
    size_t index_;
};
}
