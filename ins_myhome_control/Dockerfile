ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

WORKDIR /app
COPY rootfs/app /app
COPY rootfs/etc/services.d /etc/services.d

RUN chmod a+x /etc/services.d/ins-myhome-control/run

LABEL io.hass.name="INS MyHome Control" \
      io.hass.description="Private Home Assistant control center"
