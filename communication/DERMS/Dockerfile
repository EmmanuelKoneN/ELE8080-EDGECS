# Image de developpement : bibliotheque OpenDNP3 3.1.2 archivee, sans support.
# Pour usage industrialise, analyser/remplacer cette dependance et durcir l'image.
FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git pkg-config ca-certificates \
    libssl-dev libjsoncpp-dev libdrogon-dev libcurl4-openssl-dev libpaho-mqttpp-dev nlohmann-json3-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch 3.1.2 --recurse-submodules https://github.com/dnp3/opendnp3.git /tmp/opendnp3 \
 && cmake -S /tmp/opendnp3 -B /tmp/opendnp3/build -DCMAKE_BUILD_TYPE=Release \
      -DDNP3_TLS=OFF -DDNP3_TEST=OFF -DDNP3_DEMO=OFF \
 && cmake --build /tmp/opendnp3/build -j2 \
 && cmake --install /tmp/opendnp3/build \
 && ldconfig
WORKDIR /app/DERMS
# Build from the workspace root: docker build -f DERMS/Dockerfile .
# Copy source explicitly so workspace certificates/private keys never enter the image.
COPY shared /app/shared
COPY DERMS/CMakeLists.txt ./CMakeLists.txt
COPY DERMS/src ./src
COPY DERMS/config ./config
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
 && cmake --build build -j2

# Cette image conserve l'outillage de compilation pour simplifier le prototypage.
# Monter le certificat et la cle au runtime (ne JAMAIS ajouter de cle privee a l'image).
EXPOSE 8443
CMD ["/app/DERMS/build/edgecs_master"]
