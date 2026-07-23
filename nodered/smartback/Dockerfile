FROM nodered/node-red:latest

USER root
COPY package.json /tmp/smartback-package.json
RUN cd /usr/src/node-red \
    && npm install --omit=dev --no-audit --no-fund --no-update-notifier \
       node-red-contrib-influxdb@0.7.0
USER node-red
