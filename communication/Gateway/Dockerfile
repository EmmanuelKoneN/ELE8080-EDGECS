# Construction de demo. Télécharge OpenDNP3 3.1.2 (archive) pendant le build.
# NE PAS utiliser sur une installation électrique réelle.
FROM debian:bookworm AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates \
    libssl-dev libcurl4-openssl-dev libpaho-mqttpp-dev nlohmann-json3-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp
RUN git clone --depth 1 --branch 3.1.2 --recurse-submodules https://github.com/dnp3/opendnp3.git \
 && cmake -S opendnp3 -B opendnp3-build -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local -DDNP3_TLS=OFF -DDNP3_DEMO=OFF -DDNP3_TEST=OFF \
 && cmake --build opendnp3-build --parallel 2 \
 && cmake --install opendnp3-build
WORKDIR /src
# Build context is the workspace root: docker build -f Gateway/Dockerfile .
COPY shared /shared
COPY Gateway/CMakeLists.txt ./
COPY Gateway/src ./src
COPY Gateway/tests ./tests
COPY Gateway/config ./config
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
 && cmake --build build --parallel 2 \
 && ctest --test-dir build --output-on-failure

FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libstdc++6 libcurl4 libpaho-mqttpp3-1 libpaho-mqtt1.3 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/lib/libopendnp3* /usr/local/lib/
COPY --from=build /src/build/edgecs_gateway /usr/local/bin/edgecs_gateway
COPY --from=build /src/build/edgecs_bess_sim /usr/local/bin/edgecs_bess_sim
COPY --from=build /src/build/edgecs_der_sim /usr/local/bin/edgecs_der_sim
WORKDIR /app
COPY Gateway/config ./config
ENV DNP3_BIND_HOST=0.0.0.0
RUN ldconfig
EXPOSE 20000/tcp
ENTRYPOINT ["/usr/local/bin/edgecs_gateway"]
CMD []
