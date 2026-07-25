/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import org.apache.kafka.clients.consumer.ConsumerConfig.*
import org.apache.kafka.clients.consumer.KafkaConsumer
import org.apache.kafka.common.serialization.ByteArrayDeserializer
import org.apache.kafka.common.serialization.StringDeserializer
import org.apache.logging.log4j.LogManager
import org.apache.logging.log4j.Logger
import oteldemo.Demo.*
import java.time.Duration.ofMillis
import java.util.*
import kotlin.system.exitProcess
import dev.openfeature.contrib.providers.flagd.FlagdOptions
import dev.openfeature.contrib.providers.flagd.FlagdProvider
import dev.openfeature.sdk.Client
import dev.openfeature.sdk.EvaluationContext
import dev.openfeature.sdk.ImmutableContext
import dev.openfeature.sdk.Value
import dev.openfeature.sdk.OpenFeatureAPI

const val topic = "orders"
const val groupID = "fraud-detection"

private val logger: Logger = LogManager.getLogger(groupID)

fun main() {
    val options = FlagdOptions.builder()
    .withGlobalTelemetry(true)
    .build()
    val flagdProvider = FlagdProvider(options)
    OpenFeatureAPI.getInstance().setProvider(flagdProvider)

    val props = Properties()
    props[KEY_DESERIALIZER_CLASS_CONFIG] = StringDeserializer::class.java.name
    props[VALUE_DESERIALIZER_CLASS_CONFIG] = ByteArrayDeserializer::class.java.name
    props[GROUP_ID_CONFIG] = groupID
    val bootstrapServers = System.getenv("KAFKA_ADDR")
    if (bootstrapServers == null) {
        println("KAFKA_ADDR is not supplied")
        exitProcess(1)
    }
    props[BOOTSTRAP_SERVERS_CONFIG] = bootstrapServers
    applyKafkaSecurityConfig(props)
    val consumer = KafkaConsumer<String, ByteArray>(props).apply {
        subscribe(listOf(topic))
    }

    var totalCount = 0L

    consumer.use {
        while (true) {
            totalCount = consumer
                .poll(ofMillis(100))
                .fold(totalCount) { accumulator, record ->
                    val newCount = accumulator + 1
                    if (getFeatureFlagValue("kafkaQueueProblems") > 0) {
                        logger.info("FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second")
                        Thread.sleep(1000)
                    }
                    val orders = OrderResult.parseFrom(record.value())
                    logger.info("Consumed record with orderId: ${orders.orderId}, and updated total count to: $newCount")
                    newCount
                }
        }
    }
}

fun applyKafkaSecurityConfig(props: Properties) {
    val securityProtocol = System.getenv("KAFKA_SECURITY_PROTOCOL")
    val saslMechanism = System.getenv("KAFKA_SASL_MECHANISM")
    val username = System.getenv("KAFKA_USERNAME")
    val password = System.getenv("KAFKA_PASSWORD")

    if (securityProtocol.isNullOrBlank() &&
        saslMechanism.isNullOrBlank() &&
        username.isNullOrBlank() &&
        password.isNullOrBlank()
    ) {
        return
    }

    if (username.isNullOrBlank() || password.isNullOrBlank()) {
        throw IllegalStateException("KAFKA_USERNAME and KAFKA_PASSWORD must be set when Kafka SASL is enabled.")
    }

    val protocol = securityProtocol.takeUnless { it.isNullOrBlank() } ?: "SASL_SSL"
    val mechanism = saslMechanism.takeUnless { it.isNullOrBlank() } ?: "SCRAM-SHA-512"

    props["security.protocol"] = protocol
    props["sasl.mechanism"] = mechanism
    props["sasl.jaas.config"] =
        "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"${escapeJaas(username)}\" password=\"${escapeJaas(password)}\";"
}

fun escapeJaas(value: String): String {
    return value.replace("\\", "\\\\").replace("\"", "\\\"")
}

/**
* Retrieves the status of a feature flag from the Feature Flag service.
*
* @param ff The name of the feature flag to retrieve.
* @return `true` if the feature flag is enabled, `false` otherwise or in case of errors.
*/
fun getFeatureFlagValue(ff: String): Int {
    val client = OpenFeatureAPI.getInstance().client
    // TODO: Plumb the actual session ID from the frontend via baggage?
    val uuid = UUID.randomUUID()

    val clientAttrs = mutableMapOf<String, Value>()
    clientAttrs["session"] = Value(uuid.toString())
    client.evaluationContext = ImmutableContext(clientAttrs)
    val intValue = client.getIntegerValue(ff, 0)
    return intValue
}
