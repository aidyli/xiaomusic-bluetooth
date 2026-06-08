FROM debian:bookworm-slim
ENV container=docker DEBIAN_FRONTEND=noninteractive
STOPSIGNAL SIGRTMIN+3
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    systemd systemd-sysv dbus bluez bluez-tools rfkill usbutils procps psmisc \
    pulseaudio pulseaudio-module-bluetooth pulseaudio-utils \
    mpv ffmpeg ca-certificates python3 curl kmod \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl set-default multi-user.target \
 && systemctl enable bluetooth.service
COPY sidecar-server.py /usr/local/bin/sidecar-server.py
COPY pulse-system.pa /etc/pulse/system.pa
COPY bt-pulseaudio.service /etc/systemd/system/bt-pulseaudio.service
COPY bt-sidecar-bridge.service /etc/systemd/system/bt-sidecar-bridge.service
COPY bt-prep.service /etc/systemd/system/bt-prep.service
RUN chmod +x /usr/local/bin/sidecar-server.py \
 && systemctl enable bt-prep.service bt-pulseaudio.service bt-sidecar-bridge.service
CMD ["/sbin/init"]
