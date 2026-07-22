<?php
// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0



declare(strict_types=1);

use DI\Bridge\Slim\Bridge;
use DI\ContainerBuilder;
use OpenTelemetry\API\Globals;
use OpenTelemetry\SDK\Common\Configuration\Configuration;
use OpenTelemetry\SDK\Common\Configuration\Variables;
use OpenTelemetry\SDK\Logs\LoggerProviderInterface;
use OpenTelemetry\SDK\Metrics\MeterProviderInterface;
use OpenTelemetry\SDK\Trace\TracerProviderInterface;
use Psr\Http\Message\ServerRequestInterface;
use React\EventLoop\Loop;
use React\Http\HttpServer;
use React\Socket\SocketServer;
use Slim\Factory\AppFactory;

require __DIR__ . '/../vendor/autoload.php';

// Instantiate PHP-DI ContainerBuilder
$containerBuilder = new ContainerBuilder();

// Set up settings
$settings = require __DIR__ . '/../app/settings.php';
$settings($containerBuilder);

// Set up dependencies
$dependencies = require __DIR__ . '/../app/dependencies.php';
$dependencies($containerBuilder);

// Build PHP-DI Container instance
$container = $containerBuilder->build();

// Instantiate the app
AppFactory::setContainer($container);
$app = Bridge::create($container);

// Register middleware
$app->addRoutingMiddleware();

// Register routes
$routes = require __DIR__ . '/../app/routes.php';
$routes($app);

// Add Body Parsing Middleware
$app->addBodyParsingMiddleware();

// Add Error Middleware
$errorMiddleware = $app->addErrorMiddleware(true, true, true);
Loop::get()->addSignal(SIGTERM, function() {
    exit;
});

// forceFlush() makes a blocking HTTP call (Guzzle/PSR-18 is synchronous by
// spec) to the OTLP collector. Calling it directly on this single-threaded
// event loop freezes the whole server - including unrelated in-flight
// requests - for as long as the collector is slow/unreachable, which is what
// caused shipping's 2s call to /getquote to time out under load. pcntl_fork()
// duplicates the process (copy-on-write) so the child gets its own copy of
// the already-buffered spans/logs/metrics and can safely block on export
// while the parent loop keeps serving requests immediately.
pcntl_async_signals(true);
Loop::get()->addSignal(SIGCHLD, function () {
    // Reap every finished flush-child as soon as it exits, non-blocking, so
    // they never accumulate as zombies.
    while (pcntl_waitpid(-1, $status, WNOHANG) > 0) {
    }
});

function flushWithoutBlockingLoop(callable $flush, ?int &$lastChildPid): void
{
    if ($lastChildPid !== null && pcntl_waitpid($lastChildPid, $status, WNOHANG) === 0) {
        // Previous flush for this provider is still running - skip this
        // tick instead of piling up forks while the collector is slow/down.
        return;
    }

    $pid = pcntl_fork();
    if ($pid === -1) {
        return; // fork failed; try again next tick
    }
    if ($pid === 0) {
        // Child: only ever do the flush, then exit - never fall back into
        // shared server code (listening socket, other timers, etc).
        try {
            $flush();
        } finally {
            exit(0);
        }
    }
    $lastChildPid = $pid;
}

/* workaround for non-async batch processors */
$tracerFlushPid = null;
if (($tracerProvider = Globals::tracerProvider()) instanceof TracerProviderInterface) {
    Loop::addPeriodicTimer(Configuration::getInt(Variables::OTEL_BSP_SCHEDULE_DELAY)/1000, function() use ($tracerProvider, &$tracerFlushPid) {
        flushWithoutBlockingLoop(fn() => $tracerProvider->forceFlush(), $tracerFlushPid);
    });
}
$loggerFlushPid = null;
if (($loggerProvider = Globals::loggerProvider()) instanceof LoggerProviderInterface) {
    Loop::addPeriodicTimer(Configuration::getInt(Variables::OTEL_BLRP_SCHEDULE_DELAY)/1000, function() use ($loggerProvider, &$loggerFlushPid) {
        flushWithoutBlockingLoop(fn() => $loggerProvider->forceFlush(), $loggerFlushPid);
    });
}
$meterFlushPid = null;
if (($meterProvider = Globals::meterProvider()) instanceof MeterProviderInterface) {
    Loop::addPeriodicTimer(Configuration::getInt(Variables::OTEL_METRIC_EXPORT_INTERVAL)/1000, function() use ($meterProvider, &$meterFlushPid) {
        flushWithoutBlockingLoop(fn() => $meterProvider->forceFlush(), $meterFlushPid);
    });
}

$server = new HttpServer(function (ServerRequestInterface $request) use ($app) {
    $response = $app->handle($request);
    echo sprintf('[%s] "%s %s HTTP/%s" %d %d %s',
        date('Y-m-d H:i:sP'),
        $request->getMethod(),
        $request->getUri()->getPath(),
        $request->getProtocolVersion(),
        $response->getStatusCode(),
        $response->getBody()->getSize(),
        PHP_EOL,
    );

    return $response;
});

$ip = "0.0.0.0";

$ipv6_enabled = getenv('IPV6_ENABLED');

if ($ipv6_enabled == "true") {
    $ip = "[::]";
    echo "Overwriting Localhost IP: {$ip}" . PHP_EOL;
} 

$address = $ip . ':' . getenv('QUOTE_PORT');

$socket = new SocketServer($address);
$server->listen($socket);

echo "Listening on: {$address}" . PHP_EOL;
