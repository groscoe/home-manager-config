{ runCommand, clang, stdenv, pkg-config, libbpf, linuxHeaders }:
runCommand "camera-events" {
  nativeBuildInputs = [ clang stdenv.cc pkg-config ];
  buildInputs = [ libbpf ];
} ''
  mkdir -p "$out/bin" "$out/lib"
  ${clang.cc}/bin/clang -target bpf -O2 -g -Wall -Werror \
    -I${linuxHeaders}/include -I${libbpf}/include \
    -I${./.} -c ${./camera.bpf.c} -o "$out/lib/camera.bpf.o"
  $CC -O2 -Wall -Wextra -Werror ${./events.c} -I${./.} \
    $(pkg-config --cflags --libs libbpf) -o "$out/bin/camera-events"
''
