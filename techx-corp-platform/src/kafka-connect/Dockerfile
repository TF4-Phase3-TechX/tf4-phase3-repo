FROM eclipse-temurin:21-jre-alpine@sha256:3f08b13888f595cc49edabea7250ba69499ba25602b267da591720769400e08c

ARG KAFKA_VERSION=3.9.0
ARG SCALA_VERSION=2.13
ARG CONFLUENT_S3_SINK_VERSION=12.1.0

RUN apk add --no-cache bash curl gzip tar tini unzip \
    && addgroup -S app \
    && adduser -S app -G app \
    && mkdir -p /opt/kafka /usr/share/confluent-hub-components /var/lib/kafka-connect \
    && curl -fsSL "https://archive.apache.org/dist/kafka/${KAFKA_VERSION}/kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz" -o /tmp/kafka.tgz \
    && tar -xzf /tmp/kafka.tgz --strip-components=1 -C /opt/kafka \
    && curl -fsSL "https://api.hub.confluent.io/api/plugins/confluentinc/kafka-connect-s3/versions/${CONFLUENT_S3_SINK_VERSION}/archive" -o /tmp/kafka-connect-s3.zip \
    && unzip -q /tmp/kafka-connect-s3.zip -d /usr/share/confluent-hub-components \
    && rm -rf /tmp/kafka.tgz /tmp/kafka-connect-s3.zip \
    && chown -R app:app /opt/kafka /usr/share/confluent-hub-components /var/lib/kafka-connect

COPY src/kafka-connect/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER app
WORKDIR /opt/kafka
EXPOSE 8083

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
