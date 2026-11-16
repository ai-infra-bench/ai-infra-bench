# Incremental tools layer for the retained amd64 source workspace image.
# Download the same fixed Debian packages directly, avoiding an index refresh.
FROM sha256:132e45efd65f98fcbff55cf970488371c2d19baffe08ff6ad8b1ea1d1e0c2f24
ADD https://deb.debian.org/debian/pool/main/libu/libunwind/libunwind8_1.6.2-3_amd64.deb /tmp/libunwind8.deb
ADD https://deb.debian.org/debian/pool/main/s/strace/strace_6.1-0.1_amd64.deb /tmp/strace.deb
RUN echo '7b297868682836e4c87be349f17e4a56bc287586e3576503e84a5cb5485ce925  /tmp/libunwind8.deb' | sha256sum -c - \
 && echo '1942d086a6244a1a9643489d3b0aa604ac44b88991d6c69217a63a193671bd4f  /tmp/strace.deb' | sha256sum -c - \
 && dpkg -i /tmp/libunwind8.deb /tmp/strace.deb \
 && test "$(dpkg-query -W -f='${Version}' strace)" = '6.1-0.1' \
 && rm /tmp/libunwind8.deb /tmp/strace.deb
