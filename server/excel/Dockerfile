# Build only after verifying the local baseline tag against config's baselineImageId.
FROM smartpdf-stirling-core:3.2.2-poc2
USER root
# The slim base removes image themes, including the *document* conditional-format
# arrow/traffic-light assets. Restore the matching upstream package, hash locked.
ADD --checksum=sha256:298a9278ed46a7095308173896ea8177bd4f3b2a48e7112d75e2a1f06f14a0f1 https://ppa.launchpadcontent.net/libreoffice/ppa/ubuntu/pool/main/libr/libreoffice/libreoffice-style-colibre_26.2.6.3-0ubuntu0.24.04.1~lo1_all.deb /tmp/excel-colibre.deb
RUN dpkg-deb -x /tmp/excel-colibre.deb /tmp/excel-colibre && cp /tmp/excel-colibre/usr/share/libreoffice/share/config/images_colibre.zip /usr/lib/libreoffice/share/config/images_colibre.zip && mkdir -p /usr/share/doc/excel-colibre && cp /tmp/excel-colibre/usr/share/doc/libreoffice-style-colibre/copyright /usr/share/doc/excel-colibre/copyright && rm -rf /tmp/excel-colibre /tmp/excel-colibre.deb
# LibreOffice classifies its own embedded charts as active content. The XLSX
# preflight blocks OLE, macros, external data and linked images; this image still
# disables macro execution/OLE automation and retains the network/filesystem sandbox.
RUN python3 -c 'from pathlib import Path; p=Path("/usr/lib/libreoffice/share/registry/stirling-hardening.xcd"); s=p.read_text(); old="<prop oor:name=\"DisableActiveContent\" oor:finalized=\"true\">\n          <value>true</value>"; assert s.count(old)==1; p.write_text(s.replace(old, old.replace("<value>true</value>", "<value>false</value>")))'
USER stirlingpdfuser
LABEL org.opencontainers.image.title="Smart PDF Excel chart-capable core candidate"
