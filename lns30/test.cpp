#include "lns30.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>

int main() {
  using namespace lns30;
  constexpr int n = 400000;
  for (auto mode : {Shaper::Mode::Rounded, Shaper::Mode::Tpdf, Shaper::Mode::Shaped30}) {
    Shaper s(mode); double sum = 0, peak = 0;
    for (int i = 0; i < n; ++i) {
      double x = 0.88 * std::sin(2 * 3.141592653589793 * 997 * i / 768000.0);
      auto q = s.process(x);
      assert(q >= -524288 && q <= 524287);
      double delta = Shaper::unpack(q) - x;
      assert(std::isfinite(delta));
      sum += delta*delta;
      peak = std::max(peak, std::abs(delta));
    }
    std::cout << "mode=" << static_cast<int>(mode)
              << " whole-band_error_dBFS=" << 10*std::log10(sum/n)
              << " max_abs_error=" << peak << "\n";
    s.reset();
    assert(s.process(std::numeric_limits<double>::quiet_NaN()) == 0);
    assert(s.process(7.0) == 524287);
    assert(s.process(-7.0) == -524288);
  }
  std::cout << "PASS: bounded 20-bit integer range, finite error, nonfinite input, reset, clipping\n";
}
