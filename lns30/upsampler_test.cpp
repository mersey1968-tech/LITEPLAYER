#include "upsampler.hpp"
#include "lns30.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <vector>
#include <limits>
int main() {
  constexpr double pi = 3.14159265358979323846;
  for(unsigned factor: {16u,32u}) {
    lns30::PolyphaseUpsampler up(factor,128,0.96);
    lns30::Shaper sh(lns30::Shaper::Mode::Shaped30);
    std::vector<double> buffer(factor);
    double dcSum=0; size_t dcN=0; double e=0;
    for(unsigned n=0;n<32000;++n) {
      const double x=(n<16000)?0.2:0.77*std::sin(2*pi*1000*n/48000.0);
      up.push(x,buffer.data());
      for(double y:buffer) {
        if(!std::isfinite(y)) return 2;
        if(n>=400 && n<16000) {dcSum+=y; ++dcN;}
        int32_t q=sh.process(y);
        if(q<-524288 || q>524287) return 3;
        e+=std::pow(lns30::Shaper::unpack(q)-y,2);
      }
    }
    const double avg=dcSum/dcN;
    if(std::abs(avg-0.2)>1e-5) return 4;
    std::cout << "rate " << 48000*factor << " Hz | 20-bit range PASS | DC " << avg
              << " | quantization error RMS " << std::sqrt(e/(32000*factor)) << "\n";
  }
  std::cout<<"PASS: basic resampling and quantization numerical smoke tests. NOT proof of transparency. DSD not yet implemented.\n";
  return 0;
}
