ARG GOTENBERG_IMAGE
FROM ${GOTENBERG_IMAGE}
USER root
COPY NotoSansSC-variable.ttf /usr/local/share/fonts/m13/NotoSansSC-variable.ttf
COPY NotoSansSC-OFL.txt /usr/local/share/fonts/m13/NotoSansSC-OFL.txt
RUN fc-cache -f && fc-match 'Noto Sans SC'
USER gotenberg
