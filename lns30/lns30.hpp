#pragma once
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <algorithm>

// Experimental bounded-error-feedback 30-tap PCM noise shaper.
// Not a reproduction of HQPlayer LNS15.
namespace lns30 {
class Shaper {
public:
    static constexpr int kBits = 20;
    static constexpr int kOrder = 30;
    static constexpr double kScale = 524288.0;
    enum class Mode { Rounded, Tpdf, Shaped30 };
    explicit Shaper(Mode mode = Mode::Shaped30, uint64_t seed = 0x9e3779b97f4a7c15ULL)
      : mode_(mode), rng_(seed ? seed : 1) {
        double sum = 0;
        for (int i = 0; i < kOrder; ++i) {
            weights_[i] = std::exp(-static_cast<double>(i) / 7.0);
            sum += weights_[i];
        }
        for (auto &w : weights_) w *= -0.82 / sum;
    }
    void reset() { errors_.fill(0); index_ = 0; }
    int32_t process(double x) {
        if (!std::isfinite(x)) { reset(); x = 0; }
        const double clipped = std::clamp(x, -1.0, 1.0 - 1.0 / kScale);
        double v = clipped;
        if (mode_ == Mode::Shaped30) {
            for (int i = 0; i < kOrder; ++i) {
                const size_t slot = (index_ + kOrder - 1 - static_cast<size_t>(i)) % kOrder;
                v += weights_[i] * errors_[slot];
            }
        }
        if (mode_ == Mode::Tpdf) v += (uniform() - uniform()) / kScale;
        const double rounded = std::nearbyint(v * kScale);
        const int32_t q = static_cast<int32_t>(std::clamp(rounded, -kScale, kScale - 1));
        if (mode_ == Mode::Shaped30) {
            errors_[index_] = static_cast<double>(q) / kScale - v;
            index_ = (index_ + 1) % kOrder;
        }
        return q;
    }
    static double unpack(int32_t q) { return static_cast<double>(q) / kScale; }
private:
    double uniform() {
        rng_ ^= rng_ >> 12; rng_ ^= rng_ << 25; rng_ ^= rng_ >> 27;
        uint64_t val = rng_ * 2685821657736338717ULL;
        return static_cast<double>(val >> 11) / 9007199254740992.0;
    }
    Mode mode_;
    uint64_t rng_;
    std::array<double, kOrder> weights_{};
    std::array<double, kOrder> errors_{};
    size_t index_ = 0;
};
}
