#!/usr/bin/env bash
# Realistic World mod jar'ini paketler.
# Mod tamamen veri odaklidir (Java kodu yok); bu yuzden Gradle/Loom gerekmez —
# jar sadece kaynak dosyalarin arsividir.
set -euo pipefail
cd "$(dirname "$0")"

VERSION="1.1.1+26.2"
JAR="dist/realisticworld-${VERSION}.jar"

python3 tools/validate.py

mkdir -p dist
rm -f "$JAR"
jar --create --file "$JAR" -C src/main/resources .
jar --list --file "$JAR" | head -5
echo "olusturuldu: $JAR ($(du -h "$JAR" | cut -f1))"
