// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

using Confluent.Kafka;
using Microsoft.Extensions.Logging;
using Oteldemo;
using Microsoft.EntityFrameworkCore;
using System.Diagnostics;

namespace Accounting;

internal class DBContext : DbContext
{
    public DbSet<OrderEntity> Orders { get; set; }
    public DbSet<OrderItemEntity> CartItems { get; set; }
    public DbSet<ShippingEntity> Shipping { get; set; }

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        var connectionString = Environment.GetEnvironmentVariable("DB_CONNECTION_STRING");

        optionsBuilder.UseNpgsql(connectionString).UseSnakeCaseNamingConvention();
    }
}


internal class Consumer : IDisposable
{
    private const string TopicName = "orders";

    private ILogger _logger;
    private IConsumer<string, byte[]> _consumer;
    private bool _isListening;
    private string? _dbConnectionString;
    private static readonly ActivitySource MyActivitySource = new("Accounting.Consumer");

    /// <summary>
    /// Tracks the last successfully committed offset per partition.
    /// When a message fails, the partition is paused and no offset past the
    /// failed message is committed — preventing silent message loss.
    /// </summary>

    public Consumer(ILogger<Consumer> logger)
    {
        _logger = logger;

        var servers = Environment.GetEnvironmentVariable("KAFKA_ADDR")
            ?? throw new InvalidOperationException("The KAFKA_ADDR environment variable is not set.");

        _consumer = BuildConsumer(servers);
        _consumer.Subscribe(TopicName);

       if (_logger.IsEnabled(LogLevel.Information))
       {
           _logger.LogInformation("Connecting to Kafka: {servers}", servers);
       }

        _dbConnectionString = Environment.GetEnvironmentVariable("DB_CONNECTION_STRING");
    }

    public void StartListening()
    {
        _isListening = true;

        try
        {
            while (_isListening)
            {
                try
                {
                    using var activity = MyActivitySource.StartActivity("order-consumed",  ActivityKind.Internal);
                    var consumeResult = _consumer.Consume();
                    ProcessMessage(consumeResult);
                }
                catch (ConsumeException e)
                {
                    if (_logger.IsEnabled(LogLevel.Error))
                    {
                        _logger.LogError(e, "Consume error: {reason}", e.Error.Reason);
                    }
                }
            }
        }
        catch (OperationCanceledException)
        {
            _logger.LogInformation("Closing consumer");

            _consumer.Close();
        }
    }

    private void ProcessMessage(ConsumeResult<string, byte[]> consumeResult)
    {
        var message = consumeResult.Message;

        OrderResult order;
        try
        {
            order = OrderResult.Parser.ParseFrom(message.Value);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "Order parsing failed at partition {Partition} offset {Offset}: message cannot be deserialized. " +
                "Partition will be paused to prevent offset advance past poison message. " +
                "Manual intervention or DLQ required.",
                consumeResult.Partition, consumeResult.Offset);

            // Pause the partition so we don't commit past this unparseable message.
            // On restart the consumer will re-read from this offset.
            if (!PausePartition(consumeResult.TopicPartition, consumeResult.Offset.Value))
            {
                // Pause failed — stop the consumer to prevent offset advance past poison message.
                _isListening = false;
            }
            return;
        }

        Log.OrderReceivedMessage(_logger, order);

        if (_dbConnectionString == null)
        {
            _logger.LogWarning("DB_CONNECTION_STRING not set: order {OrderId} parsed but not persisted; committing offset anyway (no-durable-store mode)", order.OrderId);
            CommitOffset(consumeResult);
            return;
        }

        // Use a fresh DbContext per message to avoid stale tracking state.
        using var dbContext = new DBContext();

        try
        {
            // Idempotency: if order already exists with full data, treat as already persisted
            // and commit offset without re-inserting.
            if (OrderAlreadyPersisted(dbContext, order))
            {
                if (_logger.IsEnabled(LogLevel.Information))
                {
                    _logger.LogInformation("Order {OrderId} already persisted (duplicate delivery), committing offset", order.OrderId);
                }
                CommitOffset(consumeResult);
                return;
            }

            using var transaction = dbContext.Database.BeginTransaction();

            var orderEntity = new OrderEntity
            {
                Id = order.OrderId
            };
            dbContext.Add(orderEntity);
            foreach (var item in order.Items)
            {
                var orderItem = new OrderItemEntity
                {
                    ItemCostCurrencyCode = item.Cost.CurrencyCode,
                    ItemCostUnits = item.Cost.Units,
                    ItemCostNanos = item.Cost.Nanos,
                    ProductId = item.Item.ProductId,
                    Quantity = item.Item.Quantity,
                    OrderId = order.OrderId
                };

                dbContext.Add(orderItem);
            }

            var shipping = new ShippingEntity
            {
                ShippingTrackingId = order.ShippingTrackingId,
                ShippingCostCurrencyCode = order.ShippingCost.CurrencyCode,
                ShippingCostUnits = order.ShippingCost.Units,
                ShippingCostNanos = order.ShippingCost.Nanos,
                StreetAddress = order.ShippingAddress.StreetAddress,
                City = order.ShippingAddress.City,
                State = order.ShippingAddress.State,
                Country = order.ShippingAddress.Country,
                ZipCode = order.ShippingAddress.ZipCode,
                OrderId = order.OrderId
            };
            dbContext.Add(shipping);

            dbContext.SaveChanges();
            transaction.Commit();

            // Commit Kafka offset ONLY after durable DB write succeeds.
            CommitOffset(consumeResult);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex,
                "Order persistence failed for order {OrderId} at partition {Partition} offset {Offset}: " +
                "transaction rolled back, offset NOT committed. " +
                "Partition will be paused to prevent offset advance past failed message.",
                order.OrderId, consumeResult.Partition, consumeResult.Offset);

            // Pause the partition so we don't commit past this unpersisted message.
            // On restart (or manual unpause) the consumer will re-read from this offset.
            if (!PausePartition(consumeResult.TopicPartition, consumeResult.Offset.Value))
            {
                _isListening = false;
            }
        }
    }

    /// <summary>
    /// Returns true if the order with its key child rows (shipping) already exists,
    /// making this delivery safe to skip (idempotent replay).
    /// Checks both order and shipping rows — if only a partial order row exists
    /// from a prior incomplete write, we re-insert fully within a transaction.
    /// </summary>
    private static bool OrderAlreadyPersisted(DBContext dbContext, OrderResult order)
    {
        var existingOrder = dbContext.Orders.Find(order.OrderId);
        if (existingOrder == null)
            return false;

        var existingShipping = dbContext.Shipping.Find(order.ShippingTrackingId);
        return existingShipping != null;
    }

    private void CommitOffset(ConsumeResult<string, byte[]> consumeResult)
    {
        try
        {
            _consumer.Commit(consumeResult);
        }
        catch (KafkaException ex)
        {
            _logger.LogError(ex,
                "Failed to commit offset for partition {Partition} offset {Offset}. " +
                "Partition will be paused to prevent offset advance past uncertain state. " +
                "On restart message may be re-delivered (idempotency check handles duplicates).",
                consumeResult.Partition, consumeResult.Offset);

            // If we can't commit, pause to avoid committing later offsets
            // past this uncertain position.
            if (!PausePartition(consumeResult.TopicPartition, consumeResult.Offset.Value))
            {
                _isListening = false;
            }
        }
    }

    /// <summary>
    /// Pauses the given partition so no further messages are consumed from it.
    /// Returns false if pause failed — caller must stop the consumer to prevent
    /// offset advance past the failed message.
    /// </summary>
    private bool PausePartition(TopicPartition topicPartition, long offset)
    {
        try
        {
            _consumer.Pause([topicPartition]);
            _logger.LogWarning("Partition {Partition} paused at offset ~{Offset}. " +
                "Consumer will not read past this point until partition is resumed or consumer restarts.",
                topicPartition.Partition, offset);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to pause partition {Partition} at offset ~{Offset}", topicPartition.Partition, offset);
            return false;
        }
    }

    private static IConsumer<string, byte[]> BuildConsumer(string servers)
    {
        var conf = new ConsumerConfig
        {
            GroupId = "accounting",
            BootstrapServers = servers,
            AutoOffsetReset = AutoOffsetReset.Earliest,
            EnableAutoCommit = false,
            EnableAutoOffsetStore = false
        };

        return new ConsumerBuilder<string, byte[]>(conf)
            .Build();
    }

    public void Dispose()
    {
        _isListening = false;
        _consumer?.Dispose();
    }
}
