FROM eclipse-temurin:21-jre-noble@sha256:373787d1d45a87f084fda43e7de0e9acf5eedee049446efac738f13587ec4c64

ARG KAFKA_VERSION=3.9.2
ARG SCALA_VERSION=2.13
ARG CONFLUENT_S3_SINK_VERSION=10.6.14
ARG JACKSON_VERSION=2.18.8
ARG NETTY_VERSION=4.1.136.Final
ARG ZOOKEEPER_VERSION=3.8.6
ARG BOUNCYCASTLE_VERSION=1.84
ARG PLEXUS_UTILS_VERSION=3.6.1
ARG JLINE_VERSION=3.30.14

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl gzip tar tini unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /opt/kafka --shell /usr/sbin/nologin app \
    && mkdir -p /opt/kafka /usr/share/confluent-hub-components /var/lib/kafka-connect \
    && curl -fsSL "https://archive.apache.org/dist/kafka/${KAFKA_VERSION}/kafka_${SCALA_VERSION}-${KAFKA_VERSION}.tgz" -o /tmp/kafka.tgz \
    && tar -xzf /tmp/kafka.tgz --strip-components=1 -C /opt/kafka \
    && curl -fsSL "https://api.hub.confluent.io/api/plugins/confluentinc/kafka-connect-s3/versions/${CONFLUENT_S3_SINK_VERSION}/archive" -o /tmp/kafka-connect-s3.zip \
    && unzip -q /tmp/kafka-connect-s3.zip -d /usr/share/confluent-hub-components \
    && connector_lib_dir="$(find /usr/share/confluent-hub-components -type d -path '*/lib' | head -n 1)" \
    && test -n "$connector_lib_dir" \
    && find /opt/kafka "$connector_lib_dir" -name 'jackson-core-*.jar' -delete \
    && find /opt/kafka "$connector_lib_dir" -name 'jackson-databind-*.jar' -delete \
    && find /opt/kafka "$connector_lib_dir" -name 'netty-codec-*.jar' -delete \
    && find /opt/kafka "$connector_lib_dir" -name 'netty-handler-*.jar' -delete \
    && find /opt/kafka "$connector_lib_dir" -name 'zookeeper-*.jar' -delete \
    && find /opt/kafka "$connector_lib_dir" -name 'bcprov-jdk18on-*.jar' -delete \
    && find /opt/kafka "$connector_lib_dir" -name 'plexus-utils-*.jar' -delete \
    && find /opt/kafka "$connector_lib_dir" -name 'jline-*.jar' -delete \
    && curl -fsSL "https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-core/${JACKSON_VERSION}/jackson-core-${JACKSON_VERSION}.jar" -o /tmp/jackson-core.jar \
    && curl -fsSL "https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-databind/${JACKSON_VERSION}/jackson-databind-${JACKSON_VERSION}.jar" -o /tmp/jackson-databind.jar \
    && curl -fsSL "https://repo1.maven.org/maven2/io/netty/netty-codec/${NETTY_VERSION}/netty-codec-${NETTY_VERSION}.jar" -o /tmp/netty-codec.jar \
    && curl -fsSL "https://repo1.maven.org/maven2/io/netty/netty-handler/${NETTY_VERSION}/netty-handler-${NETTY_VERSION}.jar" -o /tmp/netty-handler.jar \
    && curl -fsSL "https://repo1.maven.org/maven2/org/apache/zookeeper/zookeeper/${ZOOKEEPER_VERSION}/zookeeper-${ZOOKEEPER_VERSION}.jar" -o /tmp/zookeeper.jar \
    && curl -fsSL "https://repo1.maven.org/maven2/org/bouncycastle/bcprov-jdk18on/${BOUNCYCASTLE_VERSION}/bcprov-jdk18on-${BOUNCYCASTLE_VERSION}.jar" -o /tmp/bcprov-jdk18on.jar \
    && curl -fsSL "https://repo1.maven.org/maven2/org/codehaus/plexus/plexus-utils/${PLEXUS_UTILS_VERSION}/plexus-utils-${PLEXUS_UTILS_VERSION}.jar" -o /tmp/plexus-utils.jar \
    && curl -fsSL "https://repo1.maven.org/maven2/org/jline/jline/${JLINE_VERSION}/jline-${JLINE_VERSION}.jar" -o /tmp/jline.jar \
    && for lib_dir in /opt/kafka/libs "$connector_lib_dir"; do \
        cp /tmp/jackson-core.jar "$lib_dir/jackson-core-${JACKSON_VERSION}.jar"; \
        cp /tmp/jackson-databind.jar "$lib_dir/jackson-databind-${JACKSON_VERSION}.jar"; \
        cp /tmp/netty-codec.jar "$lib_dir/netty-codec-${NETTY_VERSION}.jar"; \
        cp /tmp/netty-handler.jar "$lib_dir/netty-handler-${NETTY_VERSION}.jar"; \
        cp /tmp/zookeeper.jar "$lib_dir/zookeeper-${ZOOKEEPER_VERSION}.jar"; \
        cp /tmp/bcprov-jdk18on.jar "$lib_dir/bcprov-jdk18on-${BOUNCYCASTLE_VERSION}.jar"; \
        cp /tmp/plexus-utils.jar "$lib_dir/plexus-utils-${PLEXUS_UTILS_VERSION}.jar"; \
        cp /tmp/jline.jar "$lib_dir/jline-${JLINE_VERSION}.jar"; \
    done \
    && rm -rf /tmp/kafka.tgz /tmp/kafka-connect-s3.zip /tmp/*.jar \
    && chown -R app:app /opt/kafka /usr/share/confluent-hub-components /var/lib/kafka-connect

COPY src/kafka-connect/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER app
WORKDIR /opt/kafka
EXPOSE 8083

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
