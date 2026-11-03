FROM stirlingtools/stirling-pdf-base:1.1.0@sha256:3bcc8e10d5319b7c0550cf41b96f6980e1552c974dc37aba462b74fa17c4b5e4
ARG VERSION_TAG=3.2.2
WORKDIR /app
COPY app.jar /app.jar
COPY scripts/ /scripts/
COPY fonts/ /usr/share/fonts/truetype/
COPY LICENSE.stirling /opt/smartpdf-licenses/Stirling-PDF-LICENSE
RUN chmod +x /scripts/*.sh && echo 3.2.2 > /etc/stirling_version && fc-cache -f \
    && ln -s /logs /app/logs && ln -s /configs /app/configs \
    && ln -s /customFiles /app/customFiles && ln -s /pipeline /app/pipeline && ln -s /storage /app/storage \
    && chown -h stirlingpdfuser:stirlingpdfgroup /app/logs /app/configs /app/customFiles /app/pipeline /app/storage \
    && chown stirlingpdfuser:stirlingpdfgroup /app
ENV VERSION_TAG=$VERSION_TAG \
    FORMDETECTION_PREINSTALLEDMODELDIR="/opt/stirling/preinstalled-models" \
    STIRLING_AOT_ENABLE="false" \
    _JVM_OPTS="-XX:+ExitOnOutOfMemoryError -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/configs/heap_dumps -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC -XX:G1PeriodicGCInterval=10000 -XX:G1PeriodicGCSystemLoadThreshold=0.0 -XX:+G1PeriodicGCInvokesConcurrent -XX:+UseCompactObjectHeaders -XX:+UseStringDeduplication -XX:+ExplicitGCInvokesConcurrent -XX:ReservedCodeCacheSize=96m -XX:CICompilerCount=2 -Dspring.threads.virtual.enabled=true -Djava.awt.headless=true" \
    JAVA_CUSTOM_OPTS="" \
    HOME=/home/stirlingpdfuser \
    PUID=1000 \
    PGID=1000 \
    UMASK=022 \
    STIRLING_TEMPFILES_DIRECTORY=/tmp/stirling-pdf \
    TMPDIR=/tmp/stirling-pdf \
    TEMP=/tmp/stirling-pdf \
    TMP=/tmp/stirling-pdf \
    DBUS_SESSION_BUS_ADDRESS=/dev/null \
    SAL_TMP=/tmp/stirling-pdf/libre


ENV FAT_DOCKER=true
LABEL org.opencontainers.image.title="Smart PDF internal Stirling core candidate" org.opencontainers.image.version="3.2.2-core-poc"
EXPOSE 8080
ENTRYPOINT ["tini","--","/scripts/init.sh"]
